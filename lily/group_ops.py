"""Reliable group management helpers for Lily.

Centralizes ban/kick/mute/title/invite logic with clear public errors,
self-protection, and audit-friendly results.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from telegram import ChatPermissions
from telegram.error import BadRequest, Forbidden, TelegramError


class GroupOpsError(ValueError):
    """User-facing group management error."""


def _public_tg_error(exc: BaseException) -> str:
    text = str(exc) or type(exc).__name__
    low = text.lower()
    if "not enough rights" in low or "not enough privileges" in low:
        return "Lily needs administrator rights with the matching permission for that action."
    if "user is an administrator" in low or "can't restrict chat owner" in low:
        return "Lily cannot moderate the group owner or another administrator that way."
    if "user_not_participant" in low or "user not found" in low:
        return "That user is not a member of this chat (or the ID is invalid)."
    if "chat_admin_required" in low:
        return "Lily must be a group administrator to do that."
    if "chat not found" in low:
        return "Lily cannot access that chat."
    return text[:300]


async def resolve_member_label(bot, chat_id: int, user_id: int) -> str:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        user = member.user
        if user.username:
            return f"@{user.username} ({user_id})"
        name = " ".join(p for p in [user.first_name, user.last_name] if p).strip() or str(user_id)
        return f"{name} ({user_id})"
    except Exception:
        return str(user_id)


async def guard_moderation_target(bot, chat_id: int, actor_id: int, target_id: int, bot_id: int | None = None) -> None:
    if target_id == actor_id:
        raise GroupOpsError("You cannot run that moderation action on yourself.")
    if bot_id and target_id == bot_id:
        raise GroupOpsError("Lily cannot moderate itself.")
    try:
        member = await bot.get_chat_member(chat_id, target_id)
        if member.status in {"creator"}:
            raise GroupOpsError("Lily cannot moderate the group owner.")
        if member.status == "administrator":
            # Allow demote path separately; ban/mute of admins usually fails.
            pass
    except GroupOpsError:
        raise
    except Exception:
        # Target may already be banned / not in chat — still allow unban attempts.
        pass


async def ban_member(bot, chat_id: int, target_id: int, *, revoke_messages: bool = True, until: datetime | None = None) -> None:
    try:
        kwargs: dict[str, Any] = {"chat_id": chat_id, "user_id": target_id, "revoke_messages": revoke_messages}
        if until is not None:
            kwargs["until_date"] = until
        await bot.ban_chat_member(**kwargs)
    except (BadRequest, Forbidden, TelegramError) as exc:
        raise GroupOpsError(_public_tg_error(exc)) from None


async def unban_member(bot, chat_id: int, target_id: int) -> None:
    try:
        await bot.unban_chat_member(chat_id, target_id, only_if_banned=True)
    except (BadRequest, Forbidden, TelegramError) as exc:
        raise GroupOpsError(_public_tg_error(exc)) from None


async def kick_member(bot, chat_id: int, target_id: int) -> None:
    await ban_member(bot, chat_id, target_id, revoke_messages=False)
    await unban_member(bot, chat_id, target_id)


async def mute_member(bot, chat_id: int, target_id: int, seconds: int) -> datetime:
    seconds = max(60, min(int(seconds), 2_419_200))
    until = datetime.now(timezone.utc) + timedelta(seconds=seconds)
    try:
        await bot.restrict_chat_member(
            chat_id,
            target_id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until,
        )
    except (BadRequest, Forbidden, TelegramError) as exc:
        raise GroupOpsError(_public_tg_error(exc)) from None
    return until


async def unmute_member(bot, chat_id: int, target_id: int, permissions: ChatPermissions) -> None:
    try:
        await bot.restrict_chat_member(chat_id, target_id, permissions=permissions)
    except (BadRequest, Forbidden, TelegramError) as exc:
        raise GroupOpsError(_public_tg_error(exc)) from None


async def set_title(bot, chat_id: int, title: str) -> str:
    title = (title or "").strip()[:128]
    if len(title) < 1:
        raise GroupOpsError("Provide a non-empty group title (1–128 characters).")
    try:
        await bot.set_chat_title(chat_id, title)
    except (BadRequest, Forbidden, TelegramError) as exc:
        raise GroupOpsError(_public_tg_error(exc)) from None
    return title


async def set_description(bot, chat_id: int, description: str) -> None:
    description = (description or "").strip()[:255]
    try:
        await bot.set_chat_description(chat_id, description)
    except (BadRequest, Forbidden, TelegramError) as exc:
        raise GroupOpsError(_public_tg_error(exc)) from None


async def create_invite(
    bot,
    chat_id: int,
    *,
    name: str = "",
    member_limit: int | None = None,
    expire_hours: int | None = None,
    creates_join_request: bool = False,
) -> Any:
    payload: dict[str, Any] = {"chat_id": chat_id, "creates_join_request": bool(creates_join_request)}
    if name:
        payload["name"] = name[:32]
    if member_limit:
        payload["member_limit"] = max(1, min(int(member_limit), 99_999))
    if expire_hours:
        payload["expire_date"] = datetime.now(timezone.utc) + timedelta(hours=max(1, min(int(expire_hours), 168)))
    try:
        return await bot.create_chat_invite_link(**payload)
    except (BadRequest, Forbidden, TelegramError) as exc:
        raise GroupOpsError(_public_tg_error(exc)) from None


def format_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        hours = seconds // 3600
        mins = (seconds % 3600) // 60
        return f"{hours}h{mins}m" if mins else f"{hours}h"
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    return f"{days}d{hours}h" if hours else f"{days}d"
