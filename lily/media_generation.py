from __future__ import annotations

from typing import Any

import httpx

from .config import settings


class MediaGeneration:
    async def _request(self, endpoint: str, api_key: str, payload: dict[str, Any]) -> str:
        if not endpoint:
            raise RuntimeError("This media-generation provider is not configured. Set the matching Lily provider URL and API key first.")
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        async with httpx.AsyncClient(timeout=httpx.Timeout(float(settings.media_generation_timeout), connect=12.0)) as client:
            response = await client.post(endpoint, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        for key in ("url", "output_url", "video_url", "image_url"):
            if isinstance(data.get(key), str) and data[key]:
                return data[key]
        items = data.get("data") or data.get("outputs") or []
        if isinstance(items, list) and items and isinstance(items[0], dict):
            for key in ("url", "output_url"):
                if isinstance(items[0].get(key), str):
                    return items[0][key]
        raise RuntimeError("The media provider responded without an output URL.")

    async def image(self, prompt: str, aspect_ratio: str = "1:1") -> str:
        return await self._request(settings.image_generation_url, settings.image_generation_api_key, {"prompt": prompt[:6000], "aspect_ratio": aspect_ratio, "kind": "image"})

    async def video(self, prompt: str, aspect_ratio: str = "16:9", duration_seconds: int = 8) -> str:
        return await self._request(settings.video_generation_url, settings.video_generation_api_key, {"prompt": prompt[:6000], "aspect_ratio": aspect_ratio, "duration_seconds": max(3, min(30, duration_seconds)), "kind": "video"})


media_generation = MediaGeneration()
