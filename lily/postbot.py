from __future__ import annotations

import hashlib
import re
from typing import Any

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


class ChannelPostService:
    async def lookup_anime(self, title: str) -> dict[str, Any]:
        # Try the full title first, then the common cleaned-title variants used by anime filenames.
        candidates = [title.strip()]
        simplified = re.split(r"\s{2,}|\s+-\s+|:\s+|\s+\[", title, maxsplit=1)[0].strip()
        if simplified and simplified.lower() != title.strip().lower():
            candidates.append(simplified)
        item = None
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=8.0)) as client:
            for candidate in candidates:
                response = await client.post("https://graphql.anilist.co", json={"query": ANIME_QUERY, "variables": {"search": candidate}})
                response.raise_for_status()
                data = response.json()
                entries = data.get("data", {}).get("Page", {}).get("media", [])
                if entries:
                    item = entries[0]
                    break
        if not item:
            raise ValueError(f"I could not find anime metadata for {title!r}. Try another title or provide the fields manually.")
        title_data = item.get("title") or {}
        plot = re.sub(r"<[^>]+>", "", item.get("description") or "No synopsis available.").strip()
        next_episode = item.get("nextAiringEpisode") or {}
        studios = ", ".join(node.get("name", "") for node in (item.get("studios", {}).get("nodes", []) or []) if node.get("name"))
        return {
            "title": title_data.get("english") or title_data.get("romaji") or title_data.get("native") or title,
            "type": item.get("format") or item.get("type") or "TV",
            "rating": f"{(item.get('averageScore') or item.get('meanScore') or 0) / 10:.1f}/10" if (item.get("averageScore") or item.get("meanScore")) else "N/A",
            "status": str(item.get("status") or "Unknown").replace("_", " ").title(),
            "episodes": item.get("episodes") or (f"Next: {next_episode.get('episode')}" if next_episode.get("episode") else "Unknown"),
            "genres": ", ".join(item.get("genres") or []) or "Unknown",
            "plot": plot[:2500],
            "anilist_id": item.get("id"),
            "cover_url": (item.get("coverImage") or {}).get("large"),
            "site_url": item.get("siteUrl"),
            "studio": studios,
        }

    def announcement_blocks(self, anime: dict[str, Any], include_buttons: bool = True) -> list[dict[str, Any]]:
        blocks: list[dict[str, Any]] = [
            paragraph([bold(anime.get("title", "Anime announcement"))]),
            paragraph([bold("» Type: "), code(anime.get("type", "N/A"))]),
            paragraph([bold("» Average Rating: "), code(anime.get("rating", "N/A"))]),
            paragraph([bold("» Status: "), code(anime.get("status", "N/A"))]),
            paragraph([bold("» Episodes: "), code(str(anime.get("episodes", "N/A")))]),
            paragraph([bold("» Genre: "), anime.get("genres", "N/A")]),
            expandable_quote(anime.get("plot", "No synopsis available."), "Synopsis"),
        ]
        if include_buttons:
            blocks.append({
                "type": "buttons",
                "buttons": [
                    {"text": "More info", "style": "primary", "url": anime.get("site_url") or (f"https://anilist.co/anime/{anime.get('anilist_id')}" if anime.get("anilist_id") else "https://anilist.co/search/anime")},
                    {"text": "Share", "style": "link", "switch_inline_query": anime.get("title", "")},
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
