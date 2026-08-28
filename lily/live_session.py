"""Ephemeral tg-thinking draft session — one preview, one final reply."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from .config import settings
from .rich import rich


class LiveThinkingSession:
    """Show a single thinking draft that updates in place, then clears before the final message."""

    def __init__(self, chat_id: int, draft_id: int | str, *, min_display_seconds: float | None = None) -> None:
        self.chat_id = chat_id
        self.draft_id = draft_id
        self.min_display_seconds = (
            settings.thinking_min_display_seconds if min_display_seconds is None else min_display_seconds
        )
        self._started_at = 0.0
        self._active = False

    async def start(self, status: str = "Thinking…") -> bool:
        if not settings.rich_live_previews:
            return False
        self._started_at = time.monotonic()
        self._active = True
        return await rich.thinking_only(self.chat_id, status, draft_id=self.draft_id)

    async def update(self, status: str) -> bool:
        if not self._active or not settings.rich_live_previews:
            return False
        return await rich.thinking_only(self.chat_id, status, draft_id=self.draft_id)

    async def finish(self) -> None:
        if not self._active:
            return
        elapsed = time.monotonic() - self._started_at
        remaining = self.min_display_seconds - elapsed
        if remaining > 0:
            await asyncio.sleep(remaining)
        await rich.clear_draft(self.chat_id, self.draft_id)
        self._active = False

    async def __aenter__(self) -> "LiveThinkingSession":
        await self.start()
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.finish()


def work_draft_id(update: Any) -> int:
    return rich.normalize_draft_id(f"work:{update.update_id}")


def bind_session(context: Any, update: Any) -> LiveThinkingSession:
    chat = update.effective_chat
    if not chat:
        raise RuntimeError("Missing chat for live thinking session.")
    draft_id = work_draft_id(update)
    session = LiveThinkingSession(chat.id, draft_id)
    context.user_data["_live_thinking_session"] = session
    return session


def active_session(context: Any) -> LiveThinkingSession | None:
    value = context.user_data.get("_live_thinking_session")
    return value if isinstance(value, LiveThinkingSession) else None
