from __future__ import annotations

import re
import time
from collections import defaultdict, deque
from urllib.parse import urlparse

from telegram import ChatPermissions, Update

from .config import settings
from .db import db
from .rich import blockquote, heading, inline_keyboard, paragraph, rich


URL_RE = re.compile(r"https?://\S+|t\.me/\S+", re.IGNORECASE)
INVITE_RE = re.compile(r"(?:t\.me/(?:joinchat/|\+)|telegram\.me/(?:joinchat/|\+))", re.IGNORECASE)
SUSPICIOUS_RE = re.compile(r"(?:guaranteed profit|free crypto|double your money|dm me for|wallet connect|seed phrase)", re.IGNORECASE)


class ModerationService:
    def __init__(self) -> None:
        self.recent_messages: dict[tuple[int, int], deque[float]] = defaultdict(lambda: deque(maxlen=20))
        self.recent_texts: dict[tuple[int, int], deque[tuple[float, str]]] = defaultdict(lambda: deque(maxlen=12))
        self.recent_media: dict[tuple[int, int], deque[float]] = defaultdict(lambda: deque(maxlen=12))

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

    @staticmethod
    def _domains(text: str) -> set[str]:
        found = set()
        for value in URL_RE.findall(text):
            parsed = urlparse(value if value.startswith("http") else f"https://{value}")
            if parsed.hostname:
                found.add(parsed.hostname.lower())
        return found

    async def _delete(self, update: Update, event: str, detail: dict) -> None:
        message, chat, user = update.effective_message, update.effective_chat, update.effective_user
        if not message or not chat:
            return
        try:
            await update.get_bot().delete_message(chat.id, message.message_id)
            await db.audit(chat.id, user.id if user else None, event, detail)
        except Exception:
            pass

    async def inspect(self, update: Update) -> bool:
        """Return True when normal AI handling should continue."""
        message = update.effective_message
        chat = update.effective_chat
        user = update.effective_user
        if not message or not chat or not user or chat.type not in {"group", "supergroup"}:
            return True
        if await self.is_admin(update.get_bot(), chat.id, user.id):
            return True

        chat_settings = await db.get_chat_settings(chat.id, chat.title or "")
        controls = chat_settings.get("controls", {}) if isinstance(chat_settings.get("controls"), dict) else {}
        if controls.get("trusted_members", False) and await db.is_trusted_member(chat.id, user.id):
            return True

        locks = await db.get_locks(chat.id)
        kind = self.content_type(message)
        text = (message.text or message.caption or "").strip()
        forwarded = bool(getattr(message, "forward_origin", None) or getattr(message, "forward_from", None))
        joined_at = await db.member_joined_at(chat.id, user.id)
        cooldown = int(chat_settings.get("new_member_cooldown_seconds", 600))
        within_new_member_window = joined_at is not None and time.time() - joined_at < cooldown
        if within_new_member_window and controls.get("new_member_cooldown", False) and (kind or URL_RE.search(text)):
            await self._delete(update, "new_member_cooldown_deleted", {"content_type": kind or "link", "cooldown_seconds": cooldown})
            return False
        if within_new_member_window and controls.get("new_member_limits", False) and (forwarded or URL_RE.search(text)):
            await self._delete(update, "new_member_limit_deleted", {"forwarded": forwarded, "has_link": bool(URL_RE.search(text))})
            return False
        blocked = (
            bool(kind and (locks.get(kind, False) or controls.get(kind, False)))
            or ((locks.get("links", False) or controls.get("links", False)) and bool(URL_RE.search(text)))
            or (controls.get("forwards", False) and forwarded)
        )
        if blocked:
            await self._delete(update, "locked_content_deleted", {"content_type": kind or "links", "forwarded": forwarded})
            return False

        if controls.get("domain_blocklist", False) and text:
            domains = self._domains(text)
            blocked_domains = await db.list_blocked_domains(chat.id)
            if any(domain == blocked_domain or domain.endswith(f".{blocked_domain}") for domain in domains for blocked_domain in blocked_domains):
                await self._delete(update, "blocked_domain_deleted", {"domains": sorted(domains)})
                return False

        letters = [character for character in text if character.isalpha()]
        if controls.get("caps", False) and len(letters) >= 10 and sum(character.isupper() for character in letters) / len(letters) >= 0.75:
            await self._delete(update, "caps_spam_deleted", {"letters": len(letters)})
            return False

        if controls.get("mention_spam", False) and text.count("@") >= 6:
            await self._delete(update, "mention_spam_deleted", {"mentions": text.count("@")})
            return False

        if controls.get("invite_links", False) and INVITE_RE.search(text):
            await self._delete(update, "invite_link_deleted", {})
            return False

        emoji_count = sum(1 for character in text if ord(character) >= 0x1F000)
        if controls.get("emoji_spam", False) and emoji_count >= 12:
            await self._delete(update, "emoji_spam_deleted", {"emoji_count": emoji_count})
            return False

        if controls.get("suspicious_text", False) and SUSPICIOUS_RE.search(text):
            report_id = await db.create_report(chat.id, 0, user.id, "Automatic suspicious-text flag")
            await db.audit(chat.id, user.id, "suspicious_text_flagged", {"report_id": report_id})
            return False

        if controls.get("duplicate_text", False) and text:
            now = time.monotonic()
            text_bucket = self.recent_texts[(chat.id, user.id)]
            while text_bucket and now - text_bucket[0][0] > 90:
                text_bucket.popleft()
            if any(previous == text.lower() for _, previous in text_bucket):
                await self._delete(update, "duplicate_text_deleted", {})
                return False
            text_bucket.append((now, text.lower()[:1000]))

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
        if controls.get("flood", True) and len(bucket) >= 10:
            try:
                await update.get_bot().restrict_chat_member(chat.id, user.id, permissions=ChatPermissions(can_send_messages=False), until_date=int(time.time()) + 60)
                await db.audit(chat.id, user.id, "flood_mute", {"messages_in_10_seconds": len(bucket)})
                bucket.clear()
            except Exception:
                pass
            return False
        if kind:
            media_bucket = self.recent_media[(chat.id, user.id)]
            media_bucket.append(now)
            while media_bucket and now - media_bucket[0] > 30:
                media_bucket.popleft()
            if controls.get("media_spam", False) and len(media_bucket) >= 6:
                await self._delete(update, "media_spam_deleted", {"media_in_30_seconds": len(media_bucket)})
                return False
        return True

    async def welcome(self, update: Update) -> None:
        message = update.effective_message
        if not message or not message.new_chat_members:
            return
        settings_for_chat = await db.get_chat_settings(update.effective_chat.id, update.effective_chat.title or "")
        if not settings_for_chat.get("welcome_enabled", True) or not settings_for_chat.get("controls", {}).get("welcome", True):
            return
        for member in message.new_chat_members[:10]:
            name = member.full_name.replace("<", "&lt;").replace(">", "&gt;")
            requires_verification = bool(settings_for_chat.get("controls", {}).get("verification", False))
            await db.record_member_join(update.effective_chat.id, member.id, requires_verification)
            template = settings_for_chat.get("welcome_text") or "Welcome {user} to {group}! Please read the rules."
            text = template.replace("{user}", name).replace("{group}", update.effective_chat.title or "this group")
            markup = None
            if requires_verification:
                try:
                    await update.get_bot().restrict_chat_member(update.effective_chat.id, member.id, permissions=ChatPermissions(can_send_messages=False))
                except Exception:
                    pass
                markup = inline_keyboard([[('Verify membership', f'verify:{member.id}')]])
            blocks = [heading("Welcome", 2), paragraph(text), blockquote(settings_for_chat.get("rules") or "Be respectful and avoid spam.", "Group rules")]
            if requires_verification:
                blocks.append(paragraph(str(settings_for_chat.get("verification_prompt") or "Tap the button below to confirm that you will follow this group’s rules.")))
            await rich.send(update.effective_chat.id, blocks, reply_markup=markup)

    async def goodbye(self, update: Update) -> None:
        message = update.effective_message
        if not message or not message.left_chat_member or not update.effective_chat:
            return
        settings_for_chat = await db.get_chat_settings(update.effective_chat.id, update.effective_chat.title or "")
        if not settings_for_chat.get("goodbye_enabled", False) or not settings_for_chat.get("controls", {}).get("goodbye", False):
            return
        member = message.left_chat_member
        name = member.full_name.replace("<", "&lt;").replace(">", "&gt;")
        template = settings_for_chat.get("goodbye_text") or "{user} left {group}."
        text = template.replace("{user}", name).replace("{group}", update.effective_chat.title or "this group")
        await rich.send(update.effective_chat.id, [heading("Goodbye", 3), paragraph(text)])


moderation = ModerationService()
