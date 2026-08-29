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


def expandable_quote(value: str, credit: str | None = None, *, blocks: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Bot API 10.3 InputRichBlockExpandableBlockQuotation (collapsed-by-default quotation)."""
    block: dict[str, Any] = {"type": "expandable_blockquote"}
    if blocks:
        block["blocks"] = blocks
    else:
        text_value = str(value or "")[:4000]
        block["text"] = text_value
        block["blocks"] = [paragraph(text_value)]
    if credit:
        block["credit"] = credit
    return block


def details(summary: str, blocks: list[dict[str, Any]], is_open: bool = False) -> dict[str, Any]:
    return {"type": "details", "summary": summary, "blocks": blocks, "is_open": is_open}


def table(
    rows: list[list[str]],
    bordered: bool = True,
    striped: bool = True,
    compact: bool = True,
    caption: str | None = None,
) -> dict[str, Any]:
    """Bot API InputRichBlockTable. Bot API 10.3 adds *is_compact* for denser mobile layout."""
    cells: list[list[dict[str, Any]]] = []
    for row_index, row in enumerate(rows):
        cells.append([
            {"text": str(value), **({"is_header": True} if row_index == 0 else {})}
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
        result["caption"] = str(caption)[:512]
    return result


def document_block(
    file_id: str | None = None,
    *,
    url: str | None = None,
    caption: str | None = None,
    file_name: str | None = None,
) -> dict[str, Any]:
    """Bot API 10.3 InputRichBlockDocument — embed a managed file in a rich message."""
    block: dict[str, Any] = {"type": "document"}
    if file_id:
        block["file_id"] = str(file_id)
    elif url:
        block["url"] = str(url)[:2048]
    else:
        raise ValueError("document_block requires file_id or url")
    if caption:
        block["caption"] = str(caption)[:1024]
    if file_name:
        block["file_name"] = str(file_name)[:128]
    return block


def buttons_block(rows: list[list[dict[str, Any]]]) -> dict[str, Any]:
    """Bot API 10.3 InputRichBlockButtons — action rows inside the rich body."""
    return {"type": "buttons", "rows": rows}


def list_block(items: list[str]) -> dict[str, Any]:
    return {"type": "list", "items": [{"label": "", "blocks": [paragraph(item)]} for item in items]}


def thinking(status: str | None = None) -> dict[str, Any]:
    """Official Bot API thinking block (animated AI indicator / tg-thinking).

    Optional *status* is a short public label clients may show beside the
    animation (never model chain-of-thought).
    """
    block: dict[str, Any] = {"type": "thinking"}
    if status:
        block["status"] = str(status)[:120]
    return block


def live_action(
    status: str = "Thinking…",
    *,
    stages: list[str] | None = None,
    active_index: int = 0,
    phase: str = "plan",
    actions: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Live draft payload: tg-thinking + status + optional stage strip + disabled actions.

    Buttons in *actions* are forced disabled while the draft is streaming.
    Pass final enabled buttons only on ``rich.send``.
    """
    blocks: list[dict[str, Any]] = [thinking(status)]
    phase_label = {"plan": "Planning", "working": "Working", "done": "Done"}.get(phase, "Working")
    blocks.append(paragraph(f"🔄 {phase_label} · {str(status)[:160]}"))
    if stages:
        stage_list = _normalize_stages(list(stages), status)
        lines = _stage_lines(stage_list, active_index=active_index)
        blocks.append(preformatted("\n".join(lines)))
    if actions:
        # Force disabled for streaming safety
        disabled_rows: list[list[dict[str, Any]]] = []
        for row in actions:
            disabled_rows.append([
                {**dict(btn), "disabled": {}} if isinstance(btn, dict) else {"text": str(btn), "disabled": {}}
                for btn in (row if isinstance(row, list) else [row])
            ])
        blocks.append({"type": "buttons", "rows": disabled_rows})
    return blocks


# Public stage markers — never model chain-of-thought, only safe progress labels.
_STAGE_DONE = "✅"
_STAGE_ACTIVE = "🔄"
_STAGE_PENDING = "⏳"
_STAGE_FAIL = "❌"


def _normalize_stages(stages: list[str] | None, status: str) -> list[str]:
    cleaned = [str(s).strip()[:180] for s in (stages or []) if str(s).strip()]
    if not cleaned:
        cleaned = [str(status or "Working…")[:180]]
    return cleaned[:8]


def _stage_lines(stages: list[str], active_index: int | None = None) -> list[str]:
    """Turn a stage list into a visual progress checklist."""
    lines: list[str] = []
    total = len(stages)
    for i, stage in enumerate(stages):
        # Strip any existing emoji prefix so we control the marker.
        bare = stage.lstrip("✅🔄⏳❌•- ").strip() or stage
        if active_index is None:
            # Heuristic: last item is current when caller did not pass an index.
            if i < total - 1:
                marker = _STAGE_DONE
            else:
                marker = _STAGE_ACTIVE
        else:
            if i < active_index:
                marker = _STAGE_DONE
            elif i == active_index:
                marker = _STAGE_ACTIVE
            else:
                marker = _STAGE_PENDING
        lines.append(f"{marker} {bare}")
    return lines


def activity_status(stage: str) -> dict[str, Any]:
    """A visible procedural status, deliberately not a model reasoning trace."""
    return details("Lily activity", [paragraph(str(stage)[:400])], is_open=True)


def thinking_only_blocks(status: str = "Thinking…") -> list[dict[str, Any]]:
    """Minimal tg-thinking preview — animation + short public status."""
    return live_action(status or "Thinking…", phase="plan")


def thinking_blocks(summary: str, status: str) -> list[dict[str, Any]]:
    """Public AI activity card — never exposes private model reasoning."""
    if settings.compact_responses:
        return thinking_only_blocks(status or summary)
    return [
        heading("Lily", 3),
        thinking(),
        paragraph(str(status)[:400]),
        details("Request status", [paragraph(str(summary)[:700])], is_open=False),
    ]


def plan_stages_blocks(
    summary: str,
    stages: list[str],
    status: str,
    *,
    phase: str = "plan",
    active_index: int | None = None,
    show_thinking: bool = True,
) -> list[dict[str, Any]]:
    """Real UI stages for plan / working.

    phase:
      - "plan"     → planning the action
      - "working"  → executing the plan
      - "done"     → finished (no thinking animation)
    """
    stage_list = _normalize_stages(stages, status)
    lines = _stage_lines(stage_list, active_index=active_index)
    phase_label = {
        "plan": "📋 Planning",
        "working": "⚙️ Working",
        "done": "✅ Done",
    }.get(phase, "⚙️ Working")

    blocks: list[dict[str, Any]] = [heading("Lily", 3)]
    if show_thinking and phase != "done":
        blocks.append(thinking(status))

    blocks.append(paragraph(f"{phase_label} · {str(status)[:200]}"))
    if summary:
        blocks.append(paragraph(str(summary)[:600]))

    # Always show the stage checklist as an open details block so the UI is visible.
    blocks.append(
        details(
            f"Stages ({sum(1 for l in lines if l.startswith(_STAGE_DONE))}/{len(lines)})",
            [list_block(lines)],
            is_open=True,
        )
    )
    return blocks


def live_activity_blocks(
    summary: str,
    stages: list[str],
    status: str,
    *,
    show_thinking: bool = False,
    phase: str = "working",
    active_index: int | None = None,
) -> list[dict[str, Any]]:
    """Build a safe draft payload with real progressive UI stages.

    Never contains model reasoning or raw commands — only public progress labels.
    """
    # Even in compact mode we still surface a short stage line so the user sees progress.
    if settings.compact_responses and not stages:
        return thinking_only_blocks(status or summary)

    if settings.compact_responses:
        # Compact: thinking + one-line status + tiny stage strip.
        stage_list = _normalize_stages(stages, status)
        lines = _stage_lines(stage_list, active_index=active_index)
        blocks: list[dict[str, Any]] = [thinking(status)] if show_thinking else []
        blocks.append(paragraph(str(status or summary)[:160]))
        if lines:
            # Keep it short: only the active + last done stage.
            compact_lines = [l for l in lines if l.startswith((_STAGE_ACTIVE, _STAGE_DONE))][-3:]
            blocks.append(paragraph(" · ".join(compact_lines)[:280]))
        return blocks

    return plan_stages_blocks(
        summary,
        stages,
        status,
        phase=phase,
        active_index=active_index,
        show_thinking=show_thinking,
    )


def rich_message(blocks: list[dict[str, Any]]) -> dict[str, Any]:
    return {"blocks": blocks}



def rich_message_button(
    text: str,
    *,
    callback_data: str | None = None,
    url: str | None = None,
    web_app_url: str | None = None,
    login_url: str | None = None,
    copy_text: str | None = None,
    switch_inline_query: str | None = None,
    switch_inline_query_current_chat: str | None = None,
    style: str | None = None,
    disabled: bool = False,
) -> dict[str, Any]:
    """Bot API 10.3 RichMessageButton — used inside buttons blocks and RichTextButton.

    Exactly one action field (besides text/style) must be set.
    Styles: primary | success | danger | link (link only with callback_data).
    """
    button: dict[str, Any] = {"text": str(text)[:64]}
    actions = 0
    if callback_data is not None:
        button["callback_data"] = str(callback_data)[:64]
        actions += 1
    if url is not None:
        button["url"] = str(url)[:2048]
        actions += 1
    if web_app_url is not None:
        button["web_app"] = {"url": str(web_app_url)[:2048]}
        actions += 1
    if login_url is not None:
        button["login_url"] = {"url": str(login_url)[:2048]}
        actions += 1
    if copy_text is not None:
        button["copy_text"] = {"text": str(copy_text)[:256]}
        actions += 1
    if switch_inline_query is not None:
        button["switch_inline_query"] = str(switch_inline_query)[:256]
        actions += 1
    if switch_inline_query_current_chat is not None:
        button["switch_inline_query_current_chat"] = str(switch_inline_query_current_chat)[:256]
        actions += 1
    if actions == 0:
        button["callback_data"] = "noop"
    if style and getattr(settings, "rich_button_styles", True):
        # "link" style is only valid with callback buttons
        if style == "link" and "callback_data" not in button:
            style = "primary"
        if style in {"danger", "success", "primary", "link"}:
            button["style"] = style
    if disabled:
        button["disabled"] = {}
    return button


def rich_button(
    text: str,
    *,
    callback_data: str | None = None,
    url: str | None = None,
    web_app_url: str | None = None,
    login_url: str | None = None,
    copy_text: str | None = None,
    style: str | None = None,
    disabled: bool = False,
) -> dict[str, Any]:
    """Alias for rich_message_button — works in InlineKeyboardMarkup rows too."""
    return rich_message_button(
        text,
        callback_data=callback_data,
        url=url,
        web_app_url=web_app_url,
        login_url=login_url,
        copy_text=copy_text,
        style=style,
        disabled=disabled,
    )


def rich_text_button(
    text: str,
    *,
    callback_data: str | None = None,
    url: str | None = None,
    web_app_url: str | None = None,
    login_url: str | None = None,
    copy_text: str | None = None,
    style: str | None = None,
    disabled: bool = False,
) -> dict[str, Any]:
    """Bot API 10.3 RichTextButton — inline *text entity* of type ``button``.

    Embed inside paragraph text lists::

        paragraph([
            "Pick one: ",
            rich_text_button("Yes", callback_data="y", style="success"),
            " / ",
            rich_text_button("No", callback_data="n", style="danger"),
        ])
    """
    return {
        "type": "button",
        "button": rich_message_button(
            text,
            callback_data=callback_data,
            url=url,
            web_app_url=web_app_url,
            login_url=login_url,
            copy_text=copy_text,
            style=style,
            disabled=disabled,
        ),
    }


def button_row(*buttons: dict[str, Any]) -> list[dict[str, Any]]:
    return list(buttons)


def poll_option_buttons(options: list[str], *, prefix: str = "pollopt", disabled: bool = False) -> list[dict[str, Any]]:
    """Build a vertical buttons block for AI-suggested poll options (preview / pick)."""
    rows: list[list[dict[str, Any]]] = []
    for index, option in enumerate(options[:10]):
        label = str(option).strip()[:64] or f"Option {index + 1}"
        rows.append([
            rich_message_button(
                label,
                callback_data=f"{prefix}:{index}",
                style="primary" if index == 0 else "success",
                disabled=disabled,
            )
        ])
    return buttons_block(rows) if rows else buttons_block([])


def inline_keyboard(
    rows: list[list[tuple[str, str] | tuple[str, str, str] | dict[str, Any]]],
    *,
    disabled: bool = False,
) -> dict[str, Any]:
    """Build InlineKeyboardMarkup.

    When *disabled* is True (streaming drafts), every button carries Bot API 10.3
    ``disabled: {}`` so clients show the controls but they do nothing until the
    final message enables them.
    """
    keyboard: list[list[dict[str, Any]]] = []
    for row in rows:
        rendered: list[dict[str, Any]] = []
        for entry in row:
            if isinstance(entry, dict):
                button = dict(entry)
            else:
                label, data = entry[0], entry[1]
                button = {"text": label, "callback_data": data}
                if len(entry) > 2 and settings.rich_button_styles:
                    button["style"] = entry[2]
            if disabled:
                button["disabled"] = {}
                # Keep callback_data for visual identity; clients ignore presses while disabled.
            rendered.append(button)
        keyboard.append(rendered)
    return {"inline_keyboard": keyboard}


def confirmation_keyboard(
    action_id: str,
    include_details: bool = True,
    *,
    disabled: bool = False,
) -> dict[str, Any]:
    """Final confirmation card keyboard. Pass disabled=True only for non-final previews."""
    rows: list[list[tuple[str, str] | tuple[str, str, str]]] = [[
        ("Yes, continue", f"confirm:{action_id}:yes", "primary"),
        ("No, cancel", f"confirm:{action_id}:no", "danger"),
    ]]
    if include_details:
        rows.append([("View details", f"confirm:{action_id}:details", "secondary")])
    return inline_keyboard(rows, disabled=disabled)



def _disable_markup(reply_markup: dict[str, Any]) -> dict[str, Any]:
    """Copy inline keyboard markup with every button disabled (streaming-draft safe)."""
    rows = reply_markup.get("inline_keyboard") or []
    disabled_rows: list[list[dict[str, Any]]] = []
    for row in rows:
        disabled_rows.append([
            {**dict(btn), "disabled": {}} if isinstance(btn, dict) else {"text": str(btn), "disabled": {}}
            for btn in (row or [])
        ])
    return {"inline_keyboard": disabled_rows}


class RichClient:
    def __init__(self) -> None:
        self.base = settings.bot_api_base.rstrip("/")
        self.token = settings.bot_token
        self.timeout = httpx.Timeout(60.0, connect=10.0)
        self._draft_ids = itertools.count(1001)
        self._rich_draft_supported: bool | None = None
        self._message_draft_supported: bool | None = None

    def normalize_draft_id(self, draft_id: int | str | None = None) -> int:
        if draft_id is None:
            return next(self._draft_ids)
        if isinstance(draft_id, str):
            return int(hashlib.blake2s(draft_id.encode("utf-8"), digest_size=4).hexdigest(), 16)
        return int(draft_id)

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

    async def send(
        self,
        chat_id: int,
        blocks: list[dict[str, Any]],
        reply_markup: dict[str, Any] | None = None,
        reply_to: int | None = None,
        protect_content: bool = False,
        *,
        receiver_user_id: int | None = None,
        ephemeral: bool = False,
        replace_callback_query_id: str | None = None,
    ) -> dict[str, Any]:
        """Send a rich message. When ephemeral=True (or receiver_user_id set), try Bot API
        ephemeral delivery so only the requester sees the card in groups. Falls back to a
        normal chat message if the local Bot API binary does not support it yet.
        """
        payload: dict[str, Any] = {"chat_id": chat_id, "rich_message": rich_message(blocks), "protect_content": protect_content}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        if reply_to:
            payload["reply_parameters"] = {"message_id": reply_to}

        use_ephemeral = ephemeral or receiver_user_id is not None
        if use_ephemeral and receiver_user_id:
            eph: dict[str, Any] = {"receiver_user_id": int(receiver_user_id)}
            if replace_callback_query_id:
                eph["replace_callback_query_message"] = True
                # Some servers also expect the query id alongside the flag
                eph["callback_query_id"] = str(replace_callback_query_id)
            payload["ephemeral_message_parameters"] = eph
            payload["receiver_user_id"] = int(receiver_user_id)

        async def _try_send(body: dict[str, Any]) -> dict[str, Any]:
            try:
                return await self.call("sendRichMessage", body)
            except Exception:
                html = self._fallback_html(blocks)
                fallback: dict[str, Any] = {
                    "chat_id": chat_id,
                    "text": html,
                    "parse_mode": "HTML",
                    "protect_content": protect_content,
                }
                if reply_markup:
                    fallback["reply_markup"] = reply_markup
                if reply_to:
                    fallback["reply_parameters"] = {"message_id": reply_to}
                if "ephemeral_message_parameters" in body:
                    fallback["ephemeral_message_parameters"] = body["ephemeral_message_parameters"]
                if "receiver_user_id" in body:
                    fallback["receiver_user_id"] = body["receiver_user_id"]
                return await self.call("sendMessage", fallback)

        if use_ephemeral and receiver_user_id:
            try:
                return await _try_send(payload)
            except Exception:
                # Older Bot API: drop ephemeral fields and send a normal confirmation.
                payload.pop("ephemeral_message_parameters", None)
                payload.pop("receiver_user_id", None)
                return await _try_send(payload)
        return await _try_send(payload)

    async def send_confirmation(
        self,
        chat_id: int,
        blocks: list[dict[str, Any]],
        reply_markup: dict[str, Any],
        *,
        requester_id: int,
        chat_type: str | None = None,
        reply_to: int | None = None,
        replace_callback_query_id: str | None = None,
    ) -> dict[str, Any]:
        """Send a confirmation card. In groups/supergroups, prefer ephemeral delivery
        so only the requester sees the Yes/No/Details buttons when the feature is on.
        """
        ephemeral = bool(settings.enable_ephemeral_confirmations) and (chat_type in {"group", "supergroup"})
        return await self.send(
            chat_id,
            blocks,
            reply_markup=reply_markup,
            reply_to=reply_to,
            receiver_user_id=requester_id if ephemeral else None,
            ephemeral=ephemeral,
            replace_callback_query_id=replace_callback_query_id,
        )

    async def message_draft(self, chat_id: int, text: str, draft_id: int | str | None = None, can_stop: bool = True) -> bool:
        """Bot API 10.3 sendMessageDraft — lightweight text draft fallback."""
        if not settings.enable_message_drafts:
            return False
        normalized_id = self.normalize_draft_id(draft_id)
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "draft_id": normalized_id,
            "text": str(text)[:4090],
            "can_stop": bool(can_stop and getattr(settings, "draft_can_stop", True)),
            "keep_on_stop": bool(getattr(settings, "draft_keep_on_stop", True)),
        }
        try:
            await self.call("sendMessageDraft", payload)
            self._message_draft_supported = True
            return True
        except Exception:
            self._message_draft_supported = False
            return False

    async def rich_draft(
        self,
        chat_id: int,
        blocks: list[dict[str, Any]],
        draft_id: int | str | None = None,
        can_stop: bool = True,
        *,
        reply_markup: dict[str, Any] | None = None,
    ) -> bool:
        """Stream a partial rich message (sendRichMessageDraft).

        While streaming, any buttons are forced *disabled* (Bot API 10.3).
        The final sendRichMessage enables interactive controls.
        """
        normalized_id = self.normalize_draft_id(draft_id)
        keep = bool(getattr(settings, "draft_keep_on_stop", True))
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "draft_id": normalized_id,
            "rich_message": rich_message(blocks),
            "can_stop": bool(can_stop and getattr(settings, "draft_can_stop", True)),
            "keep_on_stop": keep,
        }
        if reply_markup and isinstance(reply_markup.get("inline_keyboard"), list):
            payload["reply_markup"] = _disable_markup(reply_markup)
        try:
            await self.call("sendRichMessageDraft", payload)
            self._rich_draft_supported = True
            return True
        except Exception:
            self._rich_draft_supported = False
            return False

    async def draft(self, chat_id: int, blocks: list[dict[str, Any]], draft_id: int | str | None = None, can_stop: bool = True) -> bool:
        """Try sendRichMessageDraft, then sendMessageDraft, without posting a final message."""
        if await self.rich_draft(chat_id, blocks, draft_id=draft_id, can_stop=can_stop):
            return True
        text = self._fallback_html(blocks)
        return await self.message_draft(chat_id, text, draft_id=draft_id, can_stop=can_stop)

    async def thinking_only(self, chat_id: int, status: str = "Thinking…", draft_id: int | str | None = None) -> bool:
        """Show only the tg-thinking animation block with a short public status."""
        if not settings.enable_ai_thinking_indicator and not settings.rich_live_previews:
            return False
        return await self.draft(chat_id, thinking_only_blocks(status), draft_id=draft_id, can_stop=True)

    async def clear_draft(self, chat_id: int, draft_id: int | str) -> bool:
        """Dismiss the live preview draft so only the final message remains in chat."""
        normalized_id = self.normalize_draft_id(draft_id)
        try:
            await self.call("sendRichMessageDraft", {
                "chat_id": chat_id,
                "draft_id": normalized_id,
                "rich_message": rich_message([]),
                "can_stop": False,
                "keep_on_stop": False,
            })
            return True
        except Exception:
            pass
        try:
            await self.call("sendMessageDraft", {
                "chat_id": chat_id,
                "draft_id": normalized_id,
                "text": "",
                "can_stop": False,
                "keep_on_stop": False,
            })
            return True
        except Exception:
            return False

    async def thinking_preview(self, chat_id: int, status: str, summary: str = "Working on your request.", draft_id: int | str | None = None) -> bool:
        """Show a professional AI-thinking indicator without exposing private reasoning."""
        if settings.compact_responses:
            return await self.thinking_only(chat_id, status or summary, draft_id=draft_id)
        if not settings.enable_ai_thinking_indicator:
            return await self.status_draft(chat_id, summary, status, draft_id=draft_id)
        return await self.draft(chat_id, thinking_blocks(summary, status), draft_id=draft_id, can_stop=True)

    async def status_draft(
        self,
        chat_id: int,
        summary: str,
        status: str,
        stages: list[str] | None = None,
        draft_id: int | str | None = None,
        show_thinking: bool = False,
        *,
        phase: str = "working",
        active_index: int | None = None,
    ) -> bool:
        blocks = live_activity_blocks(
            summary,
            stages or [status],
            status,
            show_thinking=show_thinking,
            phase=phase,
            active_index=active_index,
        )
        return await self.draft(chat_id, blocks, draft_id=draft_id, can_stop=True)

    async def preview(
        self,
        chat_id: int,
        summary: str,
        stages: list[str],
        draft_id: int | str | None = None,
        status: str = "Working on your request.",
        *,
        phase: str = "working",
        active_index: int | None = None,
    ) -> bool:
        """Send an optional live draft with real progressive UI stages — no chat spam."""
        if not settings.rich_live_previews:
            return False
        show_thinking = settings.enable_ai_thinking_indicator
        return await self.status_draft(
            chat_id,
            summary,
            status,
            stages=stages,
            draft_id=draft_id,
            show_thinking=show_thinking,
            phase=phase,
            active_index=active_index,
        )

    async def plan_preview(
        self,
        chat_id: int,
        summary: str,
        stages: list[str],
        status: str = "Building plan…",
        draft_id: int | str | None = None,
        active_index: int | None = None,
    ) -> bool:
        """Show the planning phase UI with thinking animation + stage checklist."""
        return await self.preview(
            chat_id,
            summary,
            stages,
            draft_id=draft_id,
            status=status,
            phase="plan",
            active_index=active_index if active_index is not None else 0,
        )

    async def work_preview(
        self,
        chat_id: int,
        summary: str,
        stages: list[str],
        status: str = "Executing…",
        draft_id: int | str | None = None,
        active_index: int | None = None,
    ) -> bool:
        """Show the working/execution phase UI with thinking animation + stage checklist."""
        return await self.preview(
            chat_id,
            summary,
            stages,
            draft_id=draft_id,
            status=status,
            phase="working",
            active_index=active_index,
        )

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
            elif kind in {"blockquote", "expandable_blockquote"}:
                if block.get("blocks"):
                    inner = "\n".join(self._plain(b.get("text", "")) for b in block.get("blocks", []) if isinstance(b, dict))
                else:
                    inner = self._plain(block.get("text", ""))
                parts.append(f"<blockquote>{self._escape(inner)}</blockquote>")
            elif kind == "document":
                name = self._plain(block.get("file_name") or block.get("file_id") or block.get("url") or "document")
                cap = self._plain(block.get("caption", ""))
                parts.append(f"📎 {self._escape(name)}" + (f" — {self._escape(cap)}" if cap else ""))
            elif kind == "buttons":
                parts.append("<i>[actions available in the final message]</i>")
            elif kind == "button":
                btn = block.get("button") or {}
                label = self._plain((btn or {}).get("text", "btn"))
                parts.append("[" + self._escape(label) + "]")
            elif kind == "thinking":
                status = self._plain(block.get("status") or "Thinking…")
                # HTML-mode approximation of the native tg-thinking indicator
                parts.append(f'<tg-thinking></tg-thinking> <i>{self._escape(status)}</i>')
            elif kind == "list":
                items = block.get("items") or []
                for item in items:
                    label = item.get("label") or ""
                    inner_blocks = item.get("blocks") or []
                    inner = " ".join(self._plain(b.get("text", "")) for b in inner_blocks if isinstance(b, dict))
                    line = f"{label} {inner}".strip() if label else inner
                    if line:
                        parts.append(self._escape(line))
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
