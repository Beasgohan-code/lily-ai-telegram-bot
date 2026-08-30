"""Always-on style operational briefing for Lily administrators."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


async def build_briefing(
    db: Any,
    chat_id: int | None = None,
    *,
    moderation: Any | None = None,
    observability: Any | None = None,
) -> dict[str, Any]:
    """Aggregate bounded operational counters — no secrets or private memo text.

    If ``moderation`` is provided, the briefing also surfaces the moderation
    inbox (open reports, pending verifications, unresolved warnings) as counts
    only. If ``observability`` is provided, provider health aggregates are
    included. Neither passes private reason, note, or prompt content.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    queue = await db.list_encoding_jobs(chat_id, limit=50) if chat_id is not None else []
    reports = await db.list_reports(chat_id, status="open", limit=20) if chat_id is not None else []
    open_reports = reports
    queued = [item for item in queue if str(item.get("state")) == "queued"]
    running = [item for item in queue if str(item.get("state")) == "running"]
    failed = [item for item in queue if str(item.get("state")) == "failed"]
    pending_verifications = 0
    warnings_pending = 0
    sections = [
        f"**Lily ops briefing** · {now}",
        f"• Encoding queue: {len(queued)} queued, {len(running)} running, {len(failed)} failed",
    ]
    if chat_id is not None:
        sections.append(f"• Open moderation reports (this chat): {len(open_reports)}")
    if moderation is not None:
        pending_verifications = len(await moderation.pending_verifications(chat_id)) if chat_id is not None else 0
        warnings_pending = len(await moderation.warnings_pending(chat_id)) if chat_id is not None else 0
        sections.append(f"• Moderation inbox (this chat): {len(open_reports)} reports, {pending_verifications} pending verifications, {warnings_pending} unresolved warning sets")
    if observability is not None:
        report = await observability.report(limit=50)
        sections.append(f"• AI health: {report['total_requests']} requests ({report['total_successes']} ok / {report['total_failures']} failed), {report['total_tokens']} tokens")
    sections.append("• Tip: run a scenario with `Lily, start scenario startup-mvp` for phased agency workflows.")
    return {
        "generated_at": now,
        "encoding": {"queued": len(queued), "running": len(running), "failed": len(failed)},
        "open_reports": len(open_reports),
        "pending_verifications": pending_verifications,
        "warnings_pending": warnings_pending,
        "text": "\n".join(sections),
    }
