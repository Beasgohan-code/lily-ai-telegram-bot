"""Request-scoped draft state to avoid duplicate Telegram messages."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DraftSession:
    draft_id: int
    stopped: bool = False
    last_status: str = ""


def session_key(chat_id: int, user_id: int) -> str:
    return f"{chat_id}:{user_id}"


def get_session(context: Any, chat_id: int, user_id: int, draft_id: int) -> DraftSession:
    store: dict[str, DraftSession] = context.user_data.setdefault("_draft_sessions", {})
    key = session_key(chat_id, user_id)
    current = store.get(key)
    if current is None or current.draft_id != draft_id:
        current = DraftSession(draft_id=draft_id)
        store[key] = current
    return current


def mark_stopped(context: Any, chat_id: int, user_id: int) -> bool:
    store: dict[str, DraftSession] = context.user_data.get("_draft_sessions", {})
    session = store.get(session_key(chat_id, user_id))
    if not session:
        return False
    session.stopped = True
    return True


def is_stopped(context: Any, chat_id: int, user_id: int) -> bool:
    store: dict[str, DraftSession] = context.user_data.get("_draft_sessions", {})
    session = store.get(session_key(chat_id, user_id))
    return bool(session and session.stopped)
