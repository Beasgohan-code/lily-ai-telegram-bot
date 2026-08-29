"""Ephemeral tg-thinking draft session — real progressive UI stages, one final reply."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from .config import settings
from .rich import rich


class LiveThinkingSession:
    """Show a single thinking draft that updates in place with real plan/work stages.

    Flow:
      1. start() / start_plan()  → thinking + plan stages
      2. update() / advance()    → move active stage, refresh draft
      3. start_work()            → switch phase to working
      4. finish()                → clear draft before the final message
    """

    def __init__(
        self,
        chat_id: int,
        draft_id: int | str,
        *,
        min_display_seconds: float | None = None,
        stages: list[str] | None = None,
        summary: str = "",
    ) -> None:
        self.chat_id = chat_id
        self.draft_id = draft_id
        self.min_display_seconds = (
            settings.thinking_min_display_seconds if min_display_seconds is None else min_display_seconds
        )
        self.summary = summary or "Working on your request."
        self.stages: list[str] = list(stages or ["Understand request", "Build plan", "Execute", "Reply"])
        self.active_index = 0
        self.phase = "plan"  # plan | working | done
        self._started_at = 0.0
        self._active = False

    @property
    def is_active(self) -> bool:
        return bool(self._active)


    async def start(self, status: str = "Thinking…") -> bool:
        """Begin with a minimal thinking indicator (backward compatible)."""
        if not settings.rich_live_previews:
            return False
        self._started_at = time.monotonic()
        self._active = True
        self.phase = "plan"
        self.active_index = 0
        return await rich.thinking_only(self.chat_id, status, draft_id=self.draft_id)

    async def start_plan(self, status: str = "Building plan…", stages: list[str] | None = None) -> bool:
        """Start the real planning UI with stage checklist + thinking animation."""
        if not settings.rich_live_previews:
            return False
        if stages:
            self.stages = list(stages)[:8]
        self._started_at = time.monotonic()
        self._active = True
        self.phase = "plan"
        self.active_index = 0
        return await rich.plan_preview(
            self.chat_id,
            self.summary,
            self.stages,
            status=status,
            draft_id=self.draft_id,
            active_index=self.active_index,
        )

    async def start_work(self, status: str = "Executing…") -> bool:
        """Switch from plan → working phase and refresh the draft."""
        if not self._active or not settings.rich_live_previews:
            return False
        self.phase = "working"
        # Jump active marker to the first non-done stage if still on plan stages.
        if self.active_index < len(self.stages) - 1:
            self.active_index = min(self.active_index + 1, len(self.stages) - 1)
        return await rich.work_preview(
            self.chat_id,
            self.summary,
            self.stages,
            status=status,
            draft_id=self.draft_id,
            active_index=self.active_index,
        )

    async def update(self, status: str, *, stage: str | None = None) -> bool:
        """Refresh status text. Optionally append/replace the current stage label."""
        if not self._active or not settings.rich_live_previews:
            return False
        if stage and self.stages:
            # Update the label of the active stage.
            idx = min(self.active_index, len(self.stages) - 1)
            self.stages[idx] = str(stage)[:180]
        if self.phase == "plan":
            return await rich.plan_preview(
                self.chat_id, self.summary, self.stages, status=status,
                draft_id=self.draft_id, active_index=self.active_index,
            )
        return await rich.work_preview(
            self.chat_id, self.summary, self.stages, status=status,
            draft_id=self.draft_id, active_index=self.active_index,
        )

    async def advance(self, status: str | None = None) -> bool:
        """Mark current stage done and move to the next one."""
        if not self._active or not settings.rich_live_previews:
            return False
        if self.active_index < len(self.stages) - 1:
            self.active_index += 1
        label = status or self.stages[self.active_index]
        if self.phase == "plan":
            return await rich.plan_preview(
                self.chat_id, self.summary, self.stages, status=label,
                draft_id=self.draft_id, active_index=self.active_index,
            )
        return await rich.work_preview(
            self.chat_id, self.summary, self.stages, status=label,
            draft_id=self.draft_id, active_index=self.active_index,
        )

    async def finish(self) -> None:
        if not self._active:
            return
        elapsed = time.monotonic() - self._started_at
        remaining = self.min_display_seconds - elapsed
        if remaining > 0:
            await asyncio.sleep(remaining)
        await rich.clear_draft(self.chat_id, self.draft_id)
        self._active = False
        self.phase = "done"

    async def __aenter__(self) -> "LiveThinkingSession":
        await self.start_plan()
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.finish()


def work_draft_id(update: Any) -> int:
    return rich.normalize_draft_id(f"work:{update.update_id}")


def bind_session(
    context: Any,
    update: Any,
    *,
    stages: list[str] | None = None,
    summary: str = "",
) -> LiveThinkingSession:
    chat = update.effective_chat
    if not chat:
        raise RuntimeError("Missing chat for live thinking session.")
    draft_id = work_draft_id(update)
    session = LiveThinkingSession(chat.id, draft_id, stages=stages, summary=summary)
    context.user_data["_live_thinking_session"] = session
    return session


def active_session(context: Any) -> LiveThinkingSession | None:
    value = context.user_data.get("_live_thinking_session")
    return value if isinstance(value, LiveThinkingSession) else None
