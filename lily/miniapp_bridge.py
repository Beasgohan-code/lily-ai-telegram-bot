"""Server-validated Telegram Mini App bridge for Lily.

The Mini App client is never trusted. Every protected request must include raw
Telegram ``initData`` and is verified with the bot token before a scoped user
identity reaches Lily's job/project queries.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl

from fastapi import HTTPException, Request

from .config import Settings, settings
from .db import Database, db


class MiniAppAuthError(ValueError):
    pass


@dataclass(frozen=True)
class MiniAppUser:
    id: int
    first_name: str
    username: str

    def public_dict(self) -> dict[str, object]:
        return {"id": self.id, "first_name": self.first_name, "username": self.username}


def validate_init_data(init_data: str, bot_token: str, max_age_seconds: int = 3600, now: int | None = None) -> MiniAppUser:
    """Verify Telegram Web App initData HMAC and return only the parsed user identity."""
    if not bot_token or not init_data or len(init_data) > 16_384:
        raise MiniAppAuthError("Missing Mini App authentication data.")
    try:
        pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=True)
    except ValueError as exc:
        raise MiniAppAuthError("Malformed Mini App authentication data.") from exc
    values: dict[str, str] = {}
    for key, value in pairs:
        if not key or key in values:
            raise MiniAppAuthError("Malformed Mini App authentication data.")
        values[key] = value
    supplied_hash = values.pop("hash", "")
    auth_date = values.get("auth_date", "")
    user_raw = values.get("user", "")
    if not supplied_hash or not auth_date or not user_raw:
        raise MiniAppAuthError("Incomplete Mini App authentication data.")
    try:
        authenticated_at = int(auth_date)
        current = int(time.time()) if now is None else int(now)
    except (TypeError, ValueError) as exc:
        raise MiniAppAuthError("Invalid Mini App authentication timestamp.") from exc
    if authenticated_at > current + 60 or current - authenticated_at > max(60, int(max_age_seconds)):
        raise MiniAppAuthError("Mini App authentication has expired. Reopen Lily from Telegram.")
    check_string = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    expected_hash = hmac.new(secret, check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_hash, supplied_hash):
        raise MiniAppAuthError("Mini App authentication could not be verified.")
    try:
        raw_user = json.loads(user_raw)
        user_id = int(raw_user["id"])
    except (TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        raise MiniAppAuthError("Mini App user identity is invalid.") from exc
    if user_id <= 0:
        raise MiniAppAuthError("Mini App user identity is invalid.")
    return MiniAppUser(user_id, str(raw_user.get("first_name") or "")[:128], str(raw_user.get("username") or "")[:64])


def _init_data(request: Request) -> str:
    header = request.headers.get("X-Telegram-Init-Data", "").strip()
    if header:
        return header
    authorization = request.headers.get("Authorization", "").strip()
    return authorization[4:].strip() if authorization.lower().startswith("tma ") else ""


def install_miniapp_routes(app: Any, database: Database = db, config: Settings = settings) -> None:
    """Attach minimal owner-scoped Mini App routes to Lily's existing FastAPI app."""
    async def user_from_request(request: Request) -> MiniAppUser:
        if not config.enable_miniapp_bridge:
            raise HTTPException(status_code=503, detail="Mini App bridge is disabled.")
        try:
            return validate_init_data(_init_data(request), config.bot_token, config.miniapp_init_data_ttl_seconds)
        except MiniAppAuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

    @app.get("/miniapp/health")
    async def miniapp_health():
        return {"ok": True, "bridge_enabled": config.enable_miniapp_bridge, "authentication": "telegram-init-data"}

    @app.get("/miniapp/v1/session")
    async def miniapp_session(request: Request):
        user = await user_from_request(request)
        return {"user": user.public_dict()}

    @app.get("/miniapp/v1/dashboard")
    async def miniapp_dashboard(request: Request):
        user = await user_from_request(request)
        jobs = await database.list_code_project_jobs_for_user(user.id, limit=20)
        projects = await database.list_managed_projects(user.id)
        return {
            "user": user.public_dict(),
            "code_project_jobs": [{key: job[key] for key in ("job_id", "chat_id", "project", "language", "state", "stage", "artifact_name", "file_count", "created_at", "started_at", "finished_at") if key in job} for job in jobs],
            "managed_projects": [{key: project[key] for key in ("slug", "runtime", "run_profile", "state", "revision", "updated_at") if key in project} for project in projects],
        }

    @app.post("/miniapp/v1/code-projects/{job_id}/cancel")
    async def cancel_code_project(job_id: str, request: Request):
        user = await user_from_request(request)
        accepted = await database.request_code_project_cancel_for_user(job_id, user.id)
        if not accepted:
            raise HTTPException(status_code=404, detail="No active code-project job was found for this Mini App user.")
        return {"ok": True, "job_id": job_id[:64], "state": "cancellation_requested"}
