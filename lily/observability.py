"""Provider observability: aggregate metrics, health, and usage telemetry.

This module intentionally persists only aggregate per-profile counters
(successes, failures, token totals, and coarse error-class buckets) and never
stores prompts, completions, chat content, secrets, or provider responses.
Chat-level request/byte quotas continue to live in ``usage``; this is the
provider-health and cost side of the picture.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from .config import settings
from .db import Database, db
from .model_router import ModelRouter

logger = logging.getLogger("lily.observability")


class ObservabilityService:
    def __init__(
        self,
        router: ModelRouter,
        database: Database = db,
        *,
        enabled: bool | None = None,
        flush_seconds: float | None = None,
    ) -> None:
        self.router = router
        self.db = database
        self.enabled = settings.observability_enabled if enabled is None else enabled
        self.flush_seconds = settings.observability_flush_seconds if flush_seconds is None else flush_seconds
        self._task: asyncio.Task | None = None
        self._started = False

    async def flush(self) -> int:
        """Persist in-memory aggregates and reset them. Returns row count."""
        if not self.enabled:
            return 0
        rows = [dict(row) for row in await self.router.telemetry()]
        if not rows:
            return 0
        await self.db.record_provider_telemetry(rows)
        await self.router.reset_telemetry()
        total_requests = sum(int(row["successes"] + row["failures"]) for row in rows)
        if total_requests:
            logger.info("Flushed provider telemetry (requests=%s, profiles=%s)", total_requests, len(rows))
        return len(rows)

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self.flush_seconds)
            try:
                await self.flush()
            except Exception as exc:  # never let a flush kill the worker
                logger.warning("Provider telemetry flush failed: %s", exc)

    def start(self) -> None:
        if not self.enabled or self._started:
            return
        self._started = True
        self._task = asyncio.create_task(self._loop(), name="lily-observability-flush")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await asyncio.gather(self._task, return_exceptions=True)
        finally:
            self._task = None
            self._started = False
        await self.flush()  # final persistence on shutdown

    async def report(self, limit: int = 100) -> dict[str, Any]:
        """Return a bounded redacted observability snapshot for chat/CLI display."""
        live = await self.router.status()
        try:
            history = await self.db.latest_provider_telemetry(limit)
        except Exception:
            # Live status must remain available even if the durable store is
            # not reachable; the aggregate defaults to the in-memory view.
            history = []
        total_successes = sum(int(row.get("successes", 0) or 0) for row in history)
        total_failures = sum(int(row.get("failures", 0) or 0) for row in history)
        total_tokens = sum(int(row.get("prompt_tokens", 0) or 0) + int(row.get("completion_tokens", 0) or 0) for row in history)
        return {
            "profiles": [
                {
                    "name": row["name"],
                    "model": row["model"],
                    "family": row["family"],
                    "privacy_tier": row["privacy_tier"],
                    "available": row["available"],
                    "successes": row["successes"],
                    "failures": row["failures"],
                    "last_latency_ms": row["last_latency_ms"],
                    "total_tokens": row["total_tokens"],
                    "prompt_tokens": row["prompt_tokens"],
                    "completion_tokens": row["completion_tokens"],
                    "error_classes": row["error_classes"],
                }
                for row in live
            ],
            "history_count": len(history),
            "total_requests": total_successes + total_failures,
            "total_successes": total_successes,
            "total_failures": total_failures,
            "total_tokens": total_tokens,
        }

    def public_text(self, report: dict[str, Any]) -> str:
        """Render a compact human/professional summary (no secrets or prompts)."""
        lines: list[str] = []
        for profile in report["profiles"]:
            status = "available" if profile["available"] else "cooling down"
            lines.append(
                f"• {profile['name']} / {profile['model']} ({profile['family']}) — {status}; "
                f"ok={profile['successes']}; fail={profile['failures']}; "
                f"tokens={profile['total_tokens']}; "
                f"last={profile['last_latency_ms']}ms"
            )
        if not lines:
            lines.append("No AI provider profiles are configured.")
        lines.append(
            f"_\u200bAggregate (history={report['history_count']}): "
            f"{report['total_requests']} requests, {report['total_successes']} ok, "
            f"{report['total_failures']} failed, {report['total_tokens']} tokens._"
        )
        return "\n".join(lines)


def build_observability(
    router: ModelRouter,
    database: Database = db,
    *,
    enabled: bool | None = None,
    flush_seconds: float | None = None,
) -> ObservabilityService:
    """Construct the service bound to the live router (called from main/CLI)."""
    return ObservabilityService(router, database, enabled=enabled, flush_seconds=flush_seconds)
