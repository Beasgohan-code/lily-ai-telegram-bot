from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Any

from telegram import ChatPermissions, Update
from telegram.ext import Application, CallbackQueryHandler, ContextTypes, MessageHandler, filters

from .agent import Plan, ai
from .config import settings
from .db import db
from .rich import blockquote, bold, code, confirmation_keyboard, details, divider, heading, inline_keyboard, list_block, paragraph, preformatted, rich, table, thinking
from .tools import LilyTools, ToolContext
from .postbot import post_service
from .moderation import moderation
from .plugin_manager import plugin_manager


tools = LilyTools(db)

ADMIN_ACTIONS = {
    "ban_user", "kick_user", "mute_user", "unmute_user", "delete_message", "pin_message",
    "set_settings", "create_skill", "set_group_rules", "start_channel_post", "publish_channel_post", "delete_last_post",
    "warn_user", "add_filter", "remove_filter", "set_lock", "save_note", "list_notes", "search_posts", "show_warnings",
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
    await rich.send(chat.id, [heading("Lily is working", 3), thinking(), paragraph(text_value)], reply_to=update.effective_message.message_id if update.effective_message else None)


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
        permissions = ChatPermissions(can_send_messages=True, can_send_audios=True, can_send_documents=True, can_send_photos=True, can_send_videos=True, can_send_video_notes=True, can_send_voice_notes=True, can_send_polls=True, can_send_other_messages=True, can_add_web_page_previews=True)
        await update.get_bot().restrict_chat_member(chat_id, int(plan.args["user_id"]), permissions=permissions)
        return f"User {plan.args['user_id']} was unmuted."
    if action == "delete_message":
        await update.get_bot().delete_message(chat_id, int(plan.args["message_id"]))
        await db.audit(chat_id, user_id, "delete_message", plan.args)
        return "The message was deleted."
    if action == "pin_message":
        await update.get_bot().pin_chat_message(chat_id, int(plan.args.get("message_id", update.effective_message.message_id)), disable_notification=True)
        return "The message was pinned."
    if action == "set_settings":
        allowed = {"personality", "language", "mention_only", "memory_enabled", "auto_confirm_safe", "welcome_enabled", "welcome_text", "daily_request_limit", "monthly_request_limit", "daily_bytes_limit", "monthly_bytes_limit", "warning_escalation"}
        patch = {key: value for key, value in plan.args.items() if key in allowed}
        if not patch:
            return "Tell me which setting you want to change."
        await db.update_chat_settings(chat_id, patch, update.effective_chat.title or "")
        return "The group settings were updated."
    if action == "plugin_reply":
        return str(plan.args.get("text") or plan.summary)[:3500]
    if action == "model_status":
        statuses = await ai.status()
        if not statuses:
            return "No AI model profiles are configured."
        return "\n".join(f"• {item['name']} / {item['model']} — {'available' if item['available'] else 'cooling down'}; successes={item['successes']}; failures={item['failures']}" for item in statuses)
    if action == "set_group_rules":
        rules = str(plan.args.get("rules", plan.args.get("text", "")))
        await db.update_chat_settings(chat_id, {"rules": rules}, update.effective_chat.title or "")
        return "The group rules were saved."
    if action == "warn_user":
        target_id = int(plan.args.get("user_id") or _reply_context(update).get("reply", {}).get("user_id"))
        reason = str(plan.args.get("reason") or "Group rule violation")
        count = await db.add_warning(chat_id, target_id, reason)
        await db.audit(chat_id, user_id, "warn_user", {"user_id": target_id, "reason": reason, "count": count})
        return f"User {target_id} was warned. Their warning count is now {count}."
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
        return f"The {content_type} lock is now {'enabled' if enabled else 'disabled'}."
    if action == "save_note":
        name = str(plan.args.get("name") or "general")
        content = str(plan.args.get("content") or plan.summary)
        await db.save_note(chat_id, user_id, name, content)
        return f"Saved the group note `{name}`."
    if action == "list_notes":
        notes = await db.get_notes(chat_id, str(plan.args.get("name")) if plan.args.get("name") else None)
        return "\n".join(f"• {item['name']}: {item['content']}" for item in notes)[:3500] or "No notes are saved for this group."
    if action == "show_warnings":
        target_id = int(plan.args.get("user_id") or _reply_context(update).get("reply", {}).get("user_id"))
        warnings = await db.list_warnings(chat_id, target_id)
        return "\n".join(f"• {item['reason']}" for item in warnings)[:3500] or "No warnings found for that user."
    if action == "search_posts":
        channel_id = str(plan.args.get("channel_id") or "")
        query = str(plan.args.get("query") or "").strip()
        if not channel_id or not query:
            return "Provide both the channel ID and search phrase."
        results = await db.search_posts(channel_id, query)
        if not results:
            return "No indexed Lily posts matched that search."
        return "\n".join(f"• {row['title']} — {row.get('link') or 'message ' + str(row['message_id'])}" for row in results)[:3500]
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
            await progress_message(update, value)
        ctx = ToolContext(update=update, context=context, db=db, progress=progress)
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
    if action in {"summarize_chat", "extract_tasks", "translate", "web_research", "generate_image", "create_poll"}:
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
    if plan.action == "none":
        memories = await db.recent_memories(f"chat:{update.effective_chat.id}:user:{update.effective_user.id}")
        answer = await ai.answer(plan.args.get("prompt", plan.summary), _reply_context(update), memories, chat_settings)
        await rich.send(update.effective_chat.id, [heading("Lily", 2), paragraph(answer)])
        return
    if plan.requires_confirmation or plan.risk in {"risky", "dangerous"}:
        action_id = await db.create_pending(update.effective_chat.id, update.effective_user.id, plan.action, _plan_dict(plan), settings.confirmation_ttl_seconds)
        extra = "\n\nFor audio downloads, Yes means you confirm that you have permission to download the material." if plan.action == "download_song" else ""
        await rich.send(update.effective_chat.id, [heading("Confirmation required", 2), paragraph(plan.summary), table([["Action", plan.action], ["Risk", plan.risk], ["Requested by", update.effective_user.full_name]]), paragraph(extra or "Lily will execute this only after you approve it."), details("Action details", [preformatted(json.dumps(_plan_dict(plan), indent=2, ensure_ascii=False), "json")])], reply_markup=confirmation_keyboard(action_id), reply_to=update.effective_message.message_id)
        return
    await progress_message(update, "Checking the request and preparing the result…")
    result = await execute_plan(update, context, plan)
    await rich.send(update.effective_chat.id, [heading("Completed", 2), paragraph(result)])


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message or not update.effective_chat or not update.effective_user:
        return
    text_value = message.text or message.caption or ""
    if not text_value and not message.reply_to_message:
        return
    if await handle_post_state(update, context):
        return
    if not await moderation.inspect(update):
        return
    settings_for_chat = await db.get_chat_settings(update.effective_chat.id, update.effective_chat.title or "")
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
    await progress_message(update, "Approval received. Lily is executing the action…")
    try:
        result = await execute_plan(update, context, plan)
        await rich.send(update.effective_chat.id, [heading("Approved and completed", 2), paragraph(result)])
    except Exception as exc:
        await send_error(update, str(exc)[:1000])


async def welcome_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await moderation.welcome(update)


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    if isinstance(update, Update) and update.effective_chat:
        await send_error(update, "An internal error occurred while processing that request. Check the server log for details.")


def register_handlers(application: Application) -> None:
    plugin_manager.discover()
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_handler), group=-1)
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, on_message), group=0)
    application.add_handler(CallbackQueryHandler(on_callback, pattern=r"^(confirm:|postpublish$|postcancel$)"), group=0)
    application.add_error_handler(on_error)
