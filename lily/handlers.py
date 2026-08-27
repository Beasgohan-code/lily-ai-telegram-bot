from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Any

from telegram import ChatPermissions, Update
from telegram.ext import Application, CallbackQueryHandler, ContextTypes, MessageHandler, filters

from .agent import Plan, ai
from .config import settings
from .db import db
from .rich import blockquote, bold, code, confirmation_keyboard, custom_emoji, details, divider, heading, inline_keyboard, list_block, paragraph, preformatted, rich, table, thinking
from .tools import LilyTools, ToolContext, safe_filename, source_file_from_message
from .postbot import post_service
from .moderation import moderation
from .plugin_manager import plugin_manager
from .pagination import pagination
from .queue_manager import encoding_queue
from .web_media import stream_links, web_search
from .messaging import send_long_rich
from .media_generation import media_generation
from .group_controls import GROUP_CONTROL_MAP, control_summary
from .bot_factory import BotFactoryError, ManagedBotFactory
from .knowledge_library import catalog as knowledge_catalog


tools = LilyTools(db)
bot_factory = ManagedBotFactory(db)

ADMIN_ACTIONS = {
    "ban_user", "unban_user", "kick_user", "mute_user", "unmute_user", "restrict_user", "unrestrict_user", "demote_user", "promote_user", "delete_message", "purge_messages", "report_user", "pin_message", "unpin_message",
    "set_settings", "create_skill", "set_group_rules", "start_channel_post", "publish_channel_post", "delete_last_post",
    "warn_user", "add_filter", "remove_filter", "set_lock", "save_note", "list_notes", "search_posts", "show_warnings", "set_auto_rename", "stream_link",
    "configure_group_control", "group_controls_status", "group_diagnostics", "configure_warning_escalation", "media_info", "export_audit", "trusted_member", "block_domain", "list_domains", "clear_warnings", "set_admin_title", "approve_join_request", "decline_join_request", "list_reports", "resolve_report", "audit_log", "set_welcome", "set_goodbye", "set_verification", "set_group_rules", "show_group_rules", "add_case_note", "list_case_notes", "create_poll",
    "list_managed_projects", "register_managed_project", "provision_managed_project", "project_env_schema", "project_run_profiles",
    "track_series", "list_tracked_series", "update_tracked_series",
    "download_chapter",
    "tool_capabilities",
    "show_operating_skills",
}


def _plan_dict(plan: Plan) -> dict[str, Any]:
    return asdict(plan)


def _reply_context(update: Update) -> dict[str, Any]:
    message = update.effective_message
    reply = message.reply_to_message if message else None
    result: dict[str, Any] = {"chat_type": update.effective_chat.type if update.effective_chat else "", "reply": {}}
    if message and message.text:
        found = re.search(r"(?<!\d)(-?\d{5,})(?!\d)", message.text)
        if found:
            result["target_user_id"] = int(found.group(1))
    if reply:
        result["reply"] = {"message_id": reply.message_id}
        if reply.from_user:
            result["reply"]["user_id"] = reply.from_user.id
            result["reply"]["user_name"] = reply.from_user.full_name
        file_info = None
        if reply.document:
            file_info = {"file_name": reply.document.file_name or "file.bin", "file_size": reply.document.file_size or 0, "file_id": reply.document.file_id}
        elif reply.video:
            file_info = {"file_name": f"video_{reply.video.file_unique_id}.mp4", "file_size": reply.video.file_size or 0, "file_id": reply.video.file_id}
        elif reply.audio:
            file_info = {"file_name": reply.audio.file_name or "audio.mp3", "file_size": reply.audio.file_size or 0, "file_id": reply.audio.file_id}
        if file_info:
            result["reply"].update(file_info)
    if message:
        result["message_to_act_on"] = message.message_id
    return result


async def is_admin(update: Update) -> bool:
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        return False
    if user.id in settings.admin_user_ids or chat.type == "private":
        return True
    try:
        member = await update.get_bot().get_chat_member(chat.id, user.id)
        return member.status in {"administrator", "creator"}
    except Exception:
        return False


def addressed_to_lily(update: Update, bot_username: str | None) -> bool:
    message = update.effective_message
    chat = update.effective_chat
    if not message or chat is None or chat.type == "private":
        return True
    text = message.text or message.caption or ""
    if message.reply_to_message and message.reply_to_message.from_user and message.reply_to_message.from_user.id == update.get_bot().id:
        return True
    if bot_username:
        username = bot_username.lstrip("@").lower()
        if re.search(rf"(?<![A-Za-z0-9_])@{re.escape(username)}(?![A-Za-z0-9_])", text, re.IGNORECASE):
            return True
    return text.lower().lstrip().startswith(("lily ", "lily,", "lily:", "lily!"))


async def progress_message(update: Update, text_value: str) -> None:
    chat = update.effective_chat
    if not chat:
        return
    blocks = [heading("Lily is working", 3)]
    if settings.custom_emoji_id:
        blocks.append(paragraph([custom_emoji(settings.custom_emoji_id, "✦"), " Agent activity"] ))
    blocks.extend([thinking(), paragraph(text_value)])
    await rich.send(chat.id, blocks, reply_to=update.effective_message.message_id if update.effective_message else None)


def normal_chat_permissions() -> ChatPermissions:
    return ChatPermissions(can_send_messages=True, can_send_audios=True, can_send_documents=True, can_send_photos=True, can_send_videos=True, can_send_video_notes=True, can_send_voice_notes=True, can_send_polls=True, can_send_other_messages=True, can_add_web_page_previews=True)


async def send_error(update: Update, message: str) -> None:
    if update.effective_chat:
        await rich.send(update.effective_chat.id, [heading("I couldn’t complete that", 3), paragraph(message)], reply_to=update.effective_message.message_id if update.effective_message else None)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await rich.send(update.effective_chat.id, [heading("Meet Lily", 1), paragraph("I’m your AI-native Telegram assistant. Talk to me naturally: ask questions, create files, process media, manage a group, or describe a skill you want to add."), blockquote("I can explain before I act, and I ask for confirmation before risky actions.", "Lily")], reply_to=update.effective_message.message_id)


async def help_message(update: Update) -> None:
    await rich.send(update.effective_chat.id, [heading("What Lily can do", 1), paragraph("No command memorization is required. Mention me in a group or speak to me privately."), table([
        ["Area", "Examples"],
        ["Moderation", "Ban, kick, mute, warn, delete, pin, filters"],
        ["Files", "Create PDF/Markdown/JSON/CSV/HTML, rename, compress"],
        ["Media", "Encode video/audio with FFmpeg"],
        ["AI", "Answer, summarize, translate, remember, extract tasks"],
        ["Automation", "Reminders, trigger skills, recurring workflows"],
    ]), details("Safety rules", [paragraph("Lily checks permissions before group actions, uses confirmation cards for risky work, applies daily and monthly quotas, and never executes arbitrary operating-system commands from chat.")])])


async def usage_message(update: Update) -> None:
    values = await db.usage_summary(update.effective_user.id, update.effective_chat.id)
    settings_for_chat = await db.get_chat_settings(update.effective_chat.id)
    await rich.send(update.effective_chat.id, [heading("Lily usage", 2), table([
        ["Quota", "Today", "This month"],
        ["Requests", f"{values['user_daily_requests']} / {settings_for_chat['daily_request_limit']}", f"{values['user_monthly_requests']} / {settings_for_chat['monthly_request_limit']}"],
        ["File bytes", f"{values['user_daily_bytes']} / {settings_for_chat['daily_bytes_limit']}", f"{values['user_monthly_bytes']} / {settings_for_chat['monthly_bytes_limit']}"],
    ]), paragraph("Limits are tracked separately for each user and group. Large-file jobs consume byte quota based on the source file size.")])


async def list_skills_message(update: Update) -> None:
    skills = await db.list_skills(update.effective_chat.id)
    if not skills:
        await rich.send(update.effective_chat.id, [heading("Skills", 2), paragraph("No custom skills have been created for this chat yet.")])
        return
    rows = [["Skill", "Trigger", "Action"]]
    for skill in skills:
        rows.append([skill["name"], json.dumps(skill["trigger"], ensure_ascii=False)[:80], json.dumps(skill["action"], ensure_ascii=False)[:100]])
    await rich.send(update.effective_chat.id, [heading("Custom skills", 2), table(rows)])


async def skill_trigger(update: Update) -> Plan | None:
    message = update.effective_message
    text_value = (message.text or message.caption or "").lower() if message else ""
    if not text_value:
        return None
    for skill in await db.list_skills(update.effective_chat.id):
        trigger = skill["trigger"]
        keywords = trigger.get("keywords", []) if isinstance(trigger, dict) else []
        contains = trigger.get("contains", []) if isinstance(trigger, dict) else []
        matched = any(str(keyword).lower() in text_value for keyword in keywords + contains)
        if not matched:
            continue
        action = skill["action"] if isinstance(skill["action"], dict) else {}
        action_name = action.get("action") or action.get("type") or "none"
        args = action.get("args") if isinstance(action.get("args"), dict) else action
        return Plan(intent=skill["name"], summary=f"Run skill: {skill['name']}", action=action_name, risk="dangerous" if skill["confirmation"] != "never" else "safe", requires_confirmation=skill["confirmation"] != "never", args=args)
    return None


async def begin_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE, post_type: str = "anime_announcement") -> None:
    if not await is_admin(update):
        await send_error(update, "Only a group/channel admin can prepare a channel post.")
        return
    context.user_data["post_state"] = {"stage": "await_type", "post_type": post_type}
    await rich.send(update.effective_chat.id, [heading("Lily Post Studio", 1), paragraph("What kind of post should I create? Say `anime episode announcement`, `custom announcement`, or describe another format."), details("Available formats", [paragraph("Anime episode announcements are filled automatically from public metadata. Custom announcements use the content you provide.")])])


async def handle_post_state(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    state = context.user_data.get("post_state")
    if not state or update.effective_chat.type != "private":
        return False
    value = (update.effective_message.text or "").strip()
    if not value:
        return True
    if state.get("stage") == "await_delete_channel":
        channel_id: int | str = int(value) if re.fullmatch(r"-?\d+", value) else value
        ok, label = await post_service.verify_channel(update.get_bot(), channel_id, update.effective_user.id)
        if not ok:
            await send_error(update, label)
            return True
        context.user_data.pop("post_state", None)
        plan = Plan(intent="delete_last_post", summary=f"Delete Lily’s last tracked post from {label}", action="delete_last_post", risk="dangerous", requires_confirmation=True, args={"channel_id": channel_id})
        await handle_plan(update, context, plan, await db.get_chat_settings(update.effective_chat.id))
        return True
    if state.get("stage") == "await_type":
        low = value.lower()
        state["post_type"] = "anime_announcement" if any(word in low for word in ("anime", "episode", "series")) else "custom_announcement"
        state["stage"] = "await_channel"
        await rich.send(update.effective_chat.id, [heading("Choose the channel", 2), paragraph("Send the numeric channel ID such as `-1001234567890` or the channel @username. Lily must already be an administrator there with permission to post."), paragraph(f"Selected format: {state['post_type'].replace('_', ' ').title()}")])
        return True
    if state.get("stage") == "await_channel":
        channel_id: int | str = int(value) if re.fullmatch(r"-?\d+", value) else value
        ok, label = await post_service.verify_channel(update.get_bot(), channel_id, update.effective_user.id)
        if not ok:
            await send_error(update, label)
            return True
        state.update({"stage": "await_title", "channel_id": channel_id, "channel_label": label})
        await rich.send(update.effective_chat.id, [heading("Channel selected", 2), paragraph(f"I can post to {label}. What should the post be about? For example: `Dragon Ball Super episode 12 announcement`."), paragraph("You can also say `custom post` if you want to provide the exact text yourself.")])
        return True
    if state.get("stage") == "await_title":
        await progress_message(update, "Looking up the title and filling the announcement fields…")
        try:
            if state.get("post_type") == "anime_announcement":
                anime = await post_service.lookup_anime(value)
            else:
                anime = {"title": value, "type": "Announcement", "rating": "N/A", "status": "N/A", "episodes": "N/A", "genres": "N/A", "plot": value}
            state.update({"stage": "preview", "anime": anime})
            blocks = post_service.announcement_blocks(anime, include_buttons=True)
            blocks.append({"type": "buttons", "buttons": [{"text": "Publish draft", "style": "primary", "callback_data": "postpublish"}, {"text": "Cancel", "style": "danger", "callback_data": "postcancel"}], "align": "center"})
            await rich.send(update.effective_chat.id, [heading("Post preview", 1), paragraph(f"Target channel: {state['channel_label']}"), *blocks, blockquote("Check the details before publishing. Lily will ask for one final confirmation.", "Lily")])
        except Exception as exc:
            await send_error(update, str(exc)[:1000])
        return True
    return True


async def execute_plan(update: Update, context: ContextTypes.DEFAULT_TYPE, plan: Plan) -> str:
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    action = plan.action
    if action == "ban_user":
        await update.get_bot().ban_chat_member(chat_id, int(plan.args["user_id"]))
        await db.audit(chat_id, user_id, "ban_user", plan.args)
        return f"User {plan.args['user_id']} was banned."
    if action == "unban_user":
        target = int(plan.args["user_id"])
        await update.get_bot().unban_chat_member(chat_id, target, only_if_banned=True)
        await db.audit(chat_id, user_id, "unban_user", plan.args)
        return f"User {target} was unbanned."
    if action == "demote_user":
        target = int(plan.args["user_id"])
        await update.get_bot().promote_chat_member(chat_id, target, is_anonymous=False, can_manage_chat=False, can_delete_messages=False, can_manage_video_chats=False, can_restrict_members=False, can_promote_members=False, can_change_info=False, can_invite_users=False, can_pin_messages=False)
        await db.audit(chat_id, user_id, "demote_user", plan.args)
        return f"User {target} was demoted."
    if action == "promote_user":
        target = int(plan.args["user_id"])
        await update.get_bot().promote_chat_member(chat_id, target, can_manage_chat=True, can_delete_messages=True, can_manage_video_chats=True, can_restrict_members=True, can_promote_members=False, can_change_info=True, can_invite_users=True, can_pin_messages=True)
        await db.audit(chat_id, user_id, "promote_user", plan.args)
        return f"User {target} was promoted with safe moderator permissions."
    if action == "kick_user":
        target = int(plan.args["user_id"])
        await update.get_bot().ban_chat_member(chat_id, target)
        await update.get_bot().unban_chat_member(chat_id, target, only_if_banned=True)
        await db.audit(chat_id, user_id, "kick_user", plan.args)
        return f"User {target} was removed."
    if action == "mute_user":
        seconds = max(60, min(int(plan.args.get("seconds", 3600)), 2_419_200))
        until = datetime.now(timezone.utc) + timedelta(seconds=seconds)
        await update.get_bot().restrict_chat_member(chat_id, int(plan.args["user_id"]), permissions=ChatPermissions(can_send_messages=False), until_date=until)
        await db.audit(chat_id, user_id, "mute_user", plan.args)
        return f"User {plan.args['user_id']} was muted for {seconds // 60} minutes."
    if action == "unmute_user":
        await update.get_bot().restrict_chat_member(chat_id, int(plan.args["user_id"]), permissions=normal_chat_permissions())
        return f"User {plan.args['user_id']} was unmuted."
    if action == "restrict_user":
        target = int(plan.args["user_id"])
        mode = str(plan.args.get("mode") or "read_only")
        seconds = max(60, min(int(plan.args.get("seconds", 3600)), 2_419_200))
        until = datetime.now(timezone.utc) + timedelta(seconds=seconds)
        permissions = ChatPermissions(can_send_messages=False) if mode == "read_only" else ChatPermissions(can_send_messages=True, can_send_audios=False, can_send_documents=False, can_send_photos=False, can_send_videos=False, can_send_video_notes=False, can_send_voice_notes=False, can_send_polls=False, can_send_other_messages=False, can_add_web_page_previews=False)
        await update.get_bot().restrict_chat_member(chat_id, target, permissions=permissions, until_date=until)
        await db.audit(chat_id, user_id, "restrict_user", {"user_id": target, "mode": mode, "seconds": seconds})
        return f"User {target} was restricted to {mode.replace('_', ' ')} for {seconds // 60} minutes."
    if action == "unrestrict_user":
        target = int(plan.args["user_id"])
        await update.get_bot().restrict_chat_member(chat_id, target, permissions=normal_chat_permissions())
        await db.audit(chat_id, user_id, "unrestrict_user", {"user_id": target})
        return f"Restored normal sending permissions for user {target}."
    if action == "delete_message":
        await update.get_bot().delete_message(chat_id, int(plan.args["message_id"]))
        await db.audit(chat_id, user_id, "delete_message", plan.args)
        return "The message was deleted."
    if action == "purge_messages":
        count = max(1, min(100, int(plan.args.get("count", 10))))
        end_id = update.effective_message.message_id
        deleted = 0
        for message_id in range(end_id, max(0, end_id - count), -1):
            try:
                await update.get_bot().delete_message(chat_id, message_id)
                deleted += 1
            except Exception:
                continue
        await db.audit(chat_id, user_id, "purge_messages", {"count": count, "deleted": deleted})
        return f"Purged {deleted} message(s)."
    if action == "report_user":
        reason = str(plan.args.get("reason") or "Reported by a group member")
        reply_context = _reply_context(update).get("reply", {})
        target = reply_context.get("user_name", "the replied user")
        report_id = await db.create_report(chat_id, user_id, reply_context.get("user_id"), reason)
        await db.audit(chat_id, user_id, "report_user", {"target": target, "reason": reason, "report_id": report_id})
        return f"Report #{report_id} was recorded for {target}. Group admins can review it."
    if action == "pin_message":
        await update.get_bot().pin_chat_message(chat_id, int(plan.args.get("message_id", update.effective_message.message_id)), disable_notification=True)
        return "The message was pinned."
    if action == "unpin_message":
        message_id = int(plan.args.get("message_id") or update.effective_message.message_id)
        await update.get_bot().unpin_chat_message(chat_id, message_id)
        await db.audit(chat_id, user_id, "unpin_message", {"message_id": message_id})
        return "The message was unpinned."
    if action == "set_settings":
        allowed = {"personality", "language", "mention_only", "memory_enabled", "auto_confirm_safe", "welcome_enabled", "welcome_text", "daily_request_limit", "monthly_request_limit", "daily_bytes_limit", "monthly_bytes_limit", "warning_escalation"}
        patch = {key: value for key, value in plan.args.items() if key in allowed}
        if not patch:
            return "Tell me which setting you want to change."
        await db.update_chat_settings(chat_id, patch, update.effective_chat.title or "")
        return "The group settings were updated."
    if action == "configure_group_control":
        key = str(plan.args.get("control") or "").lower().replace(" ", "_")
        control = GROUP_CONTROL_MAP.get(key)
        if not control:
            return "That is not a recognised Lily group control. Ask Lily to show the group controls first."
        enabled = bool(plan.args.get("enabled", True))
        await db.set_control(chat_id, key, enabled, update.effective_chat.title or "")
        if key in {"links", "documents", "photos", "videos", "audio", "animations", "stickers", "polls", "contacts", "locations"}:
            await db.set_lock(chat_id, key, enabled)
        await db.audit(chat_id, user_id, "configure_group_control", {"control": key, "enabled": enabled})
        return f"{control.label} is now {'enabled' if enabled else 'disabled'}."
    if action == "group_controls_status":
        controls = await db.get_controls(chat_id, update.effective_chat.title or "")
        rows = [["Control", "State", "Risk"]]
        for category, items in control_summary().items():
            rows.append([f"— {category}", "", ""])
            rows.extend([[item.label, "Enabled" if controls.get(item.key, item.default_enabled) else "Disabled", item.risk.title()] for item in items])
        await rich.send(chat_id, [heading("Lily group controls", 1), paragraph(f"{len(GROUP_CONTROL_MAP)} controls are available. Tell Lily to enable or disable any one in normal chat."), table(rows), details("Control examples", [paragraph("“Enable caps control”, “Disable link lock”, “Trust this member”, “Block domain example.com”, or “Show open reports”.")])], reply_to=update.effective_message.message_id)
        return "Displayed the group-control matrix."
    if action == "group_diagnostics":
        values = await db.get_chat_settings(chat_id, update.effective_chat.title or "")
        controls = values.get("controls", {}) if isinstance(values.get("controls"), dict) else {}
        enabled_controls = sum(1 for enabled in controls.values() if enabled)
        pending_verification = await db.list_pending_verifications(chat_id)
        reports = await db.list_reports(chat_id)
        events = await db.recent_audit(chat_id, limit=5)
        model_states = await ai.status()
        available_models = sum(1 for item in model_states if item.get("available"))
        return "\n".join([
            "Lily group diagnostics",
            f"• Controls enabled: {enabled_controls}/{len(GROUP_CONTROL_MAP)}",
            f"• Open reports: {len(reports)}",
            f"• Pending member verification: {len(pending_verification)}",
            f"• AI providers available: {available_models}/{len(model_states)}",
            f"• Warning escalation: {values.get('warning_escalation', 3)} warnings → {values.get('warning_escalation_seconds', 3600) // 60} minute restriction",
            f"• Recent audit events: {', '.join(str(item['event']) for item in events) or 'none'}",
        ])
    if action == "configure_warning_escalation":
        threshold = max(0, min(int(plan.args.get("threshold", 3)), 10))
        seconds = max(60, min(int(plan.args.get("seconds", 3600)), 2_419_200))
        await db.update_chat_settings(chat_id, {"warning_escalation": threshold, "warning_escalation_seconds": seconds}, update.effective_chat.title or "")
        await db.set_control(chat_id, "warning_escalation", threshold > 0, update.effective_chat.title or "")
        await db.audit(chat_id, user_id, "configure_warning_escalation", {"threshold": threshold, "seconds": seconds})
        return "Warning escalation is disabled." if threshold == 0 else f"After {threshold} warnings, Lily will apply a {seconds // 60}-minute restriction unless the member is trusted."
    if action == "trusted_member":
        target = int(plan.args.get("user_id") or _reply_context(update).get("reply", {}).get("user_id"))
        trusted = bool(plan.args.get("trusted", True))
        await db.set_trusted_member(chat_id, target, user_id, trusted)
        await db.audit(chat_id, user_id, "trusted_member", {"user_id": target, "trusted": trusted})
        return f"User {target} is {'now' if trusted else 'no longer'} a trusted member."
    if action == "block_domain":
        domain = str(plan.args.get("domain") or "")
        blocked = bool(plan.args.get("blocked", True))
        if not domain:
            return "Provide the domain to block or unblock."
        await db.set_blocked_domain(chat_id, domain, user_id, blocked)
        await db.audit(chat_id, user_id, "block_domain", {"domain": domain, "blocked": blocked})
        return f"Domain {domain} is {'blocked' if blocked else 'allowed'} for this group."
    if action == "list_domains":
        domains = await db.list_blocked_domains(chat_id)
        return "\n".join(f"• {domain}" for domain in domains) or "No domains are blocked."
    if action == "clear_warnings":
        target = int(plan.args.get("user_id") or _reply_context(update).get("reply", {}).get("user_id"))
        deleted = await db.clear_warnings(chat_id, target)
        await db.audit(chat_id, user_id, "clear_warnings", {"user_id": target, "cleared": deleted})
        return f"Cleared {deleted} warning(s) for user {target}."
    if action == "set_admin_title":
        target = int(plan.args.get("user_id") or _reply_context(update).get("reply", {}).get("user_id"))
        title = str(plan.args.get("title") or "")[:16]
        await update.get_bot().set_chat_administrator_custom_title(chat_id, target, title)
        await db.audit(chat_id, user_id, "set_admin_title", {"user_id": target, "title": title})
        return f"Updated administrator title for user {target}."
    if action in {"approve_join_request", "decline_join_request"}:
        target = int(plan.args.get("user_id") or _reply_context(update).get("reply", {}).get("user_id"))
        if action == "approve_join_request":
            await update.get_bot().approve_chat_join_request(chat_id, target)
        else:
            await update.get_bot().decline_chat_join_request(chat_id, target)
        await db.audit(chat_id, user_id, action, {"user_id": target})
        return f"Join request for {target} was {'approved' if action == 'approve_join_request' else 'declined'}."
    if action == "list_reports":
        reports = await db.list_reports(chat_id)
        return "\n".join(f"• #{item['id']} — user {item['target_user_id'] or 'unknown'} — {item['reason']}" for item in reports)[:3500] or "No open reports."
    if action == "resolve_report":
        report_id = int(plan.args.get("report_id") or 0)
        return f"Report #{report_id} was resolved." if report_id and await db.resolve_report(chat_id, report_id) else "That open report was not found."
    if action == "add_case_note":
        note = str(plan.args.get("note") or "").strip()
        if not note:
            return "Provide the private case note text."
        report_id = int(plan.args["report_id"]) if plan.args.get("report_id") else None
        target = int(plan.args["user_id"]) if plan.args.get("user_id") else None
        note_id = await db.add_case_note(chat_id, user_id, note, report_id, target)
        await db.audit(chat_id, user_id, "add_case_note", {"note_id": note_id, "report_id": report_id, "target_user_id": target})
        return f"Saved private moderator note #{note_id}."
    if action == "list_case_notes":
        report_id = int(plan.args["report_id"]) if plan.args.get("report_id") else None
        notes = await db.list_case_notes(chat_id, report_id)
        return "\n".join(f"• #{item['id']} — {item['note']}" for item in notes)[:3500] or "No moderator case notes are saved."
    if action == "audit_log":
        events = await db.recent_audit(chat_id, limit=30)
        return "\n".join(f"• {item['event']} — {json.dumps(item.get('detail', {}), ensure_ascii=False)[:160]}" for item in events)[:3500] or "No Lily audit events are recorded yet."
    if action == "project_run_profiles":
        return "Choose a fixed run profile: `python-main` (entrypoint such as bot.py), `python-module` (module such as manga_bot.main), `node-start` (npm run start), or `docker-compose-up` (docker compose up). Lily does not accept arbitrary chat-supplied shell commands."
    if action == "tool_capabilities":
        rows = [
            ["Capability", "Status", "Protection"],
            ["Managed project registry", "enabled", "admin-only; allow-listed repository and fixed run profile"],
            ["Project provisioning", "enabled" if settings.enable_managed_project_provisioning and not settings.bot_factory_dry_run else "dry-run / disabled", "two gates plus confirmation; private virtual environment"],
            ["Direct audio retrieval", "enabled" if settings.allow_direct_media_downloads else "disabled", "allow-listed direct audio only; rights confirmation"],
            ["Chapter file retrieval", "enabled" if settings.allow_direct_chapter_downloads else "disabled", "tracked title, approved domain, direct PDF/ZIP/CBZ, rights confirmation"],
            ["Plugins", "enabled", "trusted local plugins return named Lily plans only"],
            ["Shell and unrestricted filesystem", "disabled", "not exposed as Lily tools"],
        ]
        await rich.send(chat_id, [heading("Lily tool capability status", 2), table(rows), paragraph("Changing a host environment variable is not enough to bypass Lily’s admin, confirmation, repository, path, or source checks.")])
        return "Displayed Lily’s enabled capability gates."
    if action == "show_operating_skills":
        rows = [["Skill", "Purpose"]] + [[item["name"], item["summary"]] for item in knowledge_catalog()]
        await rich.send(chat_id, [heading("Lily operating skills", 2), paragraph("These curated protocols guide named, permissioned Lily actions. They do not enable arbitrary code or shell access."), table(rows)])
        return "Displayed Lily’s curated operating skill library."
    if action == "list_managed_projects":
        projects = await db.list_managed_projects(user_id)
        if not projects:
            return "No managed bot projects are registered for you yet."
        return "\n".join(f"• `{item['slug']}` — {item['runtime']}/{item['run_profile']} — {item['state']} — {item['repository_url']}" for item in projects)[:3500]
    if action == "register_managed_project":
        try:
            draft = bot_factory.draft(
                str(plan.args.get("slug") or ""), str(plan.args.get("repository_url") or ""), str(plan.args.get("runtime") or "python"),
                str(plan.args.get("run_profile") or "python-main"), str(plan.args.get("run_target") or "bot.py"), str(plan.args.get("branch") or "main"),
            )
            await bot_factory.register_draft(draft, user_id)
        except BotFactoryError as exc:
            return f"Project was not registered: {exc}"
        return f"Registered `{draft.slug}` as a {draft.runtime} project. Next, ask Lily to provision `{draft.slug}`. The current host remains in dry-run mode until LILY_BOT_FACTORY_DRY_RUN is explicitly disabled."
    if action == "project_env_schema":
        slug = str(plan.args.get("slug") or "")
        project = await db.get_managed_project(slug)
        if not project or int(project["owner_id"]) != user_id:
            return "That managed project was not found for your account."
        schema = await db.get_project_env_schema(slug)
        if not schema:
            return "No .env.example schema has been captured yet. Provision the project in dry-run/approved mode first; Lily never asks for secrets in a group chat."
        rows = [["Variable", "Required", "Secret", "Status"]]
        rows.extend([[item["name"], "yes" if item["required"] else "no", "yes" if item["secret"] else "no", item["validation"]] for item in schema])
        await rich.send(chat_id, [heading(f"Environment schema: {slug}", 2), table(rows)])
        return f"Displayed {len(schema)} environment variable(s) without revealing values."
    if action == "provision_managed_project":
        slug = str(plan.args.get("slug") or "")
        project = await db.get_managed_project(slug)
        if not project or int(project["owner_id"]) != user_id:
            return "That managed project was not found for your account."
        try:
            draft = bot_factory.draft(project["slug"], project["repository_url"], project["runtime"], project["run_profile"], project.get("run_target") or ("bot.py" if project["run_profile"] == "python-main" else ""), project["branch"])
            result = await bot_factory.clone_and_install(draft)
            await db.update_managed_project(slug, {"state": "dry-run" if result["dry_run"] else "provisioned"})
            await db.audit(chat_id, user_id, "managed_project_provision", {"slug": slug, "dry_run": bool(result["dry_run"]), "runtime": project["runtime"]})
        except BotFactoryError as exc:
            return f"Provisioning stopped safely: {exc}"
        if result["dry_run"]:
            return f"Dry-run for `{slug}` is ready. Lily would clone the approved repository, then run the approved install plan and `{ ' '.join(result['run']) }`. No files, dependencies, or services were changed."
        example = draft.project_root / ".env.example"
        if example.exists():
            schema = bot_factory.env.parse_example(example)
            await db.save_project_env_schema(slug, [asdict(item) for item in schema])
        return f"Provisioned `{slug}` and installed dependencies. The project is not started automatically; create and review its service configuration before any start action."
    if action == "track_series":
        title = str(plan.args.get("title") or "").strip()
        if not title:
            return "Provide the manga, manhwa, manhua, or series title to track."
        item = await db.track_series(chat_id, title, str(plan.args.get("media_type") or "manga"), user_id, str(plan.args.get("last_chapter") or ""), str(plan.args.get("target_channel_id") or ""))
        await db.audit(chat_id, user_id, "track_series", {"series_id": item["id"], "title": item["title"], "media_type": item["media_type"], "last_chapter": item["last_chapter"]})
        chapter = f" at chapter {item['last_chapter']}" if item["last_chapter"] else ""
        return f"Lily is now tracking {item['media_type']} `{item['title']}`{chapter}. This manual tracker does not scrape or download chapter content."
    if action == "list_tracked_series":
        rows = await db.list_tracked_series(chat_id)
        if not rows:
            return "No series are being tracked in this chat yet."
        await rich.send(chat_id, [heading("Tracked series", 2), table([["Title", "Type", "Latest chapter", "Status"]] + [[item["title"], item["media_type"], item["last_chapter"] or "—", item["status"]] for item in rows])])
        return f"Displayed {len(rows)} tracked series."
    if action == "update_tracked_series":
        item = await db.update_tracked_series(chat_id, str(plan.args.get("title") or ""), str(plan.args.get("last_chapter") or ""), user_id)
        if not item:
            return "That tracked series was not found. Add it first before recording a chapter update."
        await db.audit(chat_id, user_id, "update_tracked_series", {"series_id": item["id"], "title": item["title"], "last_chapter": item["last_chapter"]})
        return f"Updated `{item['title']}` to chapter {item['last_chapter']}. You can now ask Lily to prepare a channel announcement with the approved information."
    if action == "download_chapter":
        title = str(plan.args.get("title") or "").strip()
        chapter = str(plan.args.get("chapter") or "").strip()
        series = await db.get_tracked_series(chat_id, title) if title else None
        if not series:
            return "Track the series first so Lily has an approved title record; Lily does not search or scrape chapter sites."
        async def chapter_progress(value: str) -> None:
            await progress_message(update, value)
        ctx = ToolContext(update=update, context=context, db=db, progress=chapter_progress)
        try:
            path = await tools.download_chapter_file(ctx, str(plan.args.get("url") or ""), series["title"], chapter, bool(plan.args.get("rights_confirmed")))
        except (PermissionError, ValueError) as exc:
            return str(exc)
        await db.audit(chat_id, user_id, "download_chapter", {"series_id": series["id"], "title": series["title"], "chapter": chapter, "host": urlparse(str(plan.args.get("url") or "")).hostname})
        await tools.send_output(ctx, path, f"Approved chapter file: {series['title']} — Chapter {chapter}")
        return "Retrieved and delivered the approved chapter file."
    if action == "export_audit":
        events = await db.recent_audit(chat_id, limit=500)
        output = settings.work_dir / f"lily_audit_{chat_id}_{int(datetime.now(timezone.utc).timestamp())}.csv"
        with output.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["event_id", "event", "actor_id", "created_at", "details"])
            for item in events:
                writer.writerow([item.get("id"), item.get("event"), item.get("actor_id"), item.get("created_at"), json.dumps(item.get("detail", {}), ensure_ascii=False)])
        await update.get_bot().send_document(chat_id, document=output.open("rb"), caption="Lily moderation audit export")
        output.unlink(missing_ok=True)
        await db.audit(chat_id, user_id, "export_audit", {"event_count": len(events)})
        return f"Exported {len(events)} audit event(s)."
    if action == "plugin_reply":
        return str(plan.args.get("text") or plan.summary)[:3500]
    if action == "model_status":
        statuses = await ai.status()
        if not statuses:
            return "No AI model profiles are configured."
        return "\n".join(f"• {item['name']} / {item['model']} — {'available' if item['available'] else 'cooling down'}; successes={item['successes']}; failures={item['failures']}" for item in statuses)
    if action == "queue_status":
        job_id = str(plan.args.get("job_id") or "")
        item = await encoding_queue.status(job_id, user_id)
        if not item:
            return "That encoding job was not found or does not belong to you."
        return f"Job `{item['job_id']}` is **{item['state']}**. {item.get('progress', '')} {item.get('error', '')}"[:3500]
    if action == "queue_list":
        items = await encoding_queue.list(chat_id, user_id)
        if not items:
            return "You have no encoding jobs in this chat."
        return "\n".join(f"• `{item['job_id']}` — {item['state']} — {item.get('progress', '')}" for item in items)[:3500]
    if action == "cancel_queue_job":
        ok, message = await encoding_queue.cancel(str(plan.args.get("job_id") or ""), user_id)
        return message
    if action == "web_search":
        results = await web_search.search(str(plan.args.get("query") or plan.summary))
        if not results:
            return "No web results were found."
        rows = [["Title", "URL"]] + [[item["title"][:100], item["url"][:160]] for item in results]
        await rich.send(chat_id, [heading("Web search", 2), paragraph(f"Results for: {plan.args.get('query', plan.summary)}"), table(rows), details("Snippets", [paragraph(f"{item['title']}: {item['snippet']}") for item in results])])
        return f"Displayed {len(results)} web result(s)."
    if action == "generate_image":
        await progress_message(update, "Sending your image brief to the configured generation provider…")
        url = await media_generation.image(str(plan.args.get("prompt") or plan.summary), str(plan.args.get("aspect_ratio") or "1:1"))
        await rich.send(chat_id, [heading("Image ready", 2), paragraph("Lily generated an image from your brief."), blockquote(url, "Output link")])
        return f"Generated image: {url}"
    if action == "generate_video":
        await progress_message(update, "Sending your video brief to the configured generation provider…")
        url = await media_generation.video(str(plan.args.get("prompt") or plan.summary), str(plan.args.get("aspect_ratio") or "16:9"), int(plan.args.get("duration_seconds") or 8))
        await rich.send(chat_id, [heading("Video ready", 2), paragraph("Lily generated a video from your brief."), blockquote(url, "Output link")])
        return f"Generated video: {url}"
    if action == "media_info":
        async def info_progress(value: str) -> None:
            await progress_message(update, value)
        ctx = ToolContext(update=update, context=context, db=db, progress=info_progress, source_file=plan.args.get("source_file"))
        metadata = await tools.media_info(ctx)
        fmt = metadata.get("format", {}) if isinstance(metadata, dict) else {}
        rows = [["Property", "Value"], ["Format", fmt.get("format_name", "unknown")], ["Size", f"{int(float(fmt.get('size', 0) or 0)):,} bytes"], ["Duration", f"{float(fmt.get('duration', 0) or 0):.2f} seconds"]]
        for stream in metadata.get("streams", [])[:6]:
            rows.append([f"Stream {stream.get('index', '?')} ({stream.get('codec_type', 'unknown')})", f"{stream.get('codec_name', 'unknown')} {stream.get('width', '')}x{stream.get('height', '')}".strip()])
        await rich.send(chat_id, [heading("Media information", 2), table(rows)])
        return "Displayed media metadata."
    if action == "stream_link":
        async def stream_progress(value: str) -> None:
            await progress_message(update, value)
        ctx = ToolContext(update=update, context=context, db=db, progress=stream_progress, source_file=plan.args.get("source_file"))
        source = ctx.source_file or _reply_context(update).get("reply", {})
        filename = safe_filename(str(source.get("file_name") or "media.bin"))
        path = settings.work_dir / f"stream_{update.update_id}_{filename}"
        await tools._download_telegram_file(ctx, path)
        return f"Your expiring direct streaming link is:\n{await stream_links.create(path, user_id)}"
    if action == "set_auto_rename":
        enabled = bool(plan.args.get("enabled", True))
        await db.update_chat_settings(chat_id, {"auto_rename_enabled": enabled, "auto_rename_template": str(plan.args.get("template") or settings.auto_rename_template)}, update.effective_chat.title or "")
        return f"Automatic file renaming is now {'enabled' if enabled else 'disabled'} for this chat."
    if action == "set_group_rules":
        rules = str(plan.args.get("rules", plan.args.get("text", "")))
        await db.update_chat_settings(chat_id, {"rules": rules}, update.effective_chat.title or "")
        return "The group rules were saved."
    if action == "show_group_rules":
        values = await db.get_chat_settings(chat_id, update.effective_chat.title or "")
        return str(values.get("rules") or "No group rules have been saved yet.")
    if action in {"set_welcome", "set_goodbye"}:
        enabled = bool(plan.args.get("enabled", True))
        text_key = "welcome_text" if action == "set_welcome" else "goodbye_text"
        enabled_key = "welcome_enabled" if action == "set_welcome" else "goodbye_enabled"
        control_key = "welcome" if action == "set_welcome" else "goodbye"
        text_value = str(plan.args.get("text") or "").strip()
        patch = {enabled_key: enabled}
        if text_value:
            patch[text_key] = text_value[:1000]
        await db.update_chat_settings(chat_id, patch, update.effective_chat.title or "")
        await db.set_control(chat_id, control_key, enabled, update.effective_chat.title or "")
        await db.audit(chat_id, user_id, action, {"enabled": enabled, "custom_text": bool(text_value)})
        return f"The {control_key} flow is now {'enabled' if enabled else 'disabled'}."
    if action == "set_verification":
        enabled = bool(plan.args.get("enabled", True))
        await db.set_control(chat_id, "verification", enabled, update.effective_chat.title or "")
        await db.audit(chat_id, user_id, "set_verification", {"enabled": enabled})
        return f"Member verification is now {'enabled' if enabled else 'disabled'} for new members."
    if action == "warn_user":
        target_id = int(plan.args.get("user_id") or _reply_context(update).get("reply", {}).get("user_id"))
        reason = str(plan.args.get("reason") or "Group rule violation")
        count = await db.add_warning(chat_id, target_id, reason)
        await db.audit(chat_id, user_id, "warn_user", {"user_id": target_id, "reason": reason, "count": count})
        values = await db.get_chat_settings(chat_id, update.effective_chat.title or "")
        controls = values.get("controls", {}) if isinstance(values.get("controls"), dict) else {}
        threshold = int(values.get("warning_escalation", 0))
        if controls.get("warning_escalation", False) and threshold > 0 and count >= threshold and not await db.is_trusted_member(chat_id, target_id):
            seconds = max(60, min(int(values.get("warning_escalation_seconds", 3600)), 2_419_200))
            until = datetime.now(timezone.utc) + timedelta(seconds=seconds)
            try:
                await update.get_bot().restrict_chat_member(chat_id, target_id, permissions=ChatPermissions(can_send_messages=False), until_date=until)
                await db.audit(chat_id, user_id, "warning_escalation_restricted", {"user_id": target_id, "warning_count": count, "seconds": seconds})
                return f"User {target_id} was warned. Their warning count is {count}, so Lily applied a {seconds // 60}-minute restriction."
            except Exception as exc:
                await db.audit(chat_id, user_id, "warning_escalation_failed", {"user_id": target_id, "warning_count": count, "error": str(exc)[:200]})
        return f"User {target_id} was warned. Their warning count is now {count}."
    if action == "create_poll":
        question = str(plan.args.get("question") or "").strip()[:300]
        options = [str(item).strip()[:100] for item in plan.args.get("options", []) if str(item).strip()][:10]
        if not question or len(options) < 2:
            return "A poll needs a question and at least two options."
        await update.get_bot().send_poll(chat_id, question, options, is_anonymous=bool(plan.args.get("anonymous", True)))
        await db.audit(chat_id, user_id, "create_poll", {"question": question, "option_count": len(options)})
        return "The poll was posted."
    if action == "add_filter":
        trigger = str(plan.args.get("trigger") or plan.args.get("word") or "").strip()
        if not trigger:
            return "Tell me the word or phrase this filter should detect."
        await db.save_filter(chat_id, user_id, trigger, str(plan.args.get("response", "")), bool(plan.args.get("delete_message", True)), bool(plan.args.get("warn", False)))
        return f"Filter for `{trigger}` was saved."
    if action == "remove_filter":
        trigger = str(plan.args.get("trigger") or plan.args.get("word") or "").strip()
        return f"Filter removed: {trigger}" if await db.delete_filter(chat_id, trigger) else f"No filter found for: {trigger}"
    if action == "set_lock":
        content_type = str(plan.args.get("content_type") or "links").lower()
        enabled = bool(plan.args.get("enabled", True))
        await db.set_lock(chat_id, content_type, enabled)
        if content_type in GROUP_CONTROL_MAP:
            await db.set_control(chat_id, content_type, enabled, update.effective_chat.title or "")
        return f"The {content_type} lock is now {'enabled' if enabled else 'disabled'}."
    if action == "save_note":
        name = str(plan.args.get("name") or "general")
        content = str(plan.args.get("content") or plan.summary)
        await db.save_note(chat_id, user_id, name, content)
        return f"Saved the group note `{name}`."
    if action == "list_notes":
        notes = await db.get_notes(chat_id, str(plan.args.get("name")) if plan.args.get("name") else None)
        return "\n".join(f"• {item['name']}: {item['content']}" for item in notes)[:3500] or "No notes are saved for this group."
    if action == "list_filters":
        filters_list = await db.list_filters(chat_id)
        return "\n".join(f"• `{item['trigger']}` → delete={bool(item['delete_message'])}, warn={bool(item['warn'])}" for item in filters_list)[:3500] or "No filters are configured."
    if action == "list_locks":
        locks = await db.get_locks(chat_id)
        return "\n".join(f"• {name}: {'locked' if enabled else 'unlocked'}" for name, enabled in locks.items()) or "No locks are configured."
    if action == "show_warnings":
        target_id = int(plan.args.get("user_id") or _reply_context(update).get("reply", {}).get("user_id"))
        warnings = await db.list_warnings(chat_id, target_id)
        return "\n".join(f"• {item['reason']}" for item in warnings)[:3500] or "No warnings found for that user."
    if action == "search_posts":
        channel_id = str(plan.args.get("channel_id") or "")
        query = str(plan.args.get("query") or "").strip()
        if not channel_id or not query:
            return "Provide both the channel ID and search phrase."
        results = await db.search_posts(channel_id, query, limit=100)
        if not results:
            return "No indexed Lily posts matched that search."
        session = pagination.create(user_id, chat_id, query, results)
        await rich.send(chat_id, pagination.blocks(session), reply_markup=pagination.keyboard(session), reply_to=update.effective_message.message_id)
        return f"Displayed {len(results)} search result(s)."
    if action == "create_skill":
        trigger = plan.args.get("trigger")
        skill_action = plan.args.get("action")
        if not isinstance(trigger, dict) or not isinstance(skill_action, dict):
            return "Describe the skill in this form: when certain words or conditions appear, what should Lily do, and should Lily ask before risky actions?"
        name = str(plan.args.get("name") or plan.args.get("skill_name") or "Custom Lily skill")[:80]
        skill_id = await db.save_skill(chat_id, user_id, name, trigger, skill_action, str(plan.args.get("confirmation", "risky")))
        return f"Skill **{name}** was created with ID `{skill_id[:8]}`."
    if action == "publish_channel_post":
        channel_id = plan.args.get("channel_id")
        if not channel_id:
            raise ValueError("No target channel was selected.")
        ok, label = await post_service.verify_channel(update.get_bot(), channel_id, user_id)
        if not ok:
            raise PermissionError(label)
        anime = plan.args.get("anime") or {}
        blocks = post_service.announcement_blocks(anime, include_buttons=True)
        result = await rich.send(int(channel_id) if str(channel_id).lstrip("-").isdigit() else channel_id, blocks, protect_content=False)
        message_id = result.get("message_id") if isinstance(result, dict) else None
        if message_id:
            await post_service.save_last_post(channel_id, int(message_id))
            raw_channel = str(channel_id)
            link = f"https://t.me/c/{raw_channel[4:]}/{message_id}" if raw_channel.startswith("-100") else (f"https://t.me/{raw_channel.lstrip('@')}/{message_id}" if raw_channel.startswith("@") else "")
            await db.index_post(raw_channel, int(message_id), str(anime.get("title", "Announcement")), str(anime.get("plot", "")), link)
        await db.audit(chat_id, user_id, "publish_channel_post", {"channel_id": str(channel_id), "message_id": message_id, "title": anime.get("title")})
        return f"Published the announcement to {label}."
    if action == "delete_last_post":
        channel_id = plan.args.get("channel_id")
        if not channel_id:
            raise ValueError("Tell Lily which channel’s last post should be deleted.")
        ok, label = await post_service.verify_channel(update.get_bot(), channel_id, user_id)
        if not ok:
            raise PermissionError(label)
        result = await post_service.delete_last_post(update.get_bot(), channel_id)
        await db.audit(chat_id, user_id, "delete_last_post", {"channel_id": str(channel_id)})
        return f"{result} ({label})."
    if action in {"rename_file", "compress_file", "encode_media", "create_file", "download_song"}:
        async def progress(value: str) -> None:
            job_id = context.user_data.get("_encoding_job_id")
            if job_id:
                await db.update_encoding_job(job_id, progress=value)
            await progress_message(update, value)
        ctx = ToolContext(update=update, context=context, db=db, progress=progress, source_file=plan.args.get("source_file"))
        if action == "rename_file":
            path = await tools.rename_file(ctx, str(plan.args.get("new_name", "renamed_file")))
            await tools.send_output(ctx, path, "Renamed by Lily")
            return f"Renamed the file to `{path.name}`."
        if action == "compress_file":
            path = await tools.compress_file(ctx, str(plan.args.get("format", "zip")))
            await tools.send_output(ctx, path, "Compressed by Lily")
            return f"Compressed the file as `{path.name}`."
        if action == "encode_media":
            path = await tools.encode_media(ctx, str(plan.args.get("codec", "h264")), str(plan.args.get("container", "mp4")))
            await tools.send_output(ctx, path, "Encoded by Lily")
            return f"Encoded the media as `{path.name}`."
        if action == "create_file":
            path = await tools.create_file(ctx, str(plan.args.get("format", "pdf")), str(plan.args.get("prompt", "Lily document")), plan.args.get("content"))
            await tools.send_output(ctx, path, "Created by Lily")
            return f"Created `{path.name}`."
        path = await tools.download_song(ctx, str(plan.args.get("url", "")), bool(plan.args.get("rights_confirmed", False)))
        await tools.send_output(ctx, path, "Permitted audio download by Lily")
        return f"Downloaded `{path.name}`."
    if action == "remember":
        content = str(plan.args.get("content", plan.summary))
        await db.add_memory(f"chat:{chat_id}:user:{user_id}", content, user_id, chat_id)
        return "I saved that memory for this chat and user."
    if action == "forget_memory":
        return "Memory deletion should be implemented with a targeted memory ID in the next storage migration."
    if action == "set_reminder":
        return "The reminder skill is registered as an extension point; connect Lily’s persistent scheduler before enabling autonomous reminders."
    if action in {"summarize_chat", "extract_tasks", "translate", "web_research", "create_poll"}:
        return "This skill is recognized by Lily’s agent router and is ready for a provider-specific integration. The core backend keeps the action permissioned instead of pretending it completed."
    return "The request was understood, but no executable skill is enabled for it yet."


async def handle_plan(update: Update, context: ContextTypes.DEFAULT_TYPE, plan: Plan, chat_settings: dict[str, Any]) -> None:
    if plan.missing:
        await rich.send(update.effective_chat.id, [heading("I need one more detail", 3), paragraph(plan.summary), list_block(plan.missing)])
        return
    if plan.action == "help":
        await help_message(update)
        return
    if plan.action == "usage":
        await usage_message(update)
        return
    if plan.action == "list_skills":
        await list_skills_message(update)
        return
    if plan.action == "start_channel_post":
        await begin_channel_post(update, context, str(plan.args.get("post_type", "anime_announcement")))
        return
    if plan.action == "delete_last_post" and not plan.args.get("channel_id"):
        context.user_data["post_state"] = {"stage": "await_delete_channel"}
        await rich.send(update.effective_chat.id, [heading("Which channel?", 2), paragraph("Send the channel ID or @username. Lily will verify that you are an admin and that Lily can delete messages there before asking for confirmation.")])
        return
    if plan.action in ADMIN_ACTIONS and not await is_admin(update):
        await send_error(update, "Only a Telegram group admin or owner can use that action.")
        return
    if plan.action in {"rename_file", "compress_file", "encode_media", "stream_link"} and plan.args.get("source_file") is None:
        reply = _reply_context(update).get("reply", {})
        if reply.get("file_id"):
            plan.args["source_file"] = reply
    if plan.action == "none":
        memories = await db.recent_memories(f"chat:{update.effective_chat.id}:user:{update.effective_user.id}")
        answer = await ai.answer(plan.args.get("prompt", plan.summary), _reply_context(update), memories, chat_settings)
        await send_long_rich(update.effective_chat.id, answer, title="Lily", reply_to=update.effective_message.message_id)
        return
    if plan.requires_confirmation or plan.risk in {"risky", "dangerous"}:
        action_id = await db.create_pending(update.effective_chat.id, update.effective_user.id, plan.action, _plan_dict(plan), settings.confirmation_ttl_seconds)
        extra = "For audio downloads, Yes confirms you have permission to download the material." if plan.action == "download_song" else "For chapter files, Yes confirms you have already declared distribution rights for the approved direct source." if plan.action == "download_chapter" else "Lily will execute this only after you approve it."
        await rich.send(update.effective_chat.id, [heading("Confirmation required", 2), paragraph(plan.summary), table([["Action", plan.action], ["Risk", plan.risk], ["Requested by", update.effective_user.full_name]]), details("Planned stages", [list_block(plan.public_stages())]), paragraph(extra)], reply_markup=confirmation_keyboard(action_id), reply_to=update.effective_message.message_id)
        return
    await rich.send(update.effective_chat.id, [heading("Lily plan", 3), list_block(plan.public_stages())], reply_to=update.effective_message.message_id)
    await progress_message(update, "Checking the request and preparing the result…")
    result = await execute_plan(update, context, plan)
    await rich.send(update.effective_chat.id, [heading("Completed", 2), paragraph(result)])


async def auto_rename_upload(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_settings: dict[str, Any]) -> bool:
    message = update.effective_message
    source = source_file_from_message(message)
    if not source or not chat_settings.get("auto_rename_enabled"):
        return False
    old_name = source["file_name"]
    stem = Path(old_name).stem
    season_match = re.search(r"(?:s|season)[ ._-]*(\d+)", stem, re.IGNORECASE)
    episode_match = re.search(r"(?:e|episode)[ ._-]*(\d+)", stem, re.IGNORECASE)
    pair_match = re.search(r"(\d{1,2})x(\d{1,4})", stem, re.IGNORECASE)
    season = int(season_match.group(1)) if season_match else int(pair_match.group(1)) if pair_match else 1
    episode = int(episode_match.group(1)) if episode_match else int(pair_match.group(2)) if pair_match else 1
    quality_match = re.search(r"(?:2160p|1080p|720p|480p|360p|4k|8k)", stem, re.IGNORECASE)
    quality = quality_match.group(0) if quality_match else "Original"
    title = re.sub(r"[._-]*(?:s\d+e\d+|\d+x\d+|season[ ._-]*\d+|episode[ ._-]*\d+|2160p|1080p|720p|480p|360p|4k|8k).*", "", stem, flags=re.IGNORECASE).strip(" ._-_") or stem
    extension = Path(old_name).suffix.lstrip(".") or "bin"
    try:
        new_name = chat_settings.get("auto_rename_template", settings.auto_rename_template).format(title=safe_filename(title), season=season, episode=episode, quality=quality, ext=extension)
    except (KeyError, ValueError):
        new_name = f"{safe_filename(title)} - S{season:02d}E{episode:02d} - {quality}.{extension}"
    new_name = safe_filename(new_name)
    if new_name == old_name:
        return False
    plan = Plan(intent="auto_rename", summary=f"Automatically rename {old_name}", action="rename_file", risk="safe", requires_confirmation=False, args={"new_name": new_name, "source_file": source})
    await handle_plan(update, context, plan, chat_settings)
    return True


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message or not update.effective_chat or not update.effective_user:
        return
    text_value = message.text or message.caption or ""
    if await handle_post_state(update, context):
        return
    if not await moderation.inspect(update):
        return
    settings_for_chat = await db.get_chat_settings(update.effective_chat.id, update.effective_chat.title or "")
    if not text_value and await auto_rename_upload(update, context, settings_for_chat):
        return
    if not text_value and not message.reply_to_message:
        return
    skill_plan = await skill_trigger(update)
    plugin_plan = await plugin_manager.plan(text_value, update.effective_chat.id, update.effective_user.id, message.message_id)
    bot_username = context.application.bot.username
    if not bot_username:
        bot_username = (await context.application.bot.get_me()).username
    addressed = addressed_to_lily(update, bot_username)
    if not addressed and settings_for_chat.get("mention_only", True) and skill_plan is None and plugin_plan is None:
        return
    ok, reason = await db.charge_request(update.effective_user.id, update.effective_chat.id)
    if not ok:
        await send_error(update, f"Your Lily quota is unavailable because the {reason}. Try again after the quota resets or ask the administrator to change the group limits.")
        return
    if plugin_plan:
        await handle_plan(update, context, plugin_plan, settings_for_chat)
        return
    if skill_plan:
        await handle_plan(update, context, skill_plan, settings_for_chat)
        return
    memories = await db.recent_memories(f"chat:{update.effective_chat.id}:user:{update.effective_user.id}")
    plan = await ai.plan(text_value, _reply_context(update), memories, settings_for_chat)
    await handle_plan(update, context, plan, settings_for_chat)


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data:
        return
    await query.answer()
    if query.data.startswith("search:"):
        parts = query.data.split(":", 2)
        if len(parts) != 3:
            return
        session = pagination.get(parts[1])
        if not session:
            await query.edit_message_text("This Lily search session expired.")
            return
        if session.owner_id != update.effective_user.id:
            await query.answer("This search belongs to another user.", show_alert=True)
            return
        action_name = parts[2]
        if action_name == "close":
            pagination.sessions.pop(session.token, None)
            await query.edit_message_text("Search results closed.")
            return
        if action_name == "prev":
            session.page = max(0, session.page - 1)
        elif action_name == "next":
            session.page = min(session.pages - 1, session.page + 1)
        await query.edit_message_reply_markup(reply_markup=pagination.keyboard(session))
        await query.edit_message_text(text="\n".join([f"Media search: {session.query} · page {session.page + 1}/{session.pages}", *[f"{i}. {item.get('title', 'Untitled')} — {item.get('link') or 'message ' + str(item.get('message_id', ''))}" for i, item in enumerate(session.current(), start=session.page * session.page_size + 1)]]), reply_markup=pagination.keyboard(session))
        return
    if query.data.startswith("queue:"):
        parts = query.data.split(":", 2)
        if len(parts) != 3:
            return
        job_id, action_name = parts[1], parts[2]
        item = await encoding_queue.status(job_id, update.effective_user.id)
        if not item:
            await query.answer("This job is not yours or no longer exists.", show_alert=True)
            return
        if action_name == "cancel":
            ok, message = await encoding_queue.cancel(job_id, update.effective_user.id)
            await query.answer(message, show_alert=True)
            item = await encoding_queue.status(job_id, update.effective_user.id)
        await query.edit_message_text(text=f"Encoding job `{job_id}`\nState: **{item['state']}**\n{item.get('progress', '')}\n{item.get('error', '')}", parse_mode="Markdown", reply_markup=inline_keyboard([[('Refresh', f'queue:{job_id}:status'), ('Cancel', f'queue:{job_id}:cancel')]]) if item['state'] in {'queued', 'running'} else None)
        return
    if query.data.startswith("verify:"):
        try:
            target = int(query.data.split(":", 1)[1])
        except ValueError:
            return
        if update.effective_user.id != target:
            await query.answer("Only the new member can complete this verification.", show_alert=True)
            return
        if not await db.complete_verification(update.effective_chat.id, target):
            await query.answer("This verification is expired or has already been completed.", show_alert=True)
            return
        await update.get_bot().restrict_chat_member(update.effective_chat.id, target, permissions=normal_chat_permissions())
        await db.audit(update.effective_chat.id, target, "member_verified", {"user_id": target})
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("Verification complete. Your normal group permissions have been restored.")
        return
    if query.data in {"postpublish", "postcancel"}:
        state = context.user_data.get("post_state")
        if not state or state.get("stage") != "preview":
            await query.edit_message_text("This Lily post draft is no longer available.")
            return
        if query.data == "postcancel":
            context.user_data.pop("post_state", None)
            await query.edit_message_text("Post draft cancelled. Nothing was published.")
            return
        plan = Plan(intent="publish_channel_post", summary=f"Publish an anime announcement to {state['channel_label']}", action="publish_channel_post", risk="dangerous", requires_confirmation=True, args={"channel_id": state["channel_id"], "anime": state["anime"]})
        action_id = await db.create_pending(update.effective_chat.id, update.effective_user.id, plan.action, _plan_dict(plan), settings.confirmation_ttl_seconds)
        context.user_data.pop("post_state", None)
        await query.edit_message_reply_markup(reply_markup=None)
        await rich.send(update.effective_chat.id, [heading("Final publish confirmation", 2), paragraph(f"Publish this draft to {state['channel_label']}?"), paragraph("Lily must be an administrator in that channel with permission to post."), blockquote("Publishing will create a real channel post.", "Lily")], reply_markup=confirmation_keyboard(action_id))
        return
    parts = query.data.split(":", 2)
    if len(parts) != 3 or parts[0] != "confirm":
        return
    action_id, choice = parts[1], parts[2]
    pending = await db.get_pending(action_id)
    if not pending:
        await query.edit_message_text("This Lily confirmation no longer exists.")
        return
    if pending["requester_id"] != update.effective_user.id:
        await query.answer("Only the admin who requested this action can approve it.", show_alert=True)
        return
    if pending["expires_at"] < int(datetime.now(timezone.utc).timestamp()):
        await db.finish_pending(action_id, "expired")
        await query.edit_message_text("This Lily confirmation expired.")
        return
    if choice == "details":
        await query.message.reply_text(json.dumps(pending["plan"], indent=2, ensure_ascii=False)[:3900])
        return
    if choice == "no":
        await db.finish_pending(action_id, "cancelled")
        await query.edit_message_text("Cancelled. No action was taken.")
        return
    if choice != "yes" or not await is_admin(update):
        await query.answer("Only a current group admin can approve this action.", show_alert=True)
        return
    if not await db.finish_pending(action_id, "approved"):
        await query.edit_message_text("This action was already handled.")
        return
    plan = Plan.from_dict(pending["plan"])
    if plan.action == "download_song":
        plan.args["rights_confirmed"] = True
    await query.edit_message_reply_markup(reply_markup=None)
    try:
        if plan.action == "encode_media":
            job_id = await encoding_queue.enqueue(update, context, plan, execute_plan)
            await rich.send(update.effective_chat.id, [heading("Encoding job queued", 2), paragraph(f"Job ID: `{job_id}`"), paragraph("Lily will process it in the background. You can refresh its status or cancel it with the buttons below.")], reply_markup=inline_keyboard([[('Refresh', f'queue:{job_id}:status'), ('Cancel', f'queue:{job_id}:cancel')]]))
            return
        await progress_message(update, "Approval received. Lily is executing the action…")
        result = await execute_plan(update, context, plan)
        await rich.send(update.effective_chat.id, [heading("Approved and completed", 2), paragraph(result)])
    except Exception as exc:
        await send_error(update, str(exc)[:1000])


async def welcome_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await moderation.welcome(update)


async def goodbye_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await moderation.goodbye(update)


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    if isinstance(update, Update) and update.effective_chat:
        await send_error(update, "An internal error occurred while processing that request. Check the server log for details.")


def register_handlers(application: Application) -> None:
    plugin_manager.discover()
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_handler), group=-1)
    application.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, goodbye_handler), group=-1)
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, on_message), group=0)
    application.add_handler(CallbackQueryHandler(on_callback, pattern=r"^(confirm:|postpublish$|postcancel$|search:|queue:|verify:)"), group=0)
    application.add_error_handler(on_error)
