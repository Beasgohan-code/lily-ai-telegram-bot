from __future__ import annotations

import copy
import hashlib
import html
import re
import time
from typing import Any
from urllib.parse import urlsplit

import httpx

from .config import settings
from .db import db
from .rich import bold, code, expandable_quote, paragraph, rich


ANIME_QUERY = """
query ($search: String) {
  Page(perPage: 1) {
    media(search: $search, type: ANIME, sort: POPULARITY_DESC) {
      id
      title { romaji english native }
      synonyms
      type
      format
      averageScore
      meanScore
      status(version: 2)
      episodes
      duration
      genres
      description(asHtml: false)
      coverImage { large }
      siteUrl
      nextAiringEpisode { episode airingAt }
      studios { nodes { name } }
    }
  }
}
"""

_METADATA_CACHE_SECONDS = 600
_MAX_CACHE_ENTRIES = 128


def _short_text(value: Any, fallback: str, limit: int) -> str:
    cleaned = re.sub(r"\s+", " ", str(value or "")).replace("\x00", " ").strip()
    if not cleaned:
        return fallback
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[: limit - 1].rsplit(' ', 1)[0].rstrip()}…"


def _safe_anilist_url(value: Any, anilist_id: Any) -> str:
    candidate = str(value or "").strip()
    parsed = urlsplit(candidate)
    if parsed.scheme == "https" and (parsed.netloc == "anilist.co" or parsed.netloc.endswith(".anilist.co")):
        return candidate
    if str(anilist_id or "").isdigit():
        return f"https://anilist.co/anime/{anilist_id}"
    return "https://anilist.co/search/anime"


class ChannelPostService:
    def __init__(self, metadata_cache_seconds: int = _METADATA_CACHE_SECONDS) -> None:
        self.metadata_cache_seconds = max(0, metadata_cache_seconds)
        self._metadata_cache: dict[str, tuple[float, dict[str, Any]]] = {}

    @staticmethod
    def _title_candidates(title: str) -> list[str]:
        raw = _short_text(title, "", 240)
        if not raw:
            raise ValueError("Tell Lily the anime title to look up.")
        without_extension = re.sub(r"\.(?:mkv|mp4|avi|webm|m4v)$", "", raw, flags=re.IGNORECASE)
        readable = re.sub(r"[._]+", " ", without_extension).strip()
        simplified = re.split(r"\s{2,}|\s+-\s+|:\s+|\s+\[", readable, maxsplit=1)[0].strip()
        release_clean = re.split(r"\s+(?:S\d{1,2}E\d{1,3}|E\d{1,3}|EP\d{1,3}|\d{3,4}p|WEB[- ]?DL|BLURAY|HEVC|X26[45])\b", readable, maxsplit=1, flags=re.IGNORECASE)[0].strip()
        return list(dict.fromkeys(item for item in (raw, readable, simplified, release_clean) if item))

    def _cache_key(self, title: str) -> str:
        return re.sub(r"\s+", " ", title).strip().lower()

    def _cached_metadata(self, key: str) -> dict[str, Any] | None:
        cached = self._metadata_cache.get(key)
        if not cached or time.monotonic() - cached[0] >= self.metadata_cache_seconds:
            self._metadata_cache.pop(key, None)
            return None
        return copy.deepcopy(cached[1])

    def _store_metadata(self, key: str, anime: dict[str, Any]) -> None:
        if not self.metadata_cache_seconds:
            return
        if len(self._metadata_cache) >= _MAX_CACHE_ENTRIES:
            oldest = min(self._metadata_cache, key=lambda item: self._metadata_cache[item][0])
            self._metadata_cache.pop(oldest, None)
        self._metadata_cache[key] = (time.monotonic(), copy.deepcopy(anime))

    async def lookup_anime(self, title: str) -> dict[str, Any]:
        # Retry safe title variants because media filenames often contain release metadata.
        candidates = self._title_candidates(title)
        cache_key = self._cache_key(candidates[0])
        cached = self._cached_metadata(cache_key)
        if cached:
            return cached
        item = None
        had_service_error = False
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=8.0), headers={"User-Agent": "LilyTelegramBot/1.0"}) as client:
            for candidate in candidates:
                try:
                    response = await client.post("https://graphql.anilist.co", json={"query": ANIME_QUERY, "variables": {"search": candidate}})
                    response.raise_for_status()
                    data = response.json()
                except (httpx.HTTPError, ValueError):
                    had_service_error = True
                    continue
                entries = data.get("data", {}).get("Page", {}).get("media", [])
                if entries:
                    item = entries[0]
                    break
        if not item:
            if had_service_error:
                raise ValueError("Anime metadata is temporarily unavailable. Please retry or provide the post details manually.")
            raise ValueError(f"I could not find anime metadata for {title!r}. Try another title or provide the fields manually.")
        title_data = item.get("title") or {}
        plot = _short_text(html.unescape(re.sub(r"<[^>]+>", "", item.get("description") or "")), "No synopsis available.", 2500)
        next_episode = item.get("nextAiringEpisode") or {}
        studios = ", ".join(_short_text(node.get("name"), "", 80) for node in (item.get("studios", {}).get("nodes", []) or []) if node.get("name"))
        anime = {
            "title": _short_text(title_data.get("english") or title_data.get("romaji") or title_data.get("native") or candidates[0], "Anime announcement", 180),
            "type": _short_text(item.get("format") or item.get("type"), "TV", 48),
            "rating": f"{(item.get('averageScore') or item.get('meanScore') or 0) / 10:.1f}/10" if (item.get("averageScore") or item.get("meanScore")) else "N/A",
            "status": _short_text(str(item.get("status") or "Unknown").replace("_", " ").title(), "Unknown", 48),
            "episodes": _short_text(item.get("episodes") or (f"Next: {next_episode.get('episode')}" if next_episode.get("episode") else ""), "Unknown", 64),
            "genres": _short_text(", ".join(str(genre) for genre in (item.get("genres") or [])), "Unknown", 400),
            "plot": plot,
            "anilist_id": item.get("id"),
            "cover_url": (item.get("coverImage") or {}).get("large"),
            "site_url": _safe_anilist_url(item.get("siteUrl"), item.get("id")),
            "studio": _short_text(studios, "", 300),
        }
        self._store_metadata(cache_key, anime)
        return copy.deepcopy(anime)

    def announcement_blocks(self, anime: dict[str, Any], include_buttons: bool = True) -> list[dict[str, Any]]:
        title = _short_text(anime.get("title"), "Anime announcement", 180)
        anilist_id = anime.get("anilist_id")
        blocks: list[dict[str, Any]] = [
            paragraph([bold(title)]),
            paragraph([bold("» Type: "), code(_short_text(anime.get("type"), "N/A", 48))]),
            paragraph([bold("» Average Rating: "), code(_short_text(anime.get("rating"), "N/A", 32))]),
            paragraph([bold("» Status: "), code(_short_text(anime.get("status"), "N/A", 48))]),
            paragraph([bold("» Episodes: "), code(_short_text(anime.get("episodes"), "N/A", 64))]),
            paragraph([bold("» Genre: "), _short_text(anime.get("genres"), "N/A", 400)]),
            expandable_quote(_short_text(anime.get("plot"), "No synopsis available.", 2500), "Synopsis"),
        ]
        if include_buttons:
            blocks.append({
                "type": "buttons",
                "buttons": [
                    {"text": "More info", "style": "primary", "url": _safe_anilist_url(anime.get("site_url"), anilist_id)},
                    {"text": "Share", "style": "secondary", "switch_inline_query": title},
                ],
                "align": "center",
            })
        return blocks

    async def verify_channel(self, bot, channel_id: int | str, requester_id: int) -> tuple[bool, str]:
        try:
            chat = await bot.get_chat(channel_id)
            bot_member = await bot.get_chat_member(chat.id, bot.id)
            if bot_member.status not in {"administrator", "creator"}:
                return False, "Lily must be an administrator in that channel before posting."
            if getattr(bot_member, "can_post_messages", True) is False:
                return False, "Lily is an admin there but does not have permission to post messages."
            if requester_id in settings.admin_user_ids:
                return True, chat.title or str(channel_id)
            requester = await bot.get_chat_member(chat.id, requester_id)
            if requester.status not in {"administrator", "creator"}:
                return False, "Only a channel owner or administrator can ask Lily to publish there."
            return True, chat.title or str(channel_id)
        except Exception as exc:
            return False, f"I could not verify that channel: {exc}"

    def _key(self, channel_id: int | str) -> int:
        if str(channel_id).lstrip("-").isdigit():
            return int(channel_id)
        digest = hashlib.sha256(str(channel_id).lower().encode()).hexdigest()
        return -int(digest[:12], 16)

    async def save_last_post(self, channel_id: int | str, message_id: int) -> None:
        await db.update_chat_settings(self._key(channel_id), {"last_post_id": message_id, "channel_id": str(channel_id)})

    async def delete_last_post(self, bot, channel_id: int | str) -> str:
        key = self._key(channel_id)
        channel_settings = await db.get_chat_settings(key)
        message_id = channel_settings.get("last_post_id")
        if not message_id:
            raise ValueError("Lily has no tracked last post for that channel.")
        await bot.delete_message(channel_id, int(message_id))
        await db.update_chat_settings(key, {"last_post_id": None, "channel_id": str(channel_id)})
        return f"Deleted Lily’s last tracked post ({message_id}) from {channel_id}."


post_service = ChannelPostService()
