"""Always-on style operational briefing for Lily administrators."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


async def build_briefing(db: Any, chat_id: int | None = None) -> dict[str, Any]:
    """Aggregate bounded operational counters — no secrets or private memo text."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    queue = await db.list_encoding_jobs(chat_id, limit=50) if chat_id is not None else []
    reports = await db.list_reports(chat_id, status="open", limit=20) if chat_id is not None else []
    open_reports = reports
    queued = [item for item in queue if str(item.get("state")) == "queued"]
    running = [item for item in queue if str(item.get("state")) == "running"]
    failed = [item for item in queue if str(item.get("state")) == "failed"]
    sections = [
        f"**Lily ops briefing** · {now}",
        f"• Encoding queue: {len(queued)} queued, {len(running)} running, {len(failed)} failed",
    ]
    if chat_id is not None:
        sections.append(f"• Open moderation reports (this chat): {len(open_reports)}")
    sections.append("• Tip: run a scenario with `Lily, start scenario startup-mvp` for phased agency workflows.")
    return {
        "generated_at": now,
        "encoding": {"queued": len(queued), "running": len(running), "failed": len(failed)},
        "open_reports": len(open_reports),
        "text": "\n".join(sections),
    }
