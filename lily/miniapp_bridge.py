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

from .agent import Plan, ai
from .agent_team import public_team_summary
from .config import Settings, settings
from .db import Database, db
from .group_controls import GROUP_CONTROL_MAP
from .rich import rich


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


def public_miniapp_plan(plan: Plan) -> dict[str, object]:
    """Return only the Mini App-safe display of a centrally enforced plan."""
    return {
        "intent": str(plan.intent or "")[:200],
        "summary": str(plan.summary or "")[:1000],
        "action": str(plan.action or "none")[:80],
        "risk": str(plan.risk or "safe")[:20],
        "requires_confirmation": bool(plan.requires_confirmation),
        "missing": [str(item)[:200] for item in plan.missing[:8]],
        "team": public_team_summary(plan),
        "execution": "Open Lily in Telegram to review and confirm any supported action.",
    }


def public_model_status(values: list[dict[str, Any]]) -> list[dict[str, object]]:
    """Expose availability, not provider endpoints, error text, or credentials."""
    return [
        {
            "name": str(value.get("name") or "AI model")[:100],
            "model": str(value.get("model") or "")[:120],
            "family": str(value.get("family") or "")[:60],
            "privacy_tier": str(value.get("privacy_tier") or "")[:40],
            "capabilities": [str(capability)[:40] for capability in value.get("capabilities", []) if isinstance(capability, str)][:12],
            "available": bool(value.get("available")),
        }
        for value in values[:12]
        if isinstance(value, dict)
    ]


def miniapp_owner_access(user: MiniAppUser, config: Settings) -> bool:
    """Owner authority comes only from a configured Telegram ID, never client data."""
    return bool(config.admin_user_ids) and user.id in config.admin_user_ids


def _safe_event_rows(events: list[dict[str, Any]]) -> list[dict[str, object]]:
    return [{"event": str(event.get("event") or "activity")[:80], "created_at": int(event.get("created_at") or 0)} for event in events[:12]]


async def _owner_panel_summary(database: Database) -> dict[str, int]:
    """Return owner-only aggregate counters; never enumerate another user’s work."""
    tables = ("chats", "managed_projects", "code_project_jobs", "audit_log")
    values: dict[str, int] = {}
    async with database.connect() as connection:
        for table in tables:
            row = await (await connection.execute(f"SELECT COUNT(*) AS count FROM {table}")).fetchone()
            values[table] = int(row["count"] if row else 0)
    return values


def install_miniapp_routes(app: Any, database: Database = db, config: Settings = settings) -> None:
    """Attach minimal owner-scoped Mini App routes to Lily's existing FastAPI app."""
    async def user_from_request(request: Request) -> MiniAppUser:
        if not config.enable_miniapp_bridge:
            raise HTTPException(status_code=503, detail="Mini App bridge is disabled.")
        try:
            return validate_init_data(_init_data(request), config.bot_token, config.miniapp_init_data_ttl_seconds)
        except MiniAppAuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

    async def group_admin_from_request(request: Request, chat_id: int) -> MiniAppUser:
        user = await user_from_request(request)
        if chat_id >= 0:
            raise HTTPException(status_code=400, detail="Provide a numeric group or supergroup chat ID.")
        try:
            membership = await rich.call("getChatMember", {"chat_id": chat_id, "user_id": user.id})
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Lily could not verify administrator access for this group.") from exc
        status = str(membership.get("status") or "") if isinstance(membership, dict) else ""
        if status not in {"creator", "administrator"}:
            raise HTTPException(status_code=403, detail="This signed Telegram user is not an administrator of that group.")
        return user

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
        models = public_model_status(await ai.status())
        return {
            "user": user.public_dict(),
            "code_project_jobs": [{key: job[key] for key in ("job_id", "chat_id", "project", "language", "state", "stage", "artifact_name", "file_count", "created_at", "started_at", "finished_at") if key in job} for job in jobs],
            "managed_projects": [{key: project[key] for key in ("slug", "runtime", "run_profile", "state", "revision", "updated_at") if key in project} for project in projects],
            "models": models,
            "ai_mode": "free-first configured routing" if any(item["available"] for item in models) else "no available configured model",
        }

    @app.get("/miniapp/v1/panel/owner")
    async def miniapp_owner_panel(request: Request):
        user = await user_from_request(request)
        if not miniapp_owner_access(user, config):
            raise HTTPException(status_code=403, detail="This signed Telegram user is not configured as a Lily owner.")
        models = public_model_status(await ai.status())
        return {
            "role": "owner",
            "user": user.public_dict(),
            "service": {
                "miniapp_bridge_enabled": bool(config.enable_miniapp_bridge),
                "agent_team_enabled": bool(config.enable_agent_team),
                "managed_supervisor_enabled": bool(config.enable_managed_service_supervisor),
                "configured_model_count": sum(1 for model in models if model["available"]),
                "group_control_count": len(GROUP_CONTROL_MAP),
            },
            "aggregates": await _owner_panel_summary(database),
            "models": models,
            "notice": "Owner panel is read-only. Start, stop, deployment, and group changes remain in Lily’s Telegram approval flow.",
        }

    @app.get("/miniapp/v1/panel/group")
    async def miniapp_group_admin_panel(request: Request, chat_id: int):
        user = await group_admin_from_request(request, chat_id)
        values = await database.get_chat_settings(chat_id)
        controls = await database.get_controls(chat_id)
        events = await database.recent_audit(chat_id, limit=12)
        reports = await database.list_reports(chat_id)
        filters = await database.list_filters(chat_id)
        pending = await database.list_pending_verifications(chat_id)
        return {
            "role": "group_admin",
            "user": user.public_dict(),
            "chat_id": chat_id,
            "summary": {
                "title": str(values.get("title") or "Group")[:160],
                "controls_enabled": sum(1 for enabled in controls.values() if enabled),
                "controls_total": len(GROUP_CONTROL_MAP),
                "open_reports": len(reports),
                "filters": len(filters),
                "pending_verifications": len(pending),
            },
            "controls": [{"key": key, "enabled": bool(controls.get(key, control.default_enabled)), "label": control.label, "risk": control.risk} for key, control in GROUP_CONTROL_MAP.items()],
            "recent_activity": _safe_event_rows(events),
            "notice": "This panel is read-only. Open Lily in Telegram to prepare and confirm any group change.",
        }

    @app.post("/miniapp/v1/assistant/preview")
    async def miniapp_assistant_preview(request: Request):
        user = await user_from_request(request)
        try:
            payload = await request.json()
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Provide a JSON request body.") from exc
        text = str(payload.get("text") or "").strip() if isinstance(payload, dict) else ""
        if not text:
            raise HTTPException(status_code=400, detail="Enter a request for Lily.")
        if len(text) > 3_500:
            raise HTTPException(status_code=400, detail="Keep the request under 3,500 characters.")
        try:
            plan = await ai.team_plan(
                text,
                {"chat_type": "private", "reply": {}, "requester_id": user.id, "origin": "miniapp"},
                [],
                {},
            )
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Lily AI is temporarily unavailable. Try again in Telegram shortly.") from exc
        return {"plan": public_miniapp_plan(plan)}

    @app.post("/miniapp/v1/code-projects/{job_id}/cancel")
    async def cancel_code_project(job_id: str, request: Request):
        user = await user_from_request(request)
        accepted = await database.request_code_project_cancel_for_user(job_id, user.id)
        if not accepted:
            raise HTTPException(status_code=404, detail="No active code-project job was found for this Mini App user.")
        return {"ok": True, "job_id": job_id[:64], "state": "cancellation_requested"}
