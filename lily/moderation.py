from __future__ import annotations

import re
import time
from collections import defaultdict, deque
from typing import Any

from telegram import ChatPermissions, Update

from .config import settings
from .db import db
from .rich import blockquote, heading, paragraph, rich


URL_RE = re.compile(r"https?://\S+|t\.me/\S+", re.IGNORECASE)


class ModerationService:
    def __init__(self) -> None:
        self.recent_messages: dict[tuple[int, int], deque[float]] = defaultdict(lambda: deque(maxlen=20))

    async def is_admin(self, bot, chat_id: int, user_id: int) -> bool:
        if user_id in settings.admin_user_ids:
            return True
        try:
            member = await bot.get_chat_member(chat_id, user_id)
            return member.status in {"administrator", "creator"}
        except Exception:
            return False

    def content_type(self, message) -> str | None:
        if message.document:
            return "documents"
        if message.photo:
            return "photos"
        if message.video:
            return "videos"
        if message.animation:
            return "animations"
        if message.audio or message.voice:
            return "audio"
        if message.sticker:
            return "stickers"
        if message.contact:
            return "contacts"
        if message.location or message.venue:
            return "locations"
        if message.poll:
            return "polls"
        return None

    async def inspect(self, update: Update) -> bool:
        """Return True when normal AI handling should continue."""
        message = update.effective_message
        chat = update.effective_chat
        user = update.effective_user
        if not message or not chat or not user or chat.type not in {"group", "supergroup"}:
            return True
        if await self.is_admin(update.get_bot(), chat.id, user.id):
            return True

        locks = await db.get_locks(chat.id)
        kind = self.content_type(message)
        text = (message.text or message.caption or "").strip()
        blocked = bool(kind and locks.get(kind, False)) or (locks.get("links", False) and bool(URL_RE.search(text)))
        if blocked:
            try:
                await update.get_bot().delete_message(chat.id, message.message_id)
                await db.audit(chat.id, user.id, "locked_content_deleted", {"content_type": kind or "links"})
            except Exception:
                pass
            return False

        for item in await db.list_filters(chat.id):
            if item["trigger"].lower() not in text.lower():
                continue
            try:
                if item["delete_message"]:
                    await update.get_bot().delete_message(chat.id, message.message_id)
                warning_count = 0
                if item["warn"]:
                    warning_count = await db.add_warning(chat.id, user.id, f"Filter matched: {item['trigger']}")
                if item["response"]:
                    await rich.send(chat.id, [paragraph(item["response"])], reply_to=message.message_id)
                await db.audit(chat.id, user.id, "filter_triggered", {"trigger": item["trigger"], "warnings": warning_count})
            except Exception:
                pass
            return False

        now = time.monotonic()
        bucket = self.recent_messages[(chat.id, user.id)]
        bucket.append(now)
        while bucket and now - bucket[0] > 10:
            bucket.popleft()
        if len(bucket) >= 10:
            try:
                await update.get_bot().restrict_chat_member(chat.id, user.id, permissions=ChatPermissions(can_send_messages=False), until_date=int(time.time()) + 60)
                await db.audit(chat.id, user.id, "flood_mute", {"messages_in_10_seconds": len(bucket)})
                bucket.clear()
            except Exception:
                pass
            return False
        return True

    async def welcome(self, update: Update) -> None:
        message = update.effective_message
        if not message or not message.new_chat_members:
            return
        settings_for_chat = await db.get_chat_settings(update.effective_chat.id, update.effective_chat.title or "")
        if not settings_for_chat.get("welcome_enabled", True):
            return
        for member in message.new_chat_members[:10]:
            name = member.full_name.replace("<", "&lt;").replace(">", "&gt;")
            template = settings_for_chat.get("welcome_text") or "Welcome {user} to {group}! Please read the rules."
            text = template.replace("{user}", name).replace("{group}", update.effective_chat.title or "this group")
            await rich.send(update.effective_chat.id, [heading("Welcome", 2), paragraph(text), blockquote(settings_for_chat.get("rules") or "Be respectful and avoid spam.", "Group rules")])


moderation = ModerationService()
