"""Conservative MangaDex metadata client.

This module deliberately supports only title and release-feed metadata. It does
not call MangaDex@Home, retrieve reader images, or download chapter content.
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from typing import Any

import httpx

from .config import Settings, settings


class MangaDexError(RuntimeError):
    pass


class MangaDexClient:
    BASE_URL = "https://api.mangadex.org"

    def __init__(self, configured: Settings = settings, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.settings = configured
        self._client = httpx.AsyncClient(base_url=self.BASE_URL, transport=transport, timeout=12.0, headers={"User-Agent": configured.mangadex_user_agent, "Accept": "application/json"})
        self._lock = asyncio.Lock()
        self._last_request = 0.0
        self._cache: OrderedDict[str, tuple[float, Any]] = OrderedDict()

    def _enabled(self) -> None:
        if not self.settings.enable_mangadex_metadata:
            raise MangaDexError("MangaDex metadata is disabled by host policy. Set LILY_ENABLE_MANGADEX_METADATA=true after reviewing the source rules.")
        if not self.settings.mangadex_user_agent.strip():
            raise MangaDexError("Set a truthful LILY_MANGADEX_USER_AGENT before enabling MangaDex metadata.")

    async def close(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        self._enabled()
        cache_key = f"{path}?{sorted(params.items())}"
        cached = self._cache.get(cache_key)
        now = time.monotonic()
        if cached and now - cached[0] < self.settings.mangadex_cache_seconds:
            return cached[1]
        async with self._lock:
            delay = self.settings.mangadex_min_interval_seconds - (time.monotonic() - self._last_request)
            if delay > 0:
                await asyncio.sleep(delay)
            response = await self._client.get(path, params=params)
            self._last_request = time.monotonic()
        if response.status_code == 429:
            retry = response.headers.get("X-RateLimit-Retry-After") or response.headers.get("Retry-After") or "later"
            raise MangaDexError(f"MangaDex rate limited this host. Lily paused this lookup; retry after {retry}.")
        if response.status_code >= 400:
            raise MangaDexError(f"MangaDex metadata request failed with HTTP {response.status_code}.")
        payload = response.json()
        self._cache[cache_key] = (time.monotonic(), payload)
        while len(self._cache) > 128:
            self._cache.popitem(last=False)
        return payload

    @staticmethod
    def _title(attributes: dict[str, Any]) -> str:
        titles = attributes.get("title") or {}
        if not isinstance(titles, dict):
            return "Untitled"
        return next((str(value) for value in titles.values() if value), "Untitled")

    async def search_titles(self, query: str, limit: int = 5) -> list[dict[str, str]]:
        value = query.strip()
        if not value:
            raise MangaDexError("Provide a title to search MangaDex metadata.")
        payload = await self._get("/manga", {"title": value, "limit": max(1, min(limit, 10)), "includes[]": ["author", "artist"]})
        results: list[dict[str, str]] = []
        for item in payload.get("data", []) if isinstance(payload, dict) else []:
            attributes = item.get("attributes") or {}
            results.append({"id": str(item.get("id", "")), "title": self._title(attributes), "status": str(attributes.get("status") or "unknown"), "year": str(attributes.get("year") or "—")})
        return results

    async def recent_chapters(self, manga_id: str, limit: int = 5) -> list[dict[str, str]]:
        if not manga_id or len(manga_id) > 80:
            raise MangaDexError("Provide a valid MangaDex title ID.")
        payload = await self._get(f"/manga/{manga_id}/feed", {"limit": max(1, min(limit, 10)), "order[readableAt]": "desc", "includes[]": "scanlation_group"})
        results: list[dict[str, str]] = []
        for item in payload.get("data", []) if isinstance(payload, dict) else []:
            attributes = item.get("attributes") or {}
            groups = [str(rel.get("attributes", {}).get("name")) for rel in item.get("relationships", []) if rel.get("type") == "scanlation_group" and rel.get("attributes", {}).get("name")]
            results.append({"id": str(item.get("id", "")), "chapter": str(attributes.get("chapter") or "—"), "title": str(attributes.get("title") or "—"), "language": str(attributes.get("translatedLanguage") or "—"), "groups": ", ".join(groups) or "—"})
        return results


mangadex = MangaDexClient()
