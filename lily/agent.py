from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from .config import settings
from .group_controls import GROUP_CONTROL_MAP
from .model_router import ModelProfile, ModelRouter
from .execution_workflow import visible_stages
from .knowledge_library import planning_policy


ACTIONS = {
    "none", "help", "usage", "set_settings", "create_skill", "list_skills", "skill_status",
    "ban_user", "unban_user", "kick_user", "mute_user", "unmute_user", "restrict_user", "unrestrict_user", "demote_user", "promote_user", "delete_message", "purge_messages", "report_user",
    "warn_user", "pin_message", "unpin_message", "set_group_rules", "show_group_rules", "set_welcome", "set_goodbye", "set_verification", "welcome_member",
    "rename_file", "compress_file", "encode_media", "create_file", "create_code_project",
    "download_song", "generate_image", "generate_video", "create_poll", "remember", "forget_memory", "explain_message",
    "start_channel_post", "publish_channel_post", "delete_last_post",
    "add_filter", "remove_filter", "set_lock", "save_note", "list_notes", "search_posts", "show_warnings",
    "plugin_reply", "model_status", "queue_status", "queue_list", "cancel_queue_job", "web_search", "stream_link", "set_auto_rename", "list_filters", "list_locks",
    "configure_group_control", "group_controls_status", "group_diagnostics", "configure_warning_escalation", "media_info", "export_audit", "trusted_member", "block_domain", "list_domains", "clear_warnings", "set_admin_title", "approve_join_request", "decline_join_request", "list_reports", "resolve_report", "audit_log", "add_case_note", "list_case_notes",
    "list_managed_projects", "register_managed_project", "provision_managed_project", "project_env_schema", "project_run_profiles",
    "track_series", "list_tracked_series", "update_tracked_series",
    "download_chapter",
    "tool_capabilities",
    "show_operating_skills",
    "mangadex_search", "mangadex_feed",
    "member_profile", "set_chat_title", "set_chat_description",
}

RISK = {"safe", "risky", "dangerous"}
RISK_LEVEL = {"safe": 0, "risky": 1, "dangerous": 2}
ACTION_MIN_RISK = {
    "ban_user": "dangerous", "kick_user": "dangerous", "mute_user": "dangerous", "restrict_user": "dangerous", "delete_message": "dangerous", "purge_messages": "dangerous",
    "set_chat_title": "dangerous", "set_chat_description": "dangerous", "forget_memory": "risky",
}
CONFIRM_ACTIONS = {action for action, risk in ACTION_MIN_RISK.items() if risk != "safe"} | {"download_song", "download_chapter", "register_managed_project", "provision_managed_project", "create_poll", "set_auto_rename", "track_series", "update_tracked_series"}
TARGET_ACTIONS = {"ban_user", "unban_user", "kick_user", "mute_user", "unmute_user", "restrict_user", "unrestrict_user", "demote_user", "promote_user", "warn_user", "member_profile", "show_warnings"}


@dataclass
class Plan:
    intent: str = "none"
    summary: str = ""
    action: str = "none"
    risk: str = "safe"
    requires_confirmation: bool = False
    args: dict[str, Any] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    confidence: float = 0.0

    def public_stages(self) -> list[str]:
        """Return a user-visible process summary without revealing private reasoning."""
        return visible_stages(self.action, self.risk, self.missing, self.requires_confirmation)

    def enforce_safety(self) -> "Plan":
        """Ensure that model output cannot lower action-specific protections."""
        minimum = ACTION_MIN_RISK.get(self.action, "safe")
        if RISK_LEVEL.get(self.risk, 0) < RISK_LEVEL[minimum]:
            self.risk = minimum
        if self.action in CONFIRM_ACTIONS:
            self.requires_confirmation = True
        if self.action in TARGET_ACTIONS and not self.args.get("user_id"):
            self.missing = list(dict.fromkeys([*self.missing, "Reply to the member or provide their numeric user ID"]))[:8]
        if self.action == "set_chat_title" and not str(self.args.get("title") or "").strip():
            self.missing = list(dict.fromkeys([*self.missing, "Provide the new group title"]))[:8]
        if self.action == "set_chat_description" and not str(self.args.get("description") or "").strip():
            self.missing = list(dict.fromkeys([*self.missing, "Provide the new group description"]))[:8]
        return self

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Plan":
        action = str(value.get("action", "none"))
        if action not in ACTIONS:
            action = "none"
        risk = str(value.get("risk", "safe"))
        if risk not in RISK:
            risk = "risky" if action != "none" else "safe"
        return cls(
            intent=str(value.get("intent", action)),
            summary=str(value.get("summary", ""))[:1000],
            action=action,
            risk=risk,
            requires_confirmation=bool(value.get("requires_confirmation", False)),
            args=value.get("args") if isinstance(value.get("args"), dict) else {},
            missing=[str(x) for x in value.get("missing", []) if isinstance(x, str)][:8],
            confidence=max(0.0, min(1.0, float(value.get("confidence", 0.0) or 0.0))),
        ).enforce_safety()


class AIClient:
    def __init__(self) -> None:
        profiles: list[ModelProfile] = []
        for index, item in enumerate(settings.model_profiles()):
            capabilities = item.get("capabilities", ["chat"]) if isinstance(item, dict) else ["chat"]
            profiles.append(ModelProfile(
                name=str(item.get("name", f"provider-{index + 1}")),
                base_url=str(item["base_url"]),
                api_key=str(item["api_key"]),
                model=str(item["model"]),
                family=str(item.get("family", "openai")),
                capabilities=frozenset(str(value) for value in capabilities),
                priority=int(item.get("priority", index)),
                max_retries=max(0, int(item.get("max_retries", 1))),
                privacy_tier=str(item.get("privacy_tier", "hosted")),
            ))
        self.router = ModelRouter(profiles, settings.model_cooldown_base, settings.model_cooldown_max)

    @property
    def providers(self) -> list[ModelProfile]:
        return self.router.profiles

    async def status(self) -> list[dict[str, Any]]:
        return await self.router.status()

    async def _request(self, payload: dict[str, Any], requirement: str = "chat") -> dict[str, Any]:
        request = {**payload, "_allow_public_fallback": settings.allow_public_ai_fallbacks}
        data, _profile = await self.router.chat(request, requirement=requirement)
        return data

    async def plan(self, text: str, context: dict[str, Any], memories: list[str], chat_settings: dict[str, Any]) -> Plan:
        if not self.providers:
            return self.heuristic_plan(text, context)
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "intent": {"type": "string"},
                "summary": {"type": "string"},
                "action": {"type": "string", "enum": sorted(ACTIONS)},
                "risk": {"type": "string", "enum": sorted(RISK)},
                "requires_confirmation": {"type": "boolean"},
                "args": {"type": "object", "additionalProperties": True},
                "missing": {"type": "array", "items": {"type": "string"}},
                "confidence": {"type": "number"},
            },
            "required": ["intent", "summary", "action", "risk", "requires_confirmation", "args", "missing", "confidence"],
        }
        system = f"""You are Lily, an AI-first Telegram agent. Understand ordinary language and select one safe structured action.
Never call tools yourself. Output only the JSON schema.
Available actions: {', '.join(sorted(ACTIONS))}.
Dangerous actions include banning, kicking, muting, deleting, pinning, changing rules/settings, publishing or deleting channel posts, external downloads, and expensive or large file processing.
Set requires_confirmation=true for any risky or dangerous action. Require an explicit reply target or numeric user id for moderation. For download_song, require a direct permitted URL and include rights_confirmed=false until the user explicitly confirms they have permission.
		For create_skill, put a structured trigger in args.trigger and a structured action in args.action; use args.execution_mode as auto or suggest, args.confirmation as never/risky/always, bounded args.cooldown_seconds (0–86400), and args.priority (0–1000). Only a fixed safe reply action may use automatic mode with confirmation never; all other skills must preserve confirmation. For create_poll, use args.question, args.options (2–10 strings), and optional args.anonymous. For add_filter, use args.trigger and optional args.response/delete_message/warn. For set_lock, use args.content_type and args.enabled. For configure_group_control, use args.control and args.enabled. For configure_warning_escalation, use a bounded args.threshold and args.seconds. For trusted_member, set args.user_id and args.trusted. For block_domain, set args.domain and args.blocked. For set_welcome/set_goodbye use args.enabled and args.text. For restrict_user use args.user_id, args.mode (read_only or text_only), and bounded args.seconds. For add_case_note use args.note and optional args.report_id/args.user_id. For save_note, use args.name and args.content. For search_posts, use args.channel_id and args.query. For plugin_reply, use args.text. For create_code_project, use a short args.project, args.language from python/javascript/typescript/html/css/json/yaml/bash/java/csharp/go/rust, and an args.brief. This only creates a Lily-owned source workspace and sends a ZIP; it never runs generated code or accepts shell commands.
	Group settings: {json.dumps(chat_settings, ensure_ascii=False)}
	Recent memory: {json.dumps(memories, ensure_ascii=False)}
	Curated operating policy: {planning_policy()}
"""
        payload = {
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps({"request": text, "context": context}, ensure_ascii=False)},
            ],
            "response_format": {"type": "json_schema", "json_schema": {"name": "lily_action_plan", "strict": True, "schema": schema}},
            "max_completion_tokens": 1200,
            "_reasoning": True,
            "_reasoning_effort": settings.ai_reasoning_effort,
        }
        try:
            data = await self._request(payload, requirement="structured")
            content = data["choices"][0]["message"]["content"]
            return Plan.from_dict(json.loads(content))
        except Exception:
            return self.heuristic_plan(text, context)

    async def answer(self, text: str, context: dict[str, Any], memories: list[str], chat_settings: dict[str, Any]) -> str:
        if not self.providers:
            return "I understand the request, but my AI provider is not configured yet. Add OPENAI_API_KEY and OPENAI_API_BASE, then try again."
        system = f"""You are Lily, a helpful Telegram AI agent. Answer naturally and concisely.
Use the group personality: {chat_settings.get('personality', 'friendly and helpful')}.
Do not claim to have performed an action unless the backend confirms it. Do not reveal hidden chain-of-thought; give a brief answer or concise rationale only.
Recent memory: {json.dumps(memories, ensure_ascii=False)}
"""
        payload = {
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": json.dumps({"request": text, "context": context}, ensure_ascii=False)}],
            "max_completion_tokens": 1200,
            "_reasoning": True,
            "_reasoning_effort": settings.ai_reasoning_effort,
        }
        try:
            data = await self._request(payload, requirement="chat")
            return str(data["choices"][0]["message"].get("content") or "I could not generate a response.")[:3900]
        except Exception:
            return "I could not reach the AI provider right now. Please try again in a moment."

    def heuristic_plan(self, text: str, context: dict[str, Any]) -> Plan:
        value = text.strip()
        low = value.lower()
        reply = context.get("reply", {})
        target_id = context.get("target_user_id") or reply.get("user_id")
        if not target_id:
            numeric_targets = re.findall(r"(?<!\d)(-?\d{5,})(?!\d)", value)
            target_id = numeric_targets[-1] if numeric_targets else None
        if any(word in low for word in ("search the web", "web search", "look this up", "search online")):
            query = re.sub(r"^(.*?)(search the web|web search|look this up|search online)[: ]*", "", value, flags=re.I).strip() or value
            return Plan(intent="web_search", summary="Search the web", action="web_search", risk="safe", args={"query": query}, confidence=0.9)
        if any(word in low for word in ("generate an image", "create an image", "make an image", "draw an image")):
            return Plan(intent="generate_image", summary="Generate an image", action="generate_image", risk="risky", requires_confirmation=True, args={"prompt": value}, confidence=0.85)
        if any(word in low for word in ("generate a video", "create a video", "make a video")):
            return Plan(intent="generate_video", summary="Generate a video", action="generate_video", risk="risky", requires_confirmation=True, args={"prompt": value}, confidence=0.85)
        if any(word in low for word in ("create poll", "make a poll", "start a poll")):
            body = re.sub(r"^.*?(?:create|make|start)\s+(?:a\s+)?poll\s*:?\s*", "", value, flags=re.I).strip()
            parts = [part.strip() for part in body.split("|") if part.strip()]
            question, options = (parts[0], parts[1:]) if parts else ("", [])
            return Plan(intent="create_poll", summary="Create a group poll", action="create_poll", risk="risky", requires_confirmation=True, args={"question": question, "options": options, "anonymous": "non-anonymous" not in low}, missing=[] if question and 2 <= len(options) <= 10 else ["Use: create poll: Question | Option 1 | Option 2"], confidence=0.85)
        if any(word in low for word in ("media info", "media information", "inspect this file", "show file details")):
            return Plan(intent="media_info", summary="Inspect media metadata", action="media_info", risk="safe", confidence=0.9)
        if any(word in low for word in ("explain this message", "explain that message", "what does this message mean")):
            reply_text = str(reply.get("text") or "").strip()
            return Plan(intent="explain_message", summary="Explain the quoted message", action="explain_message", risk="safe", args={"message_text": reply_text}, missing=[] if reply_text else ["Reply to the message Lily should explain"], confidence=0.9)
        if any(word in low for word in ("member profile", "member status", "check member", "is this user banned")):
            return Plan(intent="member_profile", summary=f"Check member status for {target_id or 'a member'}", action="member_profile", risk="safe", args={"user_id": int(target_id) if target_id else 0}, confidence=0.9).enforce_safety()
        if any(word in low for word in ("set group title", "change group title", "rename this group")):
            title = re.sub(r"^.*?(?:set|change)\s+(?:the\s+)?group\s+title\s*(?:to|:)?\s*|^.*?rename\s+this\s+group\s*(?:to|:)?\s*", "", value, flags=re.I).strip()
            return Plan(intent="set_chat_title", summary="Change the group title", action="set_chat_title", risk="dangerous", requires_confirmation=True, args={"title": title}, confidence=0.85).enforce_safety()
        if any(word in low for word in ("set group description", "change group description")):
            description = re.sub(r"^.*?(?:set|change)\s+(?:the\s+)?group\s+description\s*(?:to|:)?\s*", "", value, flags=re.I).strip()
            return Plan(intent="set_chat_description", summary="Change the group description", action="set_chat_description", risk="dangerous", requires_confirmation=True, args={"description": description}, confidence=0.85).enforce_safety()
        if any(word in low for word in ("export audit", "download audit log", "export moderation history")):
            return Plan(intent="export_audit", summary="Export the group audit log", action="export_audit", risk="dangerous", requires_confirmation=True, confidence=0.9)
        if any(word in low for word in ("list managed bots", "show managed bots", "list bot projects")):
            return Plan(intent="list_managed_projects", summary="List registered bot projects", action="list_managed_projects", risk="safe", confidence=0.9)
        if any(word in low for word in ("tool status", "capability status", "what tools are enabled", "agent tool status")):
            return Plan(intent="tool_capabilities", summary="Show Lily tool capability gates", action="tool_capabilities", risk="safe", confidence=0.9)
        if any(word in low for word in ("operating skills", "project knowledge", "lily skill library", "show lily skills")):
            return Plan(intent="show_operating_skills", summary="Show Lily’s curated operating skills", action="show_operating_skills", risk="safe", confidence=0.9)
        if "mangadex" in low and any(word in low for word in ("search", "find", "look up")):
            query = re.sub(r"^.*?mangadex\s*(?:search|find|look up)?\s*(?:for|:)??\s*", "", value, flags=re.I).strip()
            return Plan(intent="mangadex_search", summary="Search permitted MangaDex title metadata", action="mangadex_search", risk="safe", args={"query": query}, missing=[] if query else ["Provide a title, for example: MangaDex search for Frieren"], confidence=0.85)
        if "mangadex" in low and any(word in low for word in ("feed", "recent chapters", "latest chapters")):
            found = re.search(r"\b[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\b", low)
            manga_id = found.group(0) if found else ""
            return Plan(intent="mangadex_feed", summary="Show permitted MangaDex release-feed metadata", action="mangadex_feed", risk="safe", args={"manga_id": manga_id}, missing=[] if manga_id else ["Provide the MangaDex title ID"], confidence=0.85)
        if any(word in low for word in ("run profile options", "bot run options", "custom run command options")):
            return Plan(intent="project_run_profiles", summary="Show supported bot runtime options", action="project_run_profiles", risk="safe", confidence=0.9)
        if any(word in low for word in ("project env variables", "bot environment variables", "show bot env")):
            slug_match = re.search(r"(?:for|of|project)\s+([a-z][a-z0-9-]{1,62})", low)
            slug = slug_match.group(1) if slug_match else ""
            return Plan(intent="project_env_schema", summary="Show a managed bot environment schema", action="project_env_schema", risk="safe", args={"slug": slug}, missing=[] if slug else ["Provide the registered project name"], confidence=0.85)
        if any(word in low for word in ("register bot", "register project", "create bot project")):
            url = next(iter(re.findall(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value)), "")
            slug_match = re.search(r"(?:register|create)\s+(?:a\s+)?(?:bot\s+)?(?:project\s+)?([a-z][a-z0-9-]{1,62})", low)
            slug = slug_match.group(1) if slug_match else ""
            runtime = "docker-compose" if "docker" in low else "node" if "node" in low else "python"
            profile = "docker-compose-up" if runtime == "docker-compose" else "node-start" if runtime == "node" else "python-module" if "python-module" in low else "python-main"
            target_match = re.search(r"(?:entrypoint|run target|module)\s*[:=]?\s*([A-Za-z0-9_./-]+)", value, re.I)
            target = target_match.group(1) if target_match else ("bot.py" if profile == "python-main" else "")
            missing = [] if slug and url else ["Use: register bot <name> from https://github.com/owner/repository"]
            return Plan(intent="register_managed_project", summary=f"Register managed bot project {slug or 'draft'}", action="register_managed_project", risk="risky", requires_confirmation=True, args={"slug": slug, "repository_url": url, "branch": "main", "runtime": runtime, "run_profile": profile, "run_target": target}, missing=missing, confidence=0.8)
        if any(word in low for word in ("provision bot", "install bot project", "clone bot project")):
            slug_match = re.search(r"(?:provision|install|clone)\s+(?:the\s+)?(?:bot\s+)?(?:project\s+)?([a-z][a-z0-9-]{1,62})", low)
            slug = slug_match.group(1) if slug_match else ""
            return Plan(intent="provision_managed_project", summary=f"Provision managed bot {slug or 'project'}", action="provision_managed_project", risk="dangerous", requires_confirmation=True, args={"slug": slug}, missing=[] if slug else ["Provide the registered project name"], confidence=0.85)
        if any(word in low for word in ("list tracked series", "show tracked manga", "my tracked manhwa", "my tracked manhua")):
            return Plan(intent="list_tracked_series", summary="List tracked series", action="list_tracked_series", risk="safe", confidence=0.9)
        track_match = re.search(r"(?:track|follow)\s+(?:the\s+)?(?:manga|manhwa|manhua|series)?\s*[:\-]?\s*(.+?)(?:\s+at\s+chapter\s+(.+))?$", value, re.I)
        if track_match and any(word in low for word in ("track ", "follow ")):
            title = track_match.group(1).strip(" .")
            chapter = (track_match.group(2) or "").strip(" .")
            media_type = "manhwa" if "manhwa" in low else "manhua" if "manhua" in low else "manga"
            return Plan(intent="track_series", summary=f"Track {title or 'a series'}", action="track_series", risk="risky", requires_confirmation=True, args={"title": title, "media_type": media_type, "last_chapter": chapter}, missing=[] if title else ["Provide the title to track"], confidence=0.85)
        update_match = re.search(r"(?:update|set)\s+(.+?)\s+(?:to|at)\s+chapter\s+([A-Za-z0-9.\- ]{1,40})$", value, re.I)
        if update_match and "chapter" in low:
            return Plan(intent="update_tracked_series", summary="Update a tracked series chapter", action="update_tracked_series", risk="risky", requires_confirmation=True, args={"title": update_match.group(1).strip(), "last_chapter": update_match.group(2).strip()}, confidence=0.8)
        if "chapter" in low and any(word in low for word in ("download", "fetch")):
            url = next(iter(re.findall(r"https?://\S+", value)), "")
            before_url = value.split(url, 1)[0] if url else value
            match = re.search(r"(?:download|fetch)\s+(?:(\d+(?:\.\d+)?)\s+)?(.+?)\s+chapter", before_url, re.I)
            chapter_match = re.search(r"chapter\s*(\d+(?:\.\d+)?)", before_url, re.I)
            title = match.group(2).strip(" ,.-") if match else ""
            chapter = (match.group(1) if match and match.group(1) else (chapter_match.group(1) if chapter_match else ""))
            rights = any(phrase in low for phrase in ("i have rights", "i own the rights", "licensed source", "authorized source"))
            return Plan(intent="download_chapter", summary=f"Retrieve an approved chapter file for {title or 'a tracked series'}", action="download_chapter", risk="dangerous", requires_confirmation=True, args={"title": title, "chapter": chapter, "url": url, "rights_confirmed": rights}, missing=[item for item, present in (("series title", bool(title)), ("chapter number", bool(chapter)), ("direct approved source URL", bool(url)), ("explicit distribution-rights confirmation", rights)) if not present], confidence=0.8)
        if any(word in low for word in ("stream this", "make a streaming link", "direct link for this file")):
            return Plan(intent="stream_link", summary="Create an expiring streaming link", action="stream_link", risk="risky", requires_confirmation=True, confidence=0.9)
        if any(word in low for word in ("auto rename", "automatically rename", "rename uploads")):
            enabled = not any(word in low for word in ("disable", "off", "stop"))
            template_match = re.search(r"(?:using\s+template\s*[:=]?\s*|template\s*[:=]?\s*|format\s*[:=]?\s*|using\s+)([\"']?)(.+?)\1$", value, re.I)
            template = template_match.group(2).strip() if template_match else ""
            return Plan(intent="set_auto_rename", summary="Configure automatic file renaming", action="set_auto_rename", risk="risky", requires_confirmation=True, args={"enabled": enabled, "template": template}, confidence=0.85)
        if any(word in low for word in ("list filters", "show filters")):
            return Plan(intent="list_filters", summary="List group filters", action="list_filters", risk="safe", confidence=0.9)
        if any(word in low for word in ("list locks", "show locks")):
            return Plan(intent="list_locks", summary="List group locks", action="list_locks", risk="safe", confidence=0.9)
        if any(word in low for word in ("show rules", "group rules", "what are the rules")) and not any(word in low for word in ("set", "change", "update")):
            return Plan(intent="show_group_rules", summary="Show the group rules", action="show_group_rules", risk="safe", confidence=0.9)
        if any(word in low for word in ("set rules", "update rules", "change rules")):
            rules = re.sub(r"^.*?(?:set|update|change)\s+(?:the\s+)?rules?\s*(?:to|:)?\s*", "", value, flags=re.I).strip()
            return Plan(intent="set_group_rules", summary="Update the group rules", action="set_group_rules", risk="dangerous", requires_confirmation=True, args={"rules": rules}, missing=[] if rules else ["Provide the rules text"], confidence=0.85)
        if any(word in low for word in ("welcome message", "set welcome", "change welcome")):
            enabled = not any(word in low for word in ("disable", "turn off", "stop"))
            text_value = re.sub(r"^.*?(?:welcome message|set welcome|change welcome)\s*(?:to|:)?\s*", "", value, flags=re.I).strip()
            return Plan(intent="set_welcome", summary="Configure the welcome flow", action="set_welcome", risk="risky", requires_confirmation=True, args={"enabled": enabled, "text": text_value}, confidence=0.8)
        if any(word in low for word in ("goodbye message", "set goodbye", "change goodbye")):
            enabled = not any(word in low for word in ("disable", "turn off", "stop"))
            text_value = re.sub(r"^.*?(?:goodbye message|set goodbye|change goodbye)\s*(?:to|:)?\s*", "", value, flags=re.I).strip()
            return Plan(intent="set_goodbye", summary="Configure the goodbye flow", action="set_goodbye", risk="risky", requires_confirmation=True, args={"enabled": enabled, "text": text_value}, confidence=0.8)
        if any(word in low for word in ("set verification", "enable verification", "disable verification")):
            enabled = not any(word in low for word in ("disable", "turn off", "stop"))
            return Plan(intent="set_verification", summary=f"{'Enable' if enabled else 'Disable'} member verification", action="set_verification", risk="dangerous", requires_confirmation=True, args={"enabled": enabled}, confidence=0.85)
        if any(word in low for word in ("group controls", "control status", "show moderation settings", "show group settings")):
            return Plan(intent="group_controls_status", summary="Show group control status", action="group_controls_status", risk="safe", confidence=0.9)
        if any(word in low for word in ("group diagnostics", "moderation health", "group health", "verification queue")):
            return Plan(intent="group_diagnostics", summary="Show group moderation diagnostics", action="group_diagnostics", risk="safe", confidence=0.9)
        if any(word in low for word in ("warning escalation", "auto mute after warnings", "warning limit")):
            threshold_match = re.search(r"\b(\d{1,2})\b", low)
            duration_match = re.search(r"(?:for|duration)\s+(\d{1,5})\s*(minute|minutes|hour|hours|day|days)?", low)
            threshold = int(threshold_match.group(1)) if threshold_match else 3
            amount = int(duration_match.group(1)) if duration_match else 60
            unit = duration_match.group(2) if duration_match else "minutes"
            seconds = amount * (86400 if unit.startswith("day") else 3600 if unit.startswith("hour") else 60)
            return Plan(intent="configure_warning_escalation", summary=f"Mute after {threshold} warnings", action="configure_warning_escalation", risk="dangerous", requires_confirmation=True, args={"threshold": threshold, "seconds": seconds}, confidence=0.85)
        if any(word in low for word in ("list reports", "show reports", "open reports")):
            return Plan(intent="list_reports", summary="Show open moderation reports", action="list_reports", risk="safe", confidence=0.9)
        if any(word in low for word in ("resolve report", "close report")):
            report_id = next(iter(re.findall(r"\b(\d+)\b", low)), "")
            return Plan(intent="resolve_report", summary=f"Resolve report {report_id or ''}".strip(), action="resolve_report", risk="risky", requires_confirmation=True, args={"report_id": int(report_id) if report_id else 0}, missing=[] if report_id else ["Provide the report number"], confidence=0.85)
        if any(word in low for word in ("audit log", "show audit", "recent actions")):
            return Plan(intent="audit_log", summary="Show recent Lily audit events", action="audit_log", risk="safe", confidence=0.9)
        if any(word in low for word in ("case note", "moderator note", "staff note")):
            report_match = re.search(r"(?:report|case)\s*#?(\d+)", low)
            note = re.sub(r"^.*?(?:case note|moderator note|staff note)\s*(?:for)?\s*(?:report|case)?\s*#?\d*\s*(?:saying|:|that)?\s*", "", value, flags=re.I).strip()
            if re.search(r"\b(?:show|list|view)\b", low):
                return Plan(intent="list_case_notes", summary="Show moderator case notes", action="list_case_notes", risk="safe", args={"report_id": int(report_match.group(1)) if report_match else None}, confidence=0.85)
            return Plan(intent="add_case_note", summary="Add a moderator case note", action="add_case_note", risk="risky", requires_confirmation=True, args={"report_id": int(report_match.group(1)) if report_match else None, "user_id": int(target_id) if target_id else None, "note": note}, missing=[] if note else ["Provide the private note text"], confidence=0.8)
        if any(word in low for word in ("approve join", "approve request", "accept join")):
            if not target_id:
                return Plan(intent="approve_join_request", summary="Approve a join request", action="approve_join_request", risk="dangerous", missing=["Provide the requester's numeric user ID"], confidence=0.8)
            return Plan(intent="approve_join_request", summary=f"Approve join request for {target_id}", action="approve_join_request", risk="dangerous", requires_confirmation=True, args={"user_id": int(target_id)}, confidence=0.85)
        if any(word in low for word in ("decline join", "reject join", "decline request")):
            if not target_id:
                return Plan(intent="decline_join_request", summary="Decline a join request", action="decline_join_request", risk="dangerous", missing=["Provide the requester's numeric user ID"], confidence=0.8)
            return Plan(intent="decline_join_request", summary=f"Decline join request for {target_id}", action="decline_join_request", risk="dangerous", requires_confirmation=True, args={"user_id": int(target_id)}, confidence=0.85)
        if "admin title" in low or "custom title" in low:
            title_match = re.search(r"(?:title\s+(?:to|as)|call them)\s+[\"']?([^\"']+?)(?:[\"']?$|\s+for\s+user)", value, re.I)
            if not target_id:
                return Plan(intent="set_admin_title", summary="Set an administrator title", action="set_admin_title", risk="dangerous", missing=["Reply to the administrator or provide their numeric user ID"], confidence=0.75)
            return Plan(intent="set_admin_title", summary=f"Set the admin title for {target_id}", action="set_admin_title", risk="dangerous", requires_confirmation=True, args={"user_id": int(target_id), "title": title_match.group(1).strip() if title_match else "Moderator"}, confidence=0.8)
        if any(word in low for word in ("make trusted", "trust this user", "add trusted")):
            if not target_id:
                return Plan(intent="trusted_member", summary="Trust a member", action="trusted_member", risk="dangerous", missing=["Reply to the member or provide their numeric user ID"], confidence=0.8)
            return Plan(intent="trusted_member", summary=f"Trust member {target_id}", action="trusted_member", risk="dangerous", requires_confirmation=True, args={"user_id": int(target_id), "trusted": True}, confidence=0.85)
        if any(word in low for word in ("remove trusted", "untrust this user", "untrust")):
            if not target_id:
                return Plan(intent="trusted_member", summary="Remove a trusted member", action="trusted_member", risk="dangerous", missing=["Reply to the member or provide their numeric user ID"], confidence=0.8)
            return Plan(intent="trusted_member", summary=f"Remove trust for member {target_id}", action="trusted_member", risk="dangerous", requires_confirmation=True, args={"user_id": int(target_id), "trusted": False}, confidence=0.85)
        domain = next(iter(re.findall(r"(?:https?://)?([A-Za-z0-9.-]+\.[A-Za-z]{2,})", value)), "")
        if domain and any(word in low for word in ("block domain", "ban domain", "blacklist domain")):
            return Plan(intent="block_domain", summary=f"Block domain {domain}", action="block_domain", risk="risky", requires_confirmation=True, args={"domain": domain, "blocked": True}, confidence=0.85)
        if domain and any(word in low for word in ("unblock domain", "allow domain", "remove domain")):
            return Plan(intent="block_domain", summary=f"Unblock domain {domain}", action="block_domain", risk="risky", requires_confirmation=True, args={"domain": domain, "blocked": False}, confidence=0.85)
        if any(word in low for word in ("list blocked domains", "show blocked domains", "list domains")):
            return Plan(intent="list_domains", summary="List blocked domains", action="list_domains", risk="safe", confidence=0.9)
        if any(word in low for word in ("clear warnings", "reset warnings", "remove warnings")):
            if not target_id:
                return Plan(intent="clear_warnings", summary="Clear a member’s warnings", action="clear_warnings", risk="dangerous", missing=["Reply to the member or provide their numeric user ID"], confidence=0.8)
            return Plan(intent="clear_warnings", summary=f"Clear warnings for {target_id}", action="clear_warnings", risk="dangerous", requires_confirmation=True, args={"user_id": int(target_id)}, confidence=0.85)
        for control_key, control in GROUP_CONTROL_MAP.items():
            terms = (control_key.replace("_", " "), control.label.lower())
            if any(term in low for term in terms) and any(word in low for word in ("enable", "disable", "turn on", "turn off")):
                enabled = not any(word in low for word in ("disable", "turn off"))
                return Plan(intent="configure_group_control", summary=f"{'Enable' if enabled else 'Disable'} {control.label}", action="configure_group_control", risk=control.risk, requires_confirmation=control.risk != "safe", args={"control": control_key, "enabled": enabled}, confidence=0.8)
        if any(word in low for word in ("queue status", "encoding status", "what is encoding")):
            job_id = next(iter(re.findall(r"\b[0-9a-f]{8,16}\b", low)), "")
            return Plan(intent="queue_status", summary="Show encoding queue status", action="queue_status", risk="safe", args={"job_id": job_id}, missing=[] if job_id else ["Provide or select an encoding job ID"], confidence=0.9)
        if any(word in low for word in ("encoding queue", "list encoding jobs", "show my encoding jobs")):
            return Plan(intent="queue_list", summary="List encoding jobs", action="queue_list", risk="safe", confidence=0.9)
        if any(word in low for word in ("cancel encoding", "cancel this job", "stop encoding")):
            job_id = next(iter(re.findall(r"\b[0-9a-f]{8,16}\b", low)), "")
            return Plan(intent="cancel_queue_job", summary="Cancel an encoding job", action="cancel_queue_job", risk="risky", requires_confirmation=True, args={"job_id": job_id}, missing=[] if job_id else ["Provide or select an encoding job ID"], confidence=0.9)
        if any(word in low for word in ("usage", "limits", "quota")):
            return Plan(intent="usage", summary="Show my current Lily usage", action="usage", confidence=0.95)
        if any(word in low for word in ("model status", "ai status", "which model")):
            return Plan(intent="model_status", summary="Show AI model health", action="model_status", confidence=0.95)
        if "create skill" in low or "add a skill" in low or "new skill" in low:
            return Plan(intent="create_skill", summary="Create a custom trigger skill", action="create_skill", risk="risky", requires_confirmation=True, args={"description": value}, confidence=0.8)
        if any(phrase in low for phrase in ("skill status", "skill activity", "skill runs", "automation status")):
            return Plan(intent="skill_status", summary="Show your automatic skill activity", action="skill_status", confidence=0.9)
        if "list skills" in low or "what skills" in low:
            return Plan(intent="list_skills", summary="List enabled skills", action="list_skills", confidence=0.9)
        if any(word in low for word in ("demote", "remove admin", "take away admin")):
            if not target_id:
                return Plan(intent="demote_user", summary="Demote a user", action="demote_user", risk="dangerous", missing=["Reply to the target user’s message or provide their numeric user ID"], confidence=0.8)
            return Plan(intent="demote_user", summary=f"Demote user {target_id}", action="demote_user", risk="dangerous", requires_confirmation=True, args={"user_id": int(target_id)}, confidence=0.85)
        if any(word in low for word in ("unrestrict", "restore permissions", "allow this user again")):
            if not target_id:
                return Plan(intent="unrestrict_user", summary="Restore a member’s sending permissions", action="unrestrict_user", risk="dangerous", missing=["Reply to the member or provide their numeric user ID"], confidence=0.8)
            return Plan(intent="unrestrict_user", summary=f"Restore permissions for {target_id}", action="unrestrict_user", risk="dangerous", requires_confirmation=True, args={"user_id": int(target_id)}, confidence=0.85)
        if any(word in low for word in ("text only", "restrict to text", "read only")):
            if not target_id:
                return Plan(intent="restrict_user", summary="Apply a granular member restriction", action="restrict_user", risk="dangerous", missing=["Reply to the member or provide their numeric user ID"], confidence=0.8)
            mode = "read_only" if "read only" in low else "text_only"
            return Plan(intent="restrict_user", summary=f"Restrict user {target_id} to {mode.replace('_', ' ')}", action="restrict_user", risk="dangerous", requires_confirmation=True, args={"user_id": int(target_id), "mode": mode, "seconds": 3600}, confidence=0.85)
        if any(word in low for word in ("promote", "make admin", "promote this user")):
            if not target_id:
                return Plan(intent="promote_user", summary="Promote a user", action="promote_user", risk="dangerous", missing=["Reply to the target user’s message or provide their numeric user ID"], confidence=0.8)
            return Plan(intent="promote_user", summary=f"Promote user {target_id}", action="promote_user", risk="dangerous", requires_confirmation=True, args={"user_id": int(target_id)}, confidence=0.85)
        if any(word in low for word in ("unban", "unblock")):
            if not target_id:
                return Plan(intent="unban_user", summary="Unban a user", action="unban_user", risk="dangerous", missing=["Reply to the target user’s message or provide their numeric user ID"], confidence=0.8)
            return Plan(intent="unban_user", summary=f"Unban user {target_id}", action="unban_user", risk="dangerous", requires_confirmation=True, args={"user_id": int(target_id)}, confidence=0.85)
        if "purge" in low or "delete the last" in low and "messages" in low:
            count = next(iter(re.findall(r"\b(\d{1,3})\b", low)), "10")
            return Plan(intent="purge_messages", summary=f"Delete the last {count} messages", action="purge_messages", risk="dangerous", requires_confirmation=True, args={"count": min(100, int(count))}, confidence=0.8)
        if any(word in low for word in ("unpin", "remove pin")):
            return Plan(intent="unpin_message", summary="Unpin the selected message", action="unpin_message", risk="dangerous", requires_confirmation=True, args={"message_id": int(reply.get("message_id") or context.get("message_to_act_on") or 0)}, confidence=0.85)
        if any(word in low for word in ("show warnings", "warning history", "warnings for")):
            if not target_id:
                return Plan(intent="show_warnings", summary="Show a member’s warnings", action="show_warnings", risk="safe", missing=["Reply to the member or provide their numeric user ID"], confidence=0.8)
            return Plan(intent="show_warnings", summary=f"Show warnings for {target_id}", action="show_warnings", risk="safe", args={"user_id": int(target_id)}, confidence=0.85)
        if "warn" in low:
            if not target_id:
                return Plan(intent="warn_user", summary="Warn a member", action="warn_user", risk="risky", missing=["Reply to the member or provide their numeric user ID"], confidence=0.8)
            return Plan(intent="warn_user", summary=f"Warn user {target_id}", action="warn_user", risk="risky", requires_confirmation=True, args={"user_id": int(target_id), "reason": value}, confidence=0.85)
        if any(word in low for word in ("report this", "report user", "send a report")):
            return Plan(intent="report_user", summary="Report a user to group moderators", action="report_user", risk="risky", requires_confirmation=False, args={"reason": value}, confidence=0.8)
        if any(word in low for word in ("ban", "block permanently")):
            if not target_id:
                return Plan(intent="ban_user", summary="Ban a user", action="ban_user", risk="dangerous", missing=["Reply to the user’s message or provide a numeric Telegram user ID"], confidence=0.8)
            return Plan(intent="ban_user", summary=f"Ban user {target_id}", action="ban_user", risk="dangerous", requires_confirmation=True, args={"user_id": int(target_id), "reason": value}, confidence=0.8)
        if "kick" in low or "remove this user" in low:
            if not target_id:
                return Plan(intent="kick_user", summary="Remove a user", action="kick_user", risk="dangerous", missing=["Reply to the target user’s message or provide their numeric user ID"], confidence=0.8)
            return Plan(intent="kick_user", summary=f"Remove user {target_id}", action="kick_user", risk="dangerous", requires_confirmation=True, args={"user_id": int(target_id)}, confidence=0.8)
        if "mute" in low or "restrict" in low:
            if not target_id:
                return Plan(intent="mute_user", summary="Mute a user", action="mute_user", risk="dangerous", missing=["Reply to the target user’s message or provide their numeric user ID"], confidence=0.8)
            return Plan(intent="mute_user", summary=f"Mute user {target_id}", action="mute_user", risk="dangerous", requires_confirmation=True, args={"user_id": int(target_id), "seconds": 3600}, confidence=0.8)
        if "delete" in low and ("message" in low or "this" in low):
            message_id = context.get("message_to_act_on") or reply.get("message_id")
            if not message_id:
                return Plan(intent="delete_message", summary="Delete a message", action="delete_message", risk="dangerous", missing=["Reply to the message to delete"], confidence=0.75)
            return Plan(intent="delete_message", summary=f"Delete message {message_id}", action="delete_message", risk="dangerous", requires_confirmation=True, args={"message_id": int(message_id)}, confidence=0.8)
        if any(word in low for word in ("rename", "change the filename", "rename this file")):
            filename = context.get("reply", {}).get("file_name")
            desired = re.search(r"(?:to|as)\s+[\"']?([^\"']+?)(?:[\"']?(?:\s+and|\s+then|$))", value, re.I)
            return Plan(intent="rename_file", summary="Rename the replied file", action="rename_file", risk="risky", requires_confirmation=True, args={"new_name": desired.group(1).strip() if desired else "", "file_name": filename or ""}, missing=[] if filename and desired else (["Reply to a file"] if not filename else ["Provide the new filename"]), confidence=0.9)
        if any(word in low for word in ("code project", "create code", "write python", "python script", "javascript project", "typescript project", "create a website", "code creator")):
            language = "python" if any(word in low for word in ("python", ".py", "script")) else "javascript" if any(word in low for word in ("javascript", "node", ".js")) else "typescript" if any(word in low for word in ("typescript", ".ts")) else "html" if any(word in low for word in ("html", "website", "web page")) else "python"
            named = re.search(r"(?:project|app|script)(?:\s+(?:called|named))?\s+([a-zA-Z][a-zA-Z0-9_-]{1,62})", value, re.I)
            project = (named.group(1) if named else f"lily-{language}-project").replace("_", "-").lower()
            return Plan(intent="code_creator", summary=f"Create a {language} starter project", action="create_code_project", risk="safe", args={"project": project, "language": language, "brief": value}, confidence=0.85)
        if any(word in low for word in ("compress", "zip", "reduce the size")):
            filename = context.get("reply", {}).get("file_name")
            return Plan(intent="compress_file", summary="Compress the replied file", action="compress_file", risk="risky", requires_confirmation=True, args={"file_name": filename or "", "format": "zip"}, missing=[] if filename else ["Reply to the file to compress"], confidence=0.9)
        if any(word in low for word in ("encode", "transcode", "convert video", "convert this video")):
            filename = context.get("reply", {}).get("file_name")
            return Plan(intent="encode_media", summary="Encode the replied media", action="encode_media", risk="risky", requires_confirmation=True, args={"file_name": filename or "", "codec": "h264", "container": "mp4"}, missing=[] if filename else ["Reply to the media file"], confidence=0.85)
        if any(word in low for word in ("download song", "download this song", "get this audio")):
            url = next(iter(re.findall(r"https?://\S+", value)), "")
            return Plan(intent="download_song", summary="Download permitted audio", action="download_song", risk="dangerous", requires_confirmation=True, args={"url": url, "rights_confirmed": False}, missing=[] if url else ["Provide a direct URL to audio you are authorized to download"], confidence=0.75)
        if any(word in low for word in ("post to my channel", "make a channel post", "create a post", "anime announcement", "episode announcement")):
            return Plan(intent="channel_post", summary="Create an anime-style channel announcement", action="start_channel_post", risk="dangerous", args={"post_type": "anime_announcement", "request": value}, confidence=0.85)
        if any(word in low for word in ("delete last post", "remove last post", "delete the previous post")):
            return Plan(intent="delete_last_post", summary="Delete Lily’s last tracked channel post", action="delete_last_post", risk="dangerous", requires_confirmation=True, args={}, confidence=0.85)
        lock_types = ("links", "forwards", "photos", "videos", "documents", "audio", "animations", "stickers", "polls", "contacts", "locations")
        if any(f"lock {item}" in low or f"unlock {item}" in low for item in lock_types):
            content_type = next((item for item in lock_types if item in low), "links")
            return Plan(intent="set_lock", summary=f"Update the {content_type} lock", action="set_lock", risk="dangerous", requires_confirmation=True, args={"content_type": content_type, "enabled": not low.startswith("unlock")}, confidence=0.8)
        if any(word in low for word in ("add a filter", "create a filter", "when someone says")):
            return Plan(intent="add_filter", summary="Create a group message filter", action="add_filter", risk="risky", requires_confirmation=True, args={}, missing=["trigger", "action"], confidence=0.7)
        if any(word in low for word in ("save a note", "remember this as", "save this note")):
            return Plan(intent="save_note", summary="Save a group note", action="save_note", risk="safe", args={"name": "general", "content": value}, confidence=0.75)
        if any(word in low for word in ("search posts", "find a post", "find posts")):
            return Plan(intent="search_posts", summary="Search indexed channel posts", action="search_posts", risk="safe", args={"query": value}, missing=["channel_id"], confidence=0.75)
        if any(word in low for word in ("create a pdf", "create a file", "make a document", "generate a report")):
            return Plan(intent="create_file", summary="Create a document from the request", action="create_file", risk="safe", args={"format": "pdf", "prompt": value}, confidence=0.8)
        if any(word in low for word in ("summarize", "summary")):
            return Plan(intent="summarize", summary="Summarize the supplied context", action="none", risk="safe", args={"prompt": value}, confidence=0.8)
        if any(word in low for word in ("remind me", "reminder")):
            return Plan(intent="reminder_unavailable", summary="Reminders are not enabled until Lily is attached to its persistent scheduler.", action="none", risk="safe", args={"prompt": "Explain concisely that reminders are unavailable because Lily’s persistent scheduler has not been configured; do not claim a reminder was created."}, confidence=0.95)
        if any(word in low for word in ("remember", "save this")):
            return Plan(intent="remember", summary="Save a memory", action="remember", risk="safe", args={"content": value}, confidence=0.8)
        return Plan(intent="conversation", summary="Answer the user conversationally", action="none", risk="safe", args={"prompt": value}, confidence=0.5)


ai = AIClient()
