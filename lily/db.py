from __future__ import annotations

import json
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import aiosqlite

from .config import settings
from .group_controls import control_defaults


DEFAULT_SETTINGS: dict[str, Any] = {
    "personality": "friendly, concise, and helpful",
    "language": "English",
    "mention_only": True,
    "moderation_enabled": True,
    "welcome_enabled": True,
    "welcome_text": "Welcome {user} to {group}! Please read the rules.",
    "goodbye_enabled": False,
    "goodbye_text": "{user} left {group}.",
    "verification_prompt": "Tap the button below to confirm that you will follow this group’s rules.",
    "new_member_cooldown_seconds": 600,
    "warning_escalation": 3,
    "warning_escalation_seconds": 3600,
    "auto_rename_enabled": settings.auto_rename_enabled,
    "auto_rename_template": settings.auto_rename_template,
    "memory_enabled": False,
    "auto_confirm_safe": True,
    "daily_request_limit": settings.daily_request_limit,
    "monthly_request_limit": settings.monthly_request_limit,
    "daily_bytes_limit": settings.daily_bytes_limit,
    "monthly_bytes_limit": settings.monthly_bytes_limit,
    "controls": control_defaults(),
}


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        return max(minimum, min(int(value), maximum))
    except (TypeError, ValueError):
        return default


class Database:
    def __init__(self, path: str):
        self.path = path
        self._wal_ready = False

    @asynccontextmanager
    async def connect(self):
        db = await aiosqlite.connect(self.path)
        db.row_factory = aiosqlite.Row
        # WAL is a persistent database-file setting, so only issue the pragma
        # once; re-issuing it on every connection adds a round-trip per DB op.
        if not self._wal_ready:
            await db.execute("PRAGMA journal_mode=WAL")
            self._wal_ready = True
        await db.execute("PRAGMA busy_timeout=5000")
        await db.execute("PRAGMA foreign_keys=ON")
        try:
            yield db
        finally:
            await db.close()

    async def init(self) -> None:
        async with self.connect() as db:
            await db.executescript(
                """
                CREATE TABLE IF NOT EXISTS chats (
                    chat_id INTEGER PRIMARY KEY,
                    title TEXT NOT NULL DEFAULT '',
                    settings_json TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS usage (
                    scope TEXT NOT NULL,
                    scope_id TEXT NOT NULL,
                    day TEXT NOT NULL,
                    month TEXT NOT NULL,
                    requests INTEGER NOT NULL DEFAULT 0,
                    bytes_used INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (scope, scope_id, day, month)
                );
                CREATE TABLE IF NOT EXISTS pending_actions (
                    action_id TEXT PRIMARY KEY,
                    chat_id INTEGER NOT NULL,
                    requester_id INTEGER NOT NULL,
                    action_type TEXT NOT NULL,
                    plan_json TEXT NOT NULL,
                    expires_at INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at INTEGER NOT NULL,
                    completed_at INTEGER
                );
                CREATE TABLE IF NOT EXISTS skills (
                    id TEXT PRIMARY KEY,
                    chat_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    trigger_json TEXT NOT NULL,
                    action_json TEXT NOT NULL,
                    confirmation TEXT NOT NULL DEFAULT 'risky',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    cooldown_seconds INTEGER NOT NULL DEFAULT 0,
                    last_run_at INTEGER,
                    priority INTEGER NOT NULL DEFAULT 100,
                    execution_mode TEXT NOT NULL DEFAULT 'suggest',
                    created_by INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    UNIQUE(chat_id, name)
                );
                CREATE TABLE IF NOT EXISTS skill_runs (
                    id TEXT PRIMARY KEY,
                    skill_id TEXT NOT NULL,
                    chat_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    state TEXT NOT NULL,
                    detail TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL,
                    finished_at INTEGER
                );
                CREATE INDEX IF NOT EXISTS idx_skill_runs_chat_user_created ON skill_runs(chat_id, user_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scope_key TEXT NOT NULL,
                    user_id INTEGER,
                    chat_id INTEGER,
                    content TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER,
                    actor_id INTEGER,
                    event TEXT NOT NULL,
                    detail_json TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS provider_telemetry (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    model TEXT NOT NULL,
                    family TEXT NOT NULL,
                    privacy_tier TEXT NOT NULL,
                    successes INTEGER NOT NULL DEFAULT 0,
                    failures INTEGER NOT NULL DEFAULT 0,
                    prompt_tokens INTEGER NOT NULL DEFAULT 0,
                    completion_tokens INTEGER NOT NULL DEFAULT 0,
                    error_classes_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS warnings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    reason TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS filters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    trigger TEXT NOT NULL,
                    response TEXT,
                    delete_message INTEGER NOT NULL DEFAULT 1,
                    warn INTEGER NOT NULL DEFAULT 0,
                    created_by INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    UNIQUE(chat_id, trigger)
                );
                CREATE TABLE IF NOT EXISTS locks (
                    chat_id INTEGER NOT NULL,
                    content_type TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at INTEGER NOT NULL,
                    PRIMARY KEY(chat_id, content_type)
                );
                CREATE TABLE IF NOT EXISTS notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_by INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    UNIQUE(chat_id, name)
                );
                CREATE TABLE IF NOT EXISTS indexed_posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id TEXT NOT NULL,
                    message_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    link TEXT,
                    created_at INTEGER NOT NULL,
                    UNIQUE(channel_id, message_id)
                );
                CREATE TABLE IF NOT EXISTS encoding_jobs (
                    job_id TEXT PRIMARY KEY,
                    chat_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    plan_json TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'queued',
                    progress TEXT NOT NULL DEFAULT '',
                    error TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL,
                    started_at INTEGER,
                    finished_at INTEGER
                );
                CREATE TABLE IF NOT EXISTS code_project_jobs (
                    job_id TEXT PRIMARY KEY,
                    chat_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    project TEXT NOT NULL,
                    language TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'queued',
                    stage TEXT NOT NULL DEFAULT '',
                    artifact_name TEXT NOT NULL DEFAULT '',
                    file_count INTEGER NOT NULL DEFAULT 0,
                    error TEXT NOT NULL DEFAULT '',
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    created_at INTEGER NOT NULL,
                    started_at INTEGER,
                    finished_at INTEGER
                );
                CREATE INDEX IF NOT EXISTS idx_code_project_jobs_chat_user_created ON code_project_jobs(chat_id, user_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS trusted_members (
                    chat_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    added_by INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    PRIMARY KEY(chat_id, user_id)
                );
                CREATE TABLE IF NOT EXISTS blocked_domains (
                    chat_id INTEGER NOT NULL,
                    domain TEXT NOT NULL,
                    created_by INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    PRIMARY KEY(chat_id, domain)
                );
                CREATE TABLE IF NOT EXISTS moderation_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    reporter_id INTEGER NOT NULL,
                    target_user_id INTEGER,
                    reason TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    created_at INTEGER NOT NULL,
                    resolved_at INTEGER
                );
                CREATE TABLE IF NOT EXISTS case_notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    report_id INTEGER,
                    target_user_id INTEGER,
                    author_id INTEGER NOT NULL,
                    note TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS member_intake (
                    chat_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    joined_at INTEGER NOT NULL,
                    verification_status TEXT NOT NULL DEFAULT 'not_required',
                    verified_at INTEGER,
                    PRIMARY KEY(chat_id, user_id)
                );
                CREATE TABLE IF NOT EXISTS stream_links (
                    token TEXT PRIMARY KEY,
                    path TEXT NOT NULL,
                    owner_id INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_stream_links_expires_at ON stream_links(expires_at);
                CREATE TABLE IF NOT EXISTS managed_projects (
                    slug TEXT PRIMARY KEY,
                    repository_url TEXT NOT NULL,
                    branch TEXT NOT NULL DEFAULT 'main',
                    runtime TEXT NOT NULL,
                    run_profile TEXT NOT NULL,
                    run_target TEXT NOT NULL DEFAULT '',
                    project_root TEXT NOT NULL,
                    env_path TEXT NOT NULL,
                    owner_id INTEGER NOT NULL,
                    state TEXT NOT NULL DEFAULT 'registered',
                    revision TEXT NOT NULL DEFAULT '',
                    last_error TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS managed_project_env (
                    project_slug TEXT NOT NULL,
                    name TEXT NOT NULL,
                    required INTEGER NOT NULL DEFAULT 0,
                    secret INTEGER NOT NULL DEFAULT 1,
                    default_value TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',
                    validation TEXT NOT NULL DEFAULT 'text',
                    PRIMARY KEY(project_slug, name),
                    FOREIGN KEY(project_slug) REFERENCES managed_projects(slug) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS tracked_series (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    normalized_title TEXT NOT NULL,
                    media_type TEXT NOT NULL DEFAULT 'manga',
                    last_chapter TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'tracking',
                    target_channel_id TEXT NOT NULL DEFAULT '',
                    created_by INTEGER NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    UNIQUE(chat_id, normalized_title)
                );
                """
            )
            columns = {str(row["name"]) for row in await (await db.execute("PRAGMA table_info(managed_projects)")).fetchall()}
            if "run_target" not in columns:
                await db.execute("ALTER TABLE managed_projects ADD COLUMN run_target TEXT NOT NULL DEFAULT ''")
            skill_columns = {str(row["name"]) for row in await (await db.execute("PRAGMA table_info(skills)")).fetchall()}
            if "priority" not in skill_columns:
                await db.execute("ALTER TABLE skills ADD COLUMN priority INTEGER NOT NULL DEFAULT 100")
            if "execution_mode" not in skill_columns:
                await db.execute("ALTER TABLE skills ADD COLUMN execution_mode TEXT NOT NULL DEFAULT 'suggest'")
            await db.commit()

    async def get_chat_settings(self, chat_id: int, title: str = "") -> dict[str, Any]:
        async with self.connect() as db:
            row = await (await db.execute("SELECT settings_json FROM chats WHERE chat_id=?", (chat_id,))).fetchone()
            now = int(time.time())
            if row is None:
                values = dict(DEFAULT_SETTINGS)
                await db.execute(
                    "INSERT INTO chats(chat_id,title,settings_json,created_at,updated_at) VALUES(?,?,?,?,?)",
                    (chat_id, title, json.dumps(values), now, now),
                )
                await db.commit()
                return values
            try:
                values = json.loads(row["settings_json"])
            except json.JSONDecodeError:
                values = dict(DEFAULT_SETTINGS)
            merged = {**DEFAULT_SETTINGS, **values}
            merged["controls"] = {**DEFAULT_SETTINGS["controls"], **(values.get("controls") if isinstance(values.get("controls"), dict) else {})}
            return merged

    async def update_chat_settings(self, chat_id: int, patch: dict[str, Any], title: str = "") -> dict[str, Any]:
        current = await self.get_chat_settings(chat_id, title)
        controls_patch = patch.pop("controls", None) if "controls" in patch else None
        current.update(patch)
        if isinstance(controls_patch, dict):
            current["controls"] = {**current.get("controls", {}), **controls_patch}
        async with self.connect() as db:
            await db.execute(
                "UPDATE chats SET settings_json=?,title=?,updated_at=? WHERE chat_id=?",
                (json.dumps(current), title, int(time.time()), chat_id),
            )
            await db.commit()
        return current

    async def set_control(self, chat_id: int, key: str, enabled: bool, title: str = "") -> dict[str, Any]:
        return await self.update_chat_settings(chat_id, {"controls": {key: bool(enabled)}}, title)

    async def get_controls(self, chat_id: int, title: str = "") -> dict[str, bool]:
        values = await self.get_chat_settings(chat_id, title)
        return dict(values.get("controls", {}))

    async def set_trusted_member(self, chat_id: int, user_id: int, actor_id: int, trusted: bool) -> bool:
        async with self.connect() as db:
            if trusted:
                await db.execute("INSERT INTO trusted_members(chat_id,user_id,added_by,created_at) VALUES(?,?,?,?) ON CONFLICT(chat_id,user_id) DO UPDATE SET added_by=excluded.added_by", (chat_id, user_id, actor_id, int(time.time())))
                await db.commit()
                return True
            cursor = await db.execute("DELETE FROM trusted_members WHERE chat_id=? AND user_id=?", (chat_id, user_id))
            await db.commit()
            return cursor.rowcount == 1

    async def is_trusted_member(self, chat_id: int, user_id: int) -> bool:
        async with self.connect() as db:
            row = await (await db.execute("SELECT 1 FROM trusted_members WHERE chat_id=? AND user_id=?", (chat_id, user_id))).fetchone()
            return row is not None

    async def list_trusted_members(self, chat_id: int) -> list[dict[str, Any]]:
        async with self.connect() as db:
            rows = await (await db.execute("SELECT * FROM trusted_members WHERE chat_id=? ORDER BY created_at", (chat_id,))).fetchall()
            return [dict(row) for row in rows]

    async def set_blocked_domain(self, chat_id: int, domain: str, actor_id: int, blocked: bool) -> bool:
        cleaned = domain.lower().replace("https://", "").replace("http://", "").split("/")[0].strip()
        if not cleaned:
            return False
        async with self.connect() as db:
            if blocked:
                await db.execute("INSERT INTO blocked_domains(chat_id,domain,created_by,created_at) VALUES(?,?,?,?) ON CONFLICT(chat_id,domain) DO UPDATE SET created_by=excluded.created_by", (chat_id, cleaned, actor_id, int(time.time())))
                await db.commit()
                return True
            cursor = await db.execute("DELETE FROM blocked_domains WHERE chat_id=? AND domain=?", (chat_id, cleaned))
            await db.commit()
            return cursor.rowcount == 1

    async def list_blocked_domains(self, chat_id: int) -> list[str]:
        async with self.connect() as db:
            rows = await (await db.execute("SELECT domain FROM blocked_domains WHERE chat_id=? ORDER BY domain", (chat_id,))).fetchall()
            return [str(row["domain"]) for row in rows]

    async def create_report(self, chat_id: int, reporter_id: int, target_user_id: int | None, reason: str) -> int:
        async with self.connect() as db:
            cursor = await db.execute("INSERT INTO moderation_reports(chat_id,reporter_id,target_user_id,reason,created_at) VALUES(?,?,?,?,?)", (chat_id, reporter_id, target_user_id, reason[:1000], int(time.time())))
            await db.commit()
            return int(cursor.lastrowid)

    async def list_reports(self, chat_id: int, status: str = "open", limit: int = 30) -> list[dict[str, Any]]:
        async with self.connect() as db:
            rows = await (await db.execute("SELECT * FROM moderation_reports WHERE chat_id=? AND status=? ORDER BY id DESC LIMIT ?", (chat_id, status, limit))).fetchall()
            return [dict(row) for row in rows]

    async def resolve_report(self, chat_id: int, report_id: int) -> bool:
        async with self.connect() as db:
            cursor = await db.execute("UPDATE moderation_reports SET status='resolved',resolved_at=? WHERE chat_id=? AND id=? AND status='open'", (int(time.time()), chat_id, report_id))
            await db.commit()
            return cursor.rowcount == 1

    async def add_case_note(self, chat_id: int, author_id: int, note: str, report_id: int | None = None, target_user_id: int | None = None) -> int:
        async with self.connect() as db:
            cursor = await db.execute(
                "INSERT INTO case_notes(chat_id,report_id,target_user_id,author_id,note,created_at) VALUES(?,?,?,?,?,?)",
                (chat_id, report_id, target_user_id, author_id, note[:2000], int(time.time())),
            )
            await db.commit()
            return int(cursor.lastrowid)

    async def list_case_notes(self, chat_id: int, report_id: int | None = None, limit: int = 30) -> list[dict[str, Any]]:
        async with self.connect() as db:
            if report_id is None:
                rows = await (await db.execute("SELECT * FROM case_notes WHERE chat_id=? ORDER BY id DESC LIMIT ?", (chat_id, limit))).fetchall()
            else:
                rows = await (await db.execute("SELECT * FROM case_notes WHERE chat_id=? AND report_id=? ORDER BY id DESC LIMIT ?", (chat_id, report_id, limit))).fetchall()
            return [dict(row) for row in rows]

    async def record_member_join(self, chat_id: int, user_id: int, requires_verification: bool) -> None:
        status = "pending" if requires_verification else "not_required"
        async with self.connect() as db:
            await db.execute(
                "INSERT INTO member_intake(chat_id,user_id,joined_at,verification_status,verified_at) VALUES(?,?,?,?,NULL) "
                "ON CONFLICT(chat_id,user_id) DO UPDATE SET joined_at=excluded.joined_at,verification_status=excluded.verification_status,verified_at=NULL",
                (chat_id, user_id, int(time.time()), status),
            )
            await db.commit()

    async def member_joined_at(self, chat_id: int, user_id: int) -> int | None:
        async with self.connect() as db:
            row = await (await db.execute("SELECT joined_at FROM member_intake WHERE chat_id=? AND user_id=?", (chat_id, user_id))).fetchone()
            return int(row["joined_at"]) if row else None

    async def complete_verification(self, chat_id: int, user_id: int) -> bool:
        async with self.connect() as db:
            cursor = await db.execute(
                "UPDATE member_intake SET verification_status='verified',verified_at=? WHERE chat_id=? AND user_id=? AND verification_status='pending'",
                (int(time.time()), chat_id, user_id),
            )
            await db.commit()
            return cursor.rowcount == 1

    async def list_pending_verifications(self, chat_id: int, limit: int = 30) -> list[dict[str, Any]]:
        async with self.connect() as db:
            rows = await (await db.execute(
                "SELECT * FROM member_intake WHERE chat_id=? AND verification_status='pending' ORDER BY joined_at DESC LIMIT ?",
                (chat_id, limit),
            )).fetchall()
            return [dict(row) for row in rows]

    async def save_stream_link(self, token: str, path: str, owner_id: int, expires_at: int) -> None:
        async with self.connect() as db:
            await db.execute(
                "INSERT OR REPLACE INTO stream_links(token,path,owner_id,expires_at,created_at) VALUES(?,?,?,?,?)",
                (token, path, owner_id, expires_at, int(time.time())),
            )
            await db.execute("DELETE FROM stream_links WHERE expires_at<?", (int(time.time()),))
            await db.commit()

    async def get_stream_link(self, token: str) -> dict[str, Any] | None:
        async with self.connect() as db:
            row = await (await db.execute("SELECT * FROM stream_links WHERE token=?", (token,))).fetchone()
            return dict(row) if row else None

    async def delete_stream_link(self, token: str) -> None:
        async with self.connect() as db:
            await db.execute("DELETE FROM stream_links WHERE token=?", (token,))
            await db.commit()

    async def clear_warnings(self, chat_id: int, user_id: int) -> int:
        async with self.connect() as db:
            cursor = await db.execute("DELETE FROM warnings WHERE chat_id=? AND user_id=?", (chat_id, user_id))
            await db.commit()
            return cursor.rowcount

    async def recent_audit(self, chat_id: int, limit: int = 50) -> list[dict[str, Any]]:
        async with self.connect() as db:
            rows = await (await db.execute("SELECT * FROM audit_log WHERE chat_id=? ORDER BY id DESC LIMIT ?", (chat_id, limit))).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                try:
                    item["detail"] = json.loads(item.pop("detail_json"))
                except json.JSONDecodeError:
                    item["detail"] = {}
                result.append(item)
            return result

    async def list_known_group_chats(self, limit: int = 30) -> list[dict[str, Any]]:
        """Return bounded locally known group chat records for membership verification."""
        bounded = max(1, min(int(limit), 30))
        async with self.connect() as db:
            rows = await (await db.execute(
                "SELECT chat_id,title,updated_at FROM chats WHERE chat_id<0 ORDER BY updated_at DESC LIMIT ?",
                (bounded,),
            )).fetchall()
            return [dict(row) for row in rows]

    async def _usage(self, scope: str, scope_id: int, field: str, amount: int, daily: int, monthly: int) -> tuple[bool, str]:
        now = time.gmtime()
        day = time.strftime("%Y-%m-%d", now)
        month = time.strftime("%Y-%m", now)
        async with self.connect() as db:
            row = await (await db.execute(
                "SELECT requests,bytes_used FROM usage WHERE scope=? AND scope_id=? AND day=? AND month=?",
                (scope, str(scope_id), day, month),
            )).fetchone()
            requests = int(row["requests"]) if row else 0
            bytes_used = int(row["bytes_used"]) if row else 0
            if field == "requests" and requests + amount > daily:
                return False, f"daily {scope} request limit reached ({daily})"
            if field == "bytes_used" and bytes_used + amount > daily:
                return False, f"daily {scope} file limit reached ({daily} bytes)"
            # The same row is monthly-keyed, so the monthly quota is enforced by summing its month rows.
            month_row = await (await db.execute(
                "SELECT COALESCE(SUM(requests),0) AS requests, COALESCE(SUM(bytes_used),0) AS bytes_used "
                "FROM usage WHERE scope=? AND scope_id=? AND month=?",
                (scope, str(scope_id), month),
            )).fetchone()
            month_value = int(month_row[field]) if month_row else 0
            if month_value + amount > monthly:
                return False, f"monthly {scope} limit reached ({monthly})"
            await db.execute(
                "INSERT INTO usage(scope,scope_id,day,month,requests,bytes_used) VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(scope,scope_id,day,month) DO UPDATE SET requests=requests+excluded.requests, bytes_used=bytes_used+excluded.bytes_used",
                (scope, str(scope_id), day, month, amount if field == "requests" else 0, amount if field == "bytes_used" else 0),
            )
            await db.commit()
            return True, "ok"

    async def charge_request(self, user_id: int, chat_id: int, amount: int = 1) -> tuple[bool, str]:
        settings_for_chat = await self.get_chat_settings(chat_id)
        ok, reason = await self._usage("user", user_id, "requests", amount, int(settings_for_chat["daily_request_limit"]), int(settings_for_chat["monthly_request_limit"]))
        if not ok:
            return ok, reason
        return await self._usage("chat", chat_id, "requests", amount, int(settings_for_chat["daily_request_limit"]), int(settings_for_chat["monthly_request_limit"]))

    async def charge_bytes(self, user_id: int, chat_id: int, amount: int) -> tuple[bool, str]:
        settings_for_chat = await self.get_chat_settings(chat_id)
        ok, reason = await self._usage("user", user_id, "bytes_used", amount, int(settings_for_chat["daily_bytes_limit"]), int(settings_for_chat["monthly_bytes_limit"]))
        if not ok:
            return ok, reason
        return await self._usage("chat", chat_id, "bytes_used", amount, int(settings_for_chat["daily_bytes_limit"]), int(settings_for_chat["monthly_bytes_limit"]))

    async def usage_summary(self, user_id: int, chat_id: int) -> dict[str, int]:
        now = time.gmtime()
        day = time.strftime("%Y-%m-%d", now)
        month = time.strftime("%Y-%m", now)
        result: dict[str, int] = {}
        async with self.connect() as db:
            for scope, sid in (("user", user_id), ("chat", chat_id)):
                row = await (await db.execute(
                    "SELECT COALESCE(SUM(requests),0) AS requests, COALESCE(SUM(bytes_used),0) AS bytes_used "
                    "FROM usage WHERE scope=? AND scope_id=? AND month=?",
                    (scope, str(sid), month),
                )).fetchone()
                today = await (await db.execute(
                    "SELECT requests,bytes_used FROM usage WHERE scope=? AND scope_id=? AND day=? AND month=?",
                    (scope, str(sid), day, month),
                )).fetchone()
                prefix = "user" if scope == "user" else "chat"
                result[f"{prefix}_monthly_requests"] = int(row["requests"])
                result[f"{prefix}_monthly_bytes"] = int(row["bytes_used"])
                result[f"{prefix}_daily_requests"] = int(today["requests"]) if today else 0
                result[f"{prefix}_daily_bytes"] = int(today["bytes_used"]) if today else 0
        return result

    async def create_pending(self, chat_id: int, requester_id: int, action_type: str, plan: dict[str, Any], ttl: int) -> str:
        action_id = uuid.uuid4().hex
        now = int(time.time())
        async with self.connect() as db:
            await db.execute(
                "INSERT INTO pending_actions(action_id,chat_id,requester_id,action_type,plan_json,expires_at,created_at) VALUES(?,?,?,?,?,?,?)",
                (action_id, chat_id, requester_id, action_type, json.dumps(plan), now + ttl, now),
            )
            await db.commit()
        return action_id

    async def get_pending(self, action_id: str) -> dict[str, Any] | None:
        async with self.connect() as db:
            row = await (await db.execute("SELECT * FROM pending_actions WHERE action_id=?", (action_id,))).fetchone()
            if row is None:
                return None
            result = dict(row)
            result["plan"] = json.loads(result.pop("plan_json"))
            return result

    async def finish_pending(self, action_id: str, status: str) -> bool:
        async with self.connect() as db:
            cursor = await db.execute(
                "UPDATE pending_actions SET status=?,completed_at=? WHERE action_id=? AND status='pending'",
                (status, int(time.time()), action_id),
            )
            await db.commit()
            return cursor.rowcount == 1

    async def save_skill(self, chat_id: int, created_by: int, name: str, trigger: dict[str, Any], action: dict[str, Any], confirmation: str = "risky", cooldown_seconds: int = 0, priority: int = 100, execution_mode: str = "suggest") -> str:
        skill_id = uuid.uuid4().hex
        confirmation = confirmation if confirmation in {"never", "risky", "always"} else "risky"
        execution_mode = execution_mode if execution_mode in {"auto", "suggest"} else "suggest"
        async with self.connect() as db:
            await db.execute(
                "INSERT INTO skills(id,chat_id,name,trigger_json,action_json,confirmation,cooldown_seconds,priority,execution_mode,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (skill_id, chat_id, name[:80], json.dumps(trigger), json.dumps(action), confirmation, _bounded_int(cooldown_seconds, 0, 0, 86_400), _bounded_int(priority, 100, 0, 1000), execution_mode, created_by, int(time.time())),
            )
            await db.commit()
        return skill_id

    async def list_skills(self, chat_id: int) -> list[dict[str, Any]]:
        async with self.connect() as db:
            rows = await (await db.execute("SELECT * FROM skills WHERE chat_id=? ORDER BY enabled DESC, priority DESC, created_at", (chat_id,))).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                item["trigger"] = json.loads(item.pop("trigger_json"))
                item["action"] = json.loads(item.pop("action_json"))
                result.append(item)
            return result

    async def claim_skill_run(self, skill_id: str, cooldown_seconds: int, now: int | None = None) -> bool:
        """Atomically reserve a trigger slot so a cooldown cannot be bypassed by duplicate updates."""
        timestamp = int(time.time()) if now is None else int(now)
        cooldown = _bounded_int(cooldown_seconds, 0, 0, 86_400)
        async with self.connect() as db:
            cursor = await db.execute(
                "UPDATE skills SET last_run_at=? WHERE id=? AND enabled=1 AND (last_run_at IS NULL OR last_run_at + ? <= ?)",
                (timestamp, skill_id, cooldown, timestamp),
            )
            await db.commit()
            return cursor.rowcount == 1

    async def create_skill_run(self, skill_id: str, chat_id: int, user_id: int, action: str, state: str, detail: str = "") -> str:
        run_id = uuid.uuid4().hex
        async with self.connect() as db:
            await db.execute(
                "INSERT INTO skill_runs(id,skill_id,chat_id,user_id,action,state,detail,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (run_id, skill_id, chat_id, user_id, action[:80], state[:32], detail[:500], int(time.time())),
            )
            await db.commit()
        return run_id

    async def finish_skill_run(self, run_id: str, state: str, detail: str = "") -> None:
        async with self.connect() as db:
            await db.execute(
                "UPDATE skill_runs SET state=?, detail=?, finished_at=? WHERE id=?",
                (state[:32], detail[:500], int(time.time()), run_id),
            )
            await db.commit()

    async def list_skill_runs(self, chat_id: int, user_id: int | None = None, limit: int = 20) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 100))
        async with self.connect() as db:
            if user_id is None:
                rows = await (await db.execute("SELECT * FROM skill_runs WHERE chat_id=? ORDER BY created_at DESC LIMIT ?", (chat_id, limit))).fetchall()
            else:
                rows = await (await db.execute("SELECT * FROM skill_runs WHERE chat_id=? AND user_id=? ORDER BY created_at DESC LIMIT ?", (chat_id, user_id, limit))).fetchall()
            return [dict(row) for row in rows]

    async def create_code_project_job(self, chat_id: int, user_id: int, project: str, language: str) -> str:
        job_id = uuid.uuid4().hex
        async with self.connect() as db:
            await db.execute(
                "INSERT INTO code_project_jobs(job_id,chat_id,user_id,project,language,created_at) VALUES(?,?,?,?,?,?)",
                (job_id, chat_id, user_id, project[:63], language[:32], int(time.time())),
            )
            await db.commit()
        return job_id

    async def start_code_project_job(self, job_id: str) -> bool:
        async with self.connect() as db:
            cursor = await db.execute(
                "UPDATE code_project_jobs SET state='running',stage='Preparing isolated workspace',started_at=? WHERE job_id=? AND state='queued' AND cancel_requested=0",
                (int(time.time()), job_id),
            )
            await db.commit()
            return cursor.rowcount == 1

    async def update_code_project_job(self, job_id: str, stage: str) -> None:
        async with self.connect() as db:
            await db.execute("UPDATE code_project_jobs SET stage=? WHERE job_id=? AND state='running'", (stage[:300], job_id))
            await db.commit()

    async def code_project_cancelled(self, job_id: str) -> bool:
        async with self.connect() as db:
            row = await (await db.execute("SELECT cancel_requested FROM code_project_jobs WHERE job_id=?", (job_id,))).fetchone()
            return bool(row and row["cancel_requested"])

    async def request_code_project_cancel(self, job_id: str, chat_id: int, user_id: int) -> bool:
        async with self.connect() as db:
            cursor = await db.execute(
                "UPDATE code_project_jobs SET cancel_requested=1,state=CASE WHEN state='queued' THEN 'cancelled' ELSE state END,stage=CASE WHEN state='queued' THEN 'Cancelled before execution' ELSE stage END,finished_at=CASE WHEN state='queued' THEN ? ELSE finished_at END WHERE job_id=? AND chat_id=? AND user_id=? AND state IN ('queued','running')",
                (int(time.time()), job_id, chat_id, user_id),
            )
            await db.commit()
            return cursor.rowcount == 1

    async def finish_code_project_job(self, job_id: str, state: str, stage: str, *, artifact_name: str = "", file_count: int = 0, error: str = "") -> None:
        final_state = state if state in {"completed", "cancelled", "failed"} else "failed"
        async with self.connect() as db:
            await db.execute(
                "UPDATE code_project_jobs SET state=?,stage=?,artifact_name=?,file_count=?,error=?,finished_at=? WHERE job_id=?",
                (final_state, stage[:300], artifact_name[:160], max(0, min(int(file_count), 200)), error[:500], int(time.time()), job_id),
            )
            await db.commit()

    async def get_code_project_job(self, job_id: str, chat_id: int, user_id: int) -> dict[str, Any] | None:
        async with self.connect() as db:
            row = await (await db.execute("SELECT * FROM code_project_jobs WHERE job_id=? AND chat_id=? AND user_id=?", (job_id, chat_id, user_id))).fetchone()
            return dict(row) if row else None

    async def list_code_project_jobs(self, chat_id: int, user_id: int, limit: int = 10) -> list[dict[str, Any]]:
        bounded = max(1, min(int(limit), 50))
        async with self.connect() as db:
            rows = await (await db.execute("SELECT * FROM code_project_jobs WHERE chat_id=? AND user_id=? ORDER BY created_at DESC LIMIT ?", (chat_id, user_id, bounded))).fetchall()
            return [dict(row) for row in rows]

    async def list_code_project_jobs_for_user(self, user_id: int, limit: int = 20) -> list[dict[str, Any]]:
        bounded = max(1, min(int(limit), 50))
        async with self.connect() as db:
            rows = await (await db.execute("SELECT * FROM code_project_jobs WHERE user_id=? ORDER BY created_at DESC LIMIT ?", (user_id, bounded))).fetchall()
            return [dict(row) for row in rows]

    async def request_code_project_cancel_for_user(self, job_id: str, user_id: int) -> bool:
        async with self.connect() as db:
            cursor = await db.execute(
                "UPDATE code_project_jobs SET cancel_requested=1,state=CASE WHEN state='queued' THEN 'cancelled' ELSE state END,stage=CASE WHEN state='queued' THEN 'Cancelled before execution' ELSE stage END,finished_at=CASE WHEN state='queued' THEN ? ELSE finished_at END WHERE job_id=? AND user_id=? AND state IN ('queued','running')",
                (int(time.time()), job_id, user_id),
            )
            await db.commit()
            return cursor.rowcount == 1

    async def add_warning(self, chat_id: int, user_id: int, reason: str) -> int:
        async with self.connect() as db:
            await db.execute("INSERT INTO warnings(chat_id,user_id,reason,created_at) VALUES(?,?,?,?)", (chat_id, user_id, reason[:500], int(time.time())))
            row = await (await db.execute("SELECT COUNT(*) AS count FROM warnings WHERE chat_id=? AND user_id=?", (chat_id, user_id))).fetchone()
            await db.commit()
            return int(row["count"])

    async def warning_count(self, chat_id: int, user_id: int) -> int:
        async with self.connect() as db:
            row = await (await db.execute("SELECT COUNT(*) AS count FROM warnings WHERE chat_id=? AND user_id=?", (chat_id, user_id))).fetchone()
            return int(row["count"])

    async def save_filter(self, chat_id: int, created_by: int, trigger: str, response: str = "", delete_message: bool = True, warn: bool = False) -> None:
        async with self.connect() as db:
            await db.execute("INSERT INTO filters(chat_id,trigger,response,delete_message,warn,created_by,created_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(chat_id,trigger) DO UPDATE SET response=excluded.response,delete_message=excluded.delete_message,warn=excluded.warn", (chat_id, trigger.lower()[:200], response[:500], int(delete_message), int(warn), created_by, int(time.time())))
            await db.commit()

    async def list_filters(self, chat_id: int) -> list[dict[str, Any]]:
        async with self.connect() as db:
            rows = await (await db.execute("SELECT * FROM filters WHERE chat_id=? ORDER BY id", (chat_id,))).fetchall()
            return [dict(row) for row in rows]

    async def delete_filter(self, chat_id: int, trigger: str) -> bool:
        async with self.connect() as db:
            cursor = await db.execute("DELETE FROM filters WHERE chat_id=? AND trigger=?", (chat_id, trigger.lower()))
            await db.commit()
            return cursor.rowcount == 1

    async def list_warnings(self, chat_id: int, user_id: int, limit: int = 10) -> list[dict[str, Any]]:
        async with self.connect() as db:
            rows = await (await db.execute("SELECT * FROM warnings WHERE chat_id=? AND user_id=? ORDER BY id DESC LIMIT ?", (chat_id, user_id, limit))).fetchall()
            return [dict(row) for row in rows]

    async def list_warnings_pending(self, chat_id: int, limit: int = 50) -> list[dict[str, Any]]:
        """Return per-user warning counts only, for inbox views (redacted)."""
        async with self.connect() as db:
            rows = await (await db.execute(
                "SELECT user_id, COUNT(*) AS warning_count, MAX(rowid) AS last_warning_id FROM warnings WHERE chat_id=? GROUP BY user_id ORDER BY warning_count DESC LIMIT ?",
                (chat_id, max(1, min(int(limit), 200))),
            )).fetchall()
            return [{"user_id": row["user_id"], "warning_count": row["warning_count"], "last_warning_id": row["last_warning_id"]} for row in rows]

    async def set_lock(self, chat_id: int, content_type: str, enabled: bool) -> None:
        async with self.connect() as db:
            await db.execute("INSERT INTO locks(chat_id,content_type,enabled,created_at) VALUES(?,?,?,?) ON CONFLICT(chat_id,content_type) DO UPDATE SET enabled=excluded.enabled", (chat_id, content_type.lower(), int(enabled), int(time.time())))
            await db.commit()

    async def get_locks(self, chat_id: int) -> dict[str, bool]:
        async with self.connect() as db:
            rows = await (await db.execute("SELECT content_type,enabled FROM locks WHERE chat_id=?", (chat_id,))).fetchall()
            return {row["content_type"]: bool(row["enabled"]) for row in rows}

    async def save_note(self, chat_id: int, created_by: int, name: str, content: str) -> None:
        async with self.connect() as db:
            await db.execute("INSERT INTO notes(chat_id,name,content,created_by,created_at) VALUES(?,?,?,?,?) ON CONFLICT(chat_id,name) DO UPDATE SET content=excluded.content,created_by=excluded.created_by", (chat_id, name.lower()[:100], content[:4000], created_by, int(time.time())))
            await db.commit()

    async def get_notes(self, chat_id: int, name: str | None = None) -> list[dict[str, Any]]:
        async with self.connect() as db:
            if name:
                rows = await (await db.execute("SELECT * FROM notes WHERE chat_id=? AND name=?", (chat_id, name.lower()))).fetchall()
            else:
                rows = await (await db.execute("SELECT * FROM notes WHERE chat_id=? ORDER BY id", (chat_id,))).fetchall()
            return [dict(row) for row in rows]

    async def index_post(self, channel_id: str, message_id: int, title: str, content: str, link: str = "") -> None:
        async with self.connect() as db:
            await db.execute("INSERT INTO indexed_posts(channel_id,message_id,title,content,link,created_at) VALUES(?,?,?,?,?,?) ON CONFLICT(channel_id,message_id) DO UPDATE SET title=excluded.title,content=excluded.content,link=excluded.link", (channel_id, message_id, title[:300], content[:4000], link[:500], int(time.time())))
            await db.commit()

    async def search_posts(self, channel_id: str, query: str, limit: int = 10) -> list[dict[str, Any]]:
        pattern = f"%{query.lower()}%"
        async with self.connect() as db:
            rows = await (await db.execute("SELECT * FROM indexed_posts WHERE channel_id=? AND (lower(title) LIKE ? OR lower(content) LIKE ?) ORDER BY id DESC LIMIT ?", (channel_id, pattern, pattern, limit))).fetchall()
            return [dict(row) for row in rows]

    async def create_encoding_job(self, job_id: str, chat_id: int, user_id: int, plan: dict[str, Any]) -> None:
        async with self.connect() as db:
            await db.execute("INSERT INTO encoding_jobs(job_id,chat_id,user_id,plan_json,created_at) VALUES(?,?,?,?,?)", (job_id, chat_id, user_id, json.dumps(plan), int(time.time())))
            await db.commit()

    async def update_encoding_job(self, job_id: str, state: str | None = None, progress: str | None = None, error: str | None = None) -> None:
        fields = []
        values: list[Any] = []
        if state is not None:
            fields.append("state=?"); values.append(state)
        if progress is not None:
            fields.append("progress=?"); values.append(progress[:500])
        if error is not None:
            fields.append("error=?"); values.append(error[:1000])
        if state == "running":
            fields.append("started_at=?"); values.append(int(time.time()))
        if state in {"completed", "failed", "cancelled"}:
            fields.append("finished_at=?"); values.append(int(time.time()))
        if not fields:
            return
        values.append(job_id)
        async with self.connect() as db:
            await db.execute(f"UPDATE encoding_jobs SET {', '.join(fields)} WHERE job_id=?", values)
            await db.commit()

    async def get_encoding_job(self, job_id: str) -> dict[str, Any] | None:
        async with self.connect() as db:
            row = await (await db.execute("SELECT * FROM encoding_jobs WHERE job_id=?", (job_id,))).fetchone()
            if row is None:
                return None
            result = dict(row)
            result["plan"] = json.loads(result.pop("plan_json"))
            return result

    async def list_encoding_jobs(self, chat_id: int, limit: int = 20) -> list[dict[str, Any]]:
        async with self.connect() as db:
            rows = await (await db.execute("SELECT * FROM encoding_jobs WHERE chat_id=? ORDER BY created_at DESC LIMIT ?", (chat_id, limit))).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                item["plan"] = json.loads(item.pop("plan_json"))
                result.append(item)
            return result

    async def add_memory(self, scope_key: str, content: str, user_id: int | None, chat_id: int | None) -> None:
        async with self.connect() as db:
            await db.execute(
                "INSERT INTO memories(scope_key,user_id,chat_id,content,created_at) VALUES(?,?,?,?,?)",
                (scope_key, user_id, chat_id, content[:4000], int(time.time())),
            )
            await db.commit()

    async def recent_memories(self, scope_key: str, limit: int = 8) -> list[str]:
        async with self.connect() as db:
            rows = await (await db.execute(
                "SELECT content FROM memories WHERE scope_key=? ORDER BY id DESC LIMIT ?",
                (scope_key, limit),
            )).fetchall()
            return [row["content"] for row in reversed(rows)]

    async def delete_latest_memory(self, scope_key: str, user_id: int) -> bool:
        async with self.connect() as db:
            row = await (await db.execute("SELECT id FROM memories WHERE scope_key=? AND user_id=? ORDER BY id DESC LIMIT 1", (scope_key, user_id))).fetchone()
            if not row:
                return False
            await db.execute("DELETE FROM memories WHERE id=?", (row["id"],))
            await db.commit()
            return True

    async def audit(self, chat_id: int | None, actor_id: int | None, event: str, detail: dict[str, Any]) -> None:
        async with self.connect() as db:
            await db.execute(
                "INSERT INTO audit_log(chat_id,actor_id,event,detail_json,created_at) VALUES(?,?,?,?,?)",
                (chat_id, actor_id, event, json.dumps(detail), int(time.time())),
            )
            await db.commit()

    async def record_provider_telemetry(self, rows: list[dict[str, Any]]) -> None:
        """Persist aggregate provider metrics (no prompts, secrets, or chat content)."""
        if not rows:
            return
        now = int(time.time())
        async with self.connect() as db:
            await db.executemany(
                "INSERT INTO provider_telemetry(ts,name,model,family,privacy_tier,successes,failures,prompt_tokens,completion_tokens,error_classes_json) VALUES(?,?,?,?,?,?,?,?,?,?)",
                [
                    (
                        now,
                        str(row.get("name", "")),
                        str(row.get("model", "")),
                        str(row.get("family", "")),
                        str(row.get("privacy_tier", "")),
                        int(row.get("successes", 0) or 0),
                        int(row.get("failures", 0) or 0),
                        int(row.get("prompt_tokens", 0) or 0),
                        int(row.get("completion_tokens", 0) or 0),
                        json.dumps(row.get("error_classes", {}) or {}),
                    )
                    for row in rows
                ],
            )
            await db.commit()

    async def latest_provider_telemetry(self, limit: int = 100) -> list[dict[str, Any]]:
        """Return the most recent aggregate telemetry rows for observability."""
        async with self.connect() as db:
            rows = await (await db.execute(
                "SELECT ts,name,model,family,privacy_tier,successes,failures,prompt_tokens,completion_tokens,error_classes_json FROM provider_telemetry ORDER BY id DESC LIMIT ?",
                (max(1, min(int(limit), 500)),),
            )).fetchall()
        result = []
        for row in reversed(rows):
            result.append({
                "ts": row["ts"],
                "name": row["name"],
                "model": row["model"],
                "family": row["family"],
                "privacy_tier": row["privacy_tier"],
                "successes": row["successes"],
                "failures": row["failures"],
                "prompt_tokens": row["prompt_tokens"],
                "completion_tokens": row["completion_tokens"],
                "error_classes": json.loads(row["error_classes_json"] or "{}"),
            })
        return result

    async def register_managed_project(self, project: dict[str, Any]) -> dict[str, Any]:
        now = int(time.time())
        fields = ("slug", "repository_url", "branch", "runtime", "run_profile", "run_target", "project_root", "env_path", "owner_id", "state", "revision", "last_error")
        values = {field: project.get(field, "") for field in fields}
        values["branch"] = values["branch"] or "main"
        values["state"] = values["state"] or "registered"
        async with self.connect() as db:
            await db.execute(
                """INSERT INTO managed_projects(slug,repository_url,branch,runtime,run_profile,run_target,project_root,env_path,owner_id,state,revision,last_error,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(slug) DO UPDATE SET repository_url=excluded.repository_url,branch=excluded.branch,runtime=excluded.runtime,run_profile=excluded.run_profile,run_target=excluded.run_target,project_root=excluded.project_root,env_path=excluded.env_path,owner_id=excluded.owner_id,updated_at=excluded.updated_at""",
                tuple(values[field] for field in fields) + (now, now),
            )
            await db.commit()
        return await self.get_managed_project(str(values["slug"])) or {}

    async def get_managed_project(self, slug: str) -> dict[str, Any] | None:
        async with self.connect() as db:
            row = await (await db.execute("SELECT * FROM managed_projects WHERE slug=?", (slug,))).fetchone()
            return dict(row) if row else None

    async def list_managed_projects(self, owner_id: int | None = None) -> list[dict[str, Any]]:
        async with self.connect() as db:
            if owner_id is None:
                rows = await (await db.execute("SELECT * FROM managed_projects ORDER BY updated_at DESC, slug")).fetchall()
            else:
                rows = await (await db.execute("SELECT * FROM managed_projects WHERE owner_id=? ORDER BY updated_at DESC, slug", (owner_id,))).fetchall()
            return [dict(row) for row in rows]

    async def update_managed_project(self, slug: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        allowed = {"branch", "runtime", "run_profile", "state", "revision", "last_error"}
        values = {key: value for key, value in patch.items() if key in allowed}
        if not values:
            return await self.get_managed_project(slug)
        values["updated_at"] = int(time.time())
        assignments = ", ".join(f"{key}=?" for key in values)
        async with self.connect() as db:
            await db.execute(f"UPDATE managed_projects SET {assignments} WHERE slug=?", tuple(values.values()) + (slug,))
            await db.commit()
        return await self.get_managed_project(slug)

    async def save_project_env_schema(self, slug: str, schema: list[dict[str, Any]]) -> None:
        async with self.connect() as db:
            await db.execute("DELETE FROM managed_project_env WHERE project_slug=?", (slug,))
            for item in schema:
                await db.execute(
                    "INSERT INTO managed_project_env(project_slug,name,required,secret,default_value,description,validation) VALUES(?,?,?,?,?,?,?)",
                    (slug, item["name"], int(bool(item.get("required"))), int(bool(item.get("secret", True))), str(item.get("default", "")), str(item.get("description", "")), str(item.get("validation", "text"))),
                )
            await db.commit()

    async def get_project_env_schema(self, slug: str) -> list[dict[str, Any]]:
        async with self.connect() as db:
            rows = await (await db.execute("SELECT * FROM managed_project_env WHERE project_slug=? ORDER BY name", (slug,))).fetchall()
            return [dict(row) for row in rows]

    async def track_series(self, chat_id: int, title: str, media_type: str, created_by: int, last_chapter: str = "", target_channel_id: str = "") -> dict[str, Any]:
        normalized = " ".join(title.lower().split())
        now = int(time.time())
        async with self.connect() as db:
            await db.execute(
                """INSERT INTO tracked_series(chat_id,title,normalized_title,media_type,last_chapter,target_channel_id,created_by,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?)
                ON CONFLICT(chat_id,normalized_title) DO UPDATE SET title=excluded.title,media_type=excluded.media_type,last_chapter=CASE WHEN excluded.last_chapter<>'' THEN excluded.last_chapter ELSE tracked_series.last_chapter END,target_channel_id=CASE WHEN excluded.target_channel_id<>'' THEN excluded.target_channel_id ELSE tracked_series.target_channel_id END,active=1,updated_at=excluded.updated_at""",
                (chat_id, title[:200], normalized, media_type, last_chapter[:40], target_channel_id[:80], created_by, now, now),
            )
            await db.commit()
            row = await (await db.execute("SELECT * FROM tracked_series WHERE chat_id=? AND normalized_title=?", (chat_id, normalized))).fetchone()
            return dict(row)

    async def list_tracked_series(self, chat_id: int, active_only: bool = True, limit: int = 50) -> list[dict[str, Any]]:
        async with self.connect() as db:
            query = "SELECT * FROM tracked_series WHERE chat_id=?"
            values: tuple[Any, ...] = (chat_id,)
            if active_only:
                query += " AND active=1"
            query += " ORDER BY updated_at DESC, title LIMIT ?"
            rows = await (await db.execute(query, values + (max(1, min(limit, 100)),))).fetchall()
            return [dict(row) for row in rows]

    async def get_tracked_series(self, chat_id: int, title: str) -> dict[str, Any] | None:
        normalized = " ".join(title.lower().split())
        async with self.connect() as db:
            row = await (await db.execute("SELECT * FROM tracked_series WHERE chat_id=? AND normalized_title=? AND active=1", (chat_id, normalized))).fetchone()
            return dict(row) if row else None

    async def update_tracked_series(self, chat_id: int, title: str, last_chapter: str, actor_id: int, status: str = "tracking") -> dict[str, Any] | None:
        normalized = " ".join(title.lower().split())
        now = int(time.time())
        async with self.connect() as db:
            await db.execute(
                "UPDATE tracked_series SET last_chapter=?, status=?, updated_at=? WHERE chat_id=? AND normalized_title=? AND active=1",
                (last_chapter[:40], status[:40], now, chat_id, normalized),
            )
            await db.commit()
            row = await (await db.execute("SELECT * FROM tracked_series WHERE chat_id=? AND normalized_title=?", (chat_id, normalized))).fetchone()
            return dict(row) if row else None


db = Database(settings.database_url)
