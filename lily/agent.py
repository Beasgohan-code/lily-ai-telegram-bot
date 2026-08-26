from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

import httpx

from .config import settings


ACTIONS = {
    "none", "help", "usage", "set_settings", "create_skill", "list_skills",
    "ban_user", "kick_user", "mute_user", "unmute_user", "delete_message",
    "warn_user", "pin_message", "set_group_rules", "welcome_member",
    "rename_file", "compress_file", "encode_media", "create_file", "summarize_file",
    "download_song", "set_reminder",     "summarize_chat", "extract_tasks", "translate", "web_research", "generate_image", "create_poll", "remember", "forget_memory",
    "start_channel_post", "publish_channel_post", "delete_last_post",
    "add_filter", "remove_filter", "set_lock", "save_note", "list_notes", "search_posts", "show_warnings",

}

RISK = {"safe", "risky", "dangerous"}


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
            confidence=float(value.get("confidence", 0.0) or 0.0),
        )


class AIClient:
    def __init__(self) -> None:
        keys = settings.ai_keys or ((settings.openai_api_key,) if settings.openai_api_key else ())
        bases = settings.ai_bases or ((settings.openai_api_base,) if settings.openai_api_base else ())
        self.providers = [(key, bases[min(index, len(bases) - 1)].rstrip("/")) for index, key in enumerate(keys) if bases and key]
        self.provider_index = 0
        self.model = settings.ai_model

    async def _request(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.providers:
            raise RuntimeError("No AI provider is configured")
        last_error: Exception | None = None
        for offset in range(len(self.providers)):
            index = (self.provider_index + offset) % len(self.providers)
            key, base = self.providers[index]
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(45.0, connect=10.0)) as client:
                    response = await client.post(f"{base}/chat/completions", headers={"Authorization": f"Bearer {key}"}, json=payload)
                    if response.status_code in {401, 403, 408, 409, 429} or response.status_code >= 500:
                        raise RuntimeError(f"provider {index} returned HTTP {response.status_code}")
                    response.raise_for_status()
                    data = response.json()
                self.provider_index = index
                return data
            except Exception as exc:
                last_error = exc
                continue
        raise RuntimeError(f"All AI providers failed: {last_error}")

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
For create_skill, put a short trigger description in args.trigger and a safe action description in args.action; ask for missing fields when unclear. For add_filter, use args.trigger and optional args.response/delete_message/warn. For set_lock, use args.content_type and args.enabled. For save_note, use args.name and args.content. For search_posts, use args.channel_id and args.query.
Group settings: {json.dumps(chat_settings, ensure_ascii=False)}
Recent memory: {json.dumps(memories, ensure_ascii=False)}
"""
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps({"request": text, "context": context}, ensure_ascii=False)},
            ],
            "response_format": {"type": "json_schema", "json_schema": {"name": "lily_action_plan", "strict": True, "schema": schema}},
            "max_completion_tokens": 1200,
        }
        if self.model.startswith("gpt-5"):
            payload["reasoning"] = {"effort": settings.ai_reasoning_effort}
        try:
            data = await self._request(payload)
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
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": json.dumps({"request": text, "context": context}, ensure_ascii=False)}],
            "max_completion_tokens": 1200,
        }
        if self.model.startswith("gpt-5"):
            payload["reasoning"] = {"effort": settings.ai_reasoning_effort}
        try:
            data = await self._request(payload)
            return str(data["choices"][0]["message"].get("content") or "I could not generate a response.")[:3900]
        except Exception:
            return "I could not reach the AI provider right now. Please try again in a moment."

    def heuristic_plan(self, text: str, context: dict[str, Any]) -> Plan:
        value = text.strip()
        low = value.lower()
        reply = context.get("reply", {})
        target_id = context.get("target_user_id") or reply.get("user_id")
        if any(word in low for word in ("usage", "limits", "quota")):
            return Plan(intent="usage", summary="Show my current Lily usage", action="usage", confidence=0.95)
        if "create skill" in low or "add a skill" in low or "new skill" in low:
            return Plan(intent="create_skill", summary="Create a custom trigger skill", action="create_skill", risk="risky", requires_confirmation=True, args={"description": value}, confidence=0.8)
        if "list skills" in low or "what skills" in low:
            return Plan(intent="list_skills", summary="List enabled skills", action="list_skills", confidence=0.9)
        if any(word in low for word in ("ban", "block permanently")):
            if not target_id:
                return Plan(intent="ban_user", summary="Ban a user", action="ban_user", risk="dangerous", requires_confirmation=False, missing=["Reply to the user’s message or provide a numeric Telegram user ID"], confidence=0.8)
            return Plan(intent="ban_user", summary=f"Ban user {target_id}", action="ban_user", risk="dangerous", requires_confirmation=True, args={"user_id": int(target_id), "reason": value, "rights_confirmed": True}, confidence=0.8)
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
            return Plan(intent="channel_post", summary="Create an anime-style channel announcement", action="start_channel_post", risk="dangerous", requires_confirmation=True, args={"post_type": "anime_announcement", "request": value}, confidence=0.85)
        if any(word in low for word in ("delete last post", "remove last post", "delete the previous post")):
            return Plan(intent="delete_last_post", summary="Delete Lily’s last tracked channel post", action="delete_last_post", risk="dangerous", requires_confirmation=True, args={}, confidence=0.85)
        if any(word in low for word in ("lock links", "lock photos", "lock videos", "lock documents", "unlock links", "unlock photos", "unlock videos", "unlock documents")):
            content_type = next((item for item in ("links", "photos", "videos", "documents") if item in low), "links")
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
            return Plan(intent="summarize", summary="Summarize the supplied context", action="summarize_chat", risk="safe", confidence=0.8)
        if any(word in low for word in ("remind me", "reminder")):
            return Plan(intent="reminder", summary="Create a reminder", action="set_reminder", risk="risky", requires_confirmation=True, args={"text": value}, confidence=0.75)
        if any(word in low for word in ("remember", "save this")):
            return Plan(intent="remember", summary="Save a memory", action="remember", risk="safe", args={"content": value}, confidence=0.8)
        return Plan(intent="conversation", summary="Answer the user conversationally", action="none", risk="safe", args={"prompt": value}, confidence=0.5)


ai = AIClient()
