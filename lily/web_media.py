from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from pathlib import Path
from urllib.parse import urlencode

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from .config import settings


class WebSearch:
    async def search(self, query: str, limit: int | None = None) -> list[dict[str, str]]:
        query = query.strip()[:500]
        if not query:
            return []
        limit = max(1, min(limit or settings.web_search_max_results, 10))
        params = {"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"}
        if settings.web_search_api_key:
            params["key"] = settings.web_search_api_key
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=8.0), follow_redirects=True) as client:
            response = await client.get(settings.web_search_url, params=params, headers={"User-Agent": "LilyTelegramBot/1.0"})
            response.raise_for_status()
            data = response.json()
        results: list[dict[str, str]] = []
        abstract_url = data.get("AbstractURL")
        abstract = data.get("AbstractText")
        if abstract_url and abstract:
            results.append({"title": data.get("Heading") or query, "url": abstract_url, "snippet": abstract})
        def walk(items):
            for item in items or []:
                if item.get("FirstURL") and item.get("Text"):
                    yield {"title": item["Text"].split(" - ", 1)[0][:160], "url": item["FirstURL"], "snippet": item["Text"][:500]}
                yield from walk(item.get("Topics"))
        for item in walk(data.get("RelatedTopics")):
            if len(results) >= limit:
                break
            if item["url"] not in {row["url"] for row in results}:
                results.append(item)
        return results


class StreamLinks:
    def __init__(self) -> None:
        self._files: dict[str, tuple[Path, int, int]] = {}

    def _secret(self) -> bytes:
        secret = settings.stream_signing_secret or settings.bot_token
        if not secret:
            raise RuntimeError("Configure LILY_STREAM_SIGNING_SECRET or TELEGRAM_BOT_TOKEN first")
        return secret.encode()

    def create(self, path: Path, owner_id: int) -> str:
        path = path.resolve()
        allowed_roots = [settings.work_dir.resolve(), settings.download_dir.resolve()]
        if not any(path == root or root in path.parents for root in allowed_roots):
            raise PermissionError("Only Lily-managed files can receive streaming links.")
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(str(path))
        expires = int(time.time()) + settings.stream_link_ttl_seconds
        nonce = secrets.token_urlsafe(12)
        payload = f"{owner_id}.{expires}.{nonce}"
        signature = hmac.new(self._secret(), payload.encode(), hashlib.sha256).hexdigest()[:32]
        token = f"{payload}.{signature}"
        self._files[token] = (path, int(owner_id), expires)
        if not settings.stream_public_base_url:
            raise RuntimeError("Configure LILY_STREAM_PUBLIC_BASE_URL to generate public links.")
        return f"{settings.stream_public_base_url}/stream/{token}"

    def resolve(self, token: str) -> Path:
        record = self._files.get(token)
        if not record:
            raise KeyError(token)
        path, _owner_id, expires = record
        if expires < int(time.time()):
            self._files.pop(token, None)
            raise KeyError(token)
        parts = token.split(".")
        if len(parts) != 4:
            raise KeyError(token)
        payload = ".".join(parts[:3])
        expected = hmac.new(self._secret(), payload.encode(), hashlib.sha256).hexdigest()[:32]
        if not hmac.compare_digest(parts[3], expected) or not path.exists():
            raise KeyError(token)
        return path

    def app(self) -> FastAPI:
        app = FastAPI(title="Lily streaming service", docs_url=None, redoc_url=None)

        @app.get("/stream/{token}")
        async def stream(token: str):
            try:
                path = self.resolve(token)
            except KeyError:
                raise HTTPException(status_code=404, detail="Link expired or not found")
            return FileResponse(path, filename=path.name)

        @app.get("/health")
        async def health():
            return {"ok": True, "service": "lily-stream"}

        return app


web_search = WebSearch()
stream_links = StreamLinks()
