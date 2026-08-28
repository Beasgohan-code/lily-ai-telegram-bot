"""Route user requests to the most relevant Lily knowledge collection."""

from __future__ import annotations

import re
from typing import Any

from .knowledge_library import SKILLS, read_skill


_COLLECTION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "moderation": ("ban", "kick", "mute", "warn", "moderat", "filter", "lock", "report", "spam", "flood", "verify"),
    "media": ("encode", "ffmpeg", "compress", "rename", "stream", "video", "audio", "transcode", "ffprobe"),
    "series-release": ("manga", "manhwa", "manhua", "chapter", "track series", "release", "anime"),
    "queue": ("queue", "job", "encoding", "cancel job", "background"),
    "channels": ("channel post", "announcement", "publish", "rich message"),
    "model-routing": ("model", "provider", "fallback", "cooldown", "ai key", "openai", "gemini"),
    "bot-operations": ("register bot", "managed project", "provision", "bot factory"),
    "deployment": ("deploy", "railway", "render", "vercel", "systemctl", "service"),
    "miniapp": ("mini app", "miniapp", "web app", "initdata"),
    "agent-workflow": ("plan", "confirm", "approval", "workflow", "scenario", "runbook", "handoff"),
    "agency-orchestration": ("nexus", "orchestrat", "specialist team", "agent team", "runbook"),
    "rag-routing": ("knowledge", "rag", "search skill", "operating skill"),
    "sources/mangadex": ("mangadex",),
    "telegram-api": ("telegram api", "bot api", "richmessage", "local bot api"),
}


def route(text: str, limit: int = 3) -> list[dict[str, Any]]:
    """Score bundled knowledge collections and return the top matches."""
    low = text.lower()
    scores: list[tuple[int, str]] = []
    for name, keywords in _COLLECTION_KEYWORDS.items():
        if name not in SKILLS:
            continue
        score = sum(2 if re.search(rf"\b{re.escape(word)}\b", low) else 1 for word in keywords if word in low)
        if score:
            scores.append((score, name))
    scores.sort(key=lambda item: (-item[0], item[1]))
    results: list[dict[str, Any]] = []
    for score, name in scores[: max(1, min(limit, 5))]:
        try:
            excerpt = read_skill(name, limit=600)
        except KeyError:
            excerpt = SKILLS[name]
        results.append({"collection": name, "score": score, "summary": SKILLS[name], "excerpt": excerpt[:600]})
    return results


def planning_context(text: str) -> str:
    """Return a bounded excerpt from the best-matching knowledge collections."""
    matches = route(text, limit=2)
    if not matches:
        return ""
    parts = [f"[{item['collection']}] {item['excerpt']}" for item in matches]
    return "\n\n".join(parts)[:2_400]
