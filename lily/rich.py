from __future__ import annotations

import hashlib
import itertools
from typing import Any

import httpx

from .config import settings


def text(value: str) -> str:
    return str(value)


def bold(value: str | list[Any]) -> dict[str, Any]:
    return {"type": "bold", "text": value}


def italic(value: str | list[Any]) -> dict[str, Any]:
    return {"type": "italic", "text": value}


def code(value: str) -> dict[str, Any]:
    return {"type": "code", "text": value}


def custom_emoji(custom_emoji_id: str, fallback_text: str = "✨") -> dict[str, Any]:
    return {"type": "custom_emoji", "custom_emoji_id": str(custom_emoji_id), "text": fallback_text}


def paragraph(value: str | list[Any]) -> dict[str, Any]:
    return {"type": "paragraph", "text": value}


def heading(value: str, size: int = 2) -> dict[str, Any]:
    return {"type": "heading", "text": value, "size": max(1, min(6, size))}


def preformatted(value: str, language: str | None = None) -> dict[str, Any]:
    block: dict[str, Any] = {"type": "pre", "text": value}
    if language:
        block["language"] = language
    return block


def divider() -> dict[str, Any]:
    return {"type": "divider"}


def blockquote(value: str | list[Any], credit: str | None = None) -> dict[str, Any]:
    block: dict[str, Any] = {"type": "blockquote", "blocks": [paragraph(value)]}
    if credit:
        block["credit"] = credit
    return block


def expandable_quote(value: str, credit: str | None = None) -> dict[str, Any]:
    block: dict[str, Any] = {"type": "expandable_blockquote", "text": value}
    if credit:
        block["credit"] = credit
    return block


def details(summary: str, blocks: list[dict[str, Any]], is_open: bool = False) -> dict[str, Any]:
    return {"type": "details", "summary": summary, "blocks": blocks, "is_open": is_open}


def table(rows: list[list[str]], bordered: bool = True, striped: bool = True, compact: bool = True, caption: str | None = None) -> dict[str, Any]:
    cells = []
    for row_index, row in enumerate(rows):
        cells.append([
            {"text": value, **({"is_header": True} if row_index == 0 else {})}
            for value in row
        ])
    result: dict[str, Any] = {
        "type": "table",
        "cells": cells,
        "is_bordered": bordered,
        "is_striped": striped,
        "is_compact": compact,
    }
    if caption:
        result["caption"] = caption
    return result


def list_block(items: list[str]) -> dict[str, Any]:
    return {"type": "list", "items": [{"label": "", "blocks": [paragraph(item)]} for item in items]}


def thinking() -> dict[str, Any]:
    return {"type": "thinking"}


def activity_status(stage: str) -> dict[str, Any]:
    """A visible procedural status, deliberately not a model reasoning trace."""
    return details("Lily activity", [paragraph(str(stage)[:400])], is_open=False)


def live_activity_blocks(summary: str, stages: list[str], status: str) -> list[dict[str, Any]]:
    """Build a safe draft payload that never contains model reasoning or raw commands."""
    return [
        heading("Lily live activity", 3),
        paragraph(str(summary)[:800]),
        activity_status(str(status)[:400]),
        details("Public execution stages", [list_block([str(stage)[:180] for stage in stages[:8]])]),
    ]


def rich_message(blocks: list[dict[str, Any]]) -> dict[str, Any]:
    return {"blocks": blocks}


def inline_keyboard(rows: list[list[tuple[str, str] | tuple[str, str, str]]]) -> dict[str, Any]:
    keyboard = []
    for row in rows:
        rendered = []
        for entry in row:
            label, data = entry[0], entry[1]
            button: dict[str, Any] = {"text": label, "callback_data": data}
            if len(entry) > 2 and settings.rich_button_styles:
                button["style"] = entry[2]
            rendered.append(button)
        keyboard.append(rendered)
    return {"inline_keyboard": keyboard}


def confirmation_keyboard(action_id: str, include_details: bool = True) -> dict[str, Any]:
    rows: list[list[tuple[str, str] | tuple[str, str, str]]] = [[("Yes, continue", f"confirm:{action_id}:yes", "primary"), ("No, cancel", f"confirm:{action_id}:no", "danger")]]
    if include_details:
        rows.append([("View details", f"confirm:{action_id}:details", "secondary")])
    return inline_keyboard(rows)


class RichClient:
    def __init__(self) -> None:
        self.base = settings.bot_api_base.rstrip("/")
        self.token = settings.bot_token
        self.timeout = httpx.Timeout(60.0, connect=10.0)
        self._draft_ids = itertools.count(1001)

    async def call(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")
        url = f"{self.base}{self.token}/{method}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram {method} failed: {data.get('description', data)}")
        return data.get("result", data)

    async def send(self, chat_id: int, blocks: list[dict[str, Any]], reply_markup: dict[str, Any] | None = None, reply_to: int | None = None, protect_content: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {"chat_id": chat_id, "rich_message": rich_message(blocks), "protect_content": protect_content}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        if reply_to:
            payload["reply_parameters"] = {"message_id": reply_to}
        try:
            return await self.call("sendRichMessage", payload)
        except Exception:
            # Keeps Lily usable if a deployment temporarily runs an older local Bot API binary.
            html = self._fallback_html(blocks)
            fallback: dict[str, Any] = {"chat_id": chat_id, "text": html, "parse_mode": "HTML", "protect_content": protect_content}
            if reply_markup:
                fallback["reply_markup"] = reply_markup
            if reply_to:
                fallback["reply_parameters"] = {"message_id": reply_to}
            return await self.call("sendMessage", fallback)

    async def draft(self, chat_id: int, blocks: list[dict[str, Any]], draft_id: int | None = None, can_stop: bool = True) -> bool:
        draft_id = draft_id or next(self._draft_ids)
        try:
            await self.call("sendRichMessageDraft", {
                "chat_id": chat_id,
                "draft_id": draft_id,
                "rich_message": rich_message(blocks),
                "can_stop": can_stop,
                "keep_on_stop": False,
            })
            return True
        except Exception:
            return False

    async def preview(self, chat_id: int, summary: str, stages: list[str], draft_id: int | str | None = None, status: str = "Waiting for confirmation or starting the approved task.") -> bool:
        """Send an optional live Rich Message draft with public task stages only."""
        normalized_id = draft_id
        if isinstance(draft_id, str):
            normalized_id = int(hashlib.blake2s(draft_id.encode("utf-8"), digest_size=4).hexdigest(), 16)
        return await self.draft(chat_id, live_activity_blocks(summary, stages, status), draft_id=normalized_id, can_stop=True)

    def _fallback_html(self, blocks: list[dict[str, Any]]) -> str:
        parts: list[str] = []
        for block in blocks:
            kind = block.get("type")
            if kind == "heading":
                parts.append(f"<b>{self._escape(self._plain(block.get('text', '')))}</b>")
            elif kind == "blockquote":
                inner = "\n".join(self._plain(b.get("text", "")) for b in block.get("blocks", []))
                parts.append(f"<blockquote>{self._escape(inner)}</blockquote>")
            elif kind == "table":
                rows = []
                for row in block.get("cells", []):
                    rows.append(" | ".join(self._plain(c.get("text", "")) for c in row))
                parts.append(f"<pre>{self._escape(chr(10).join(rows))}</pre>")
            elif kind == "pre":
                parts.append(f"<pre>{self._escape(self._plain(block.get('text', '')))}</pre>")
            elif kind == "divider":
                parts.append("────────────")
            elif kind == "details":
                inner = self._fallback_html(block.get("blocks", []))
                parts.append(f"<b>{self._escape(self._plain(block.get('summary', '')))}</b>\n{inner}")
            elif kind == "thinking":
                parts.append("<i>Thinking…</i>")
            else:
                parts.append(self._escape(self._plain(block.get("text", ""))))
        return "\n\n".join(parts)[:4090]

    def _plain(self, value: Any) -> str:
        if isinstance(value, list):
            return "".join(self._plain(item) for item in value)
        if isinstance(value, dict):
            return self._plain(value.get("text", ""))
        return str(value)

    def _escape(self, value: str) -> str:
        return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


rich = RichClient()
