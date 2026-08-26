from __future__ import annotations

import json
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import aiosqlite

from .config import settings


DEFAULT_SETTINGS: dict[str, Any] = {
    "personality": "friendly, concise, and helpful",
    "language": "English",
    "mention_only": True,
    "moderation_enabled": True,
    "welcome_enabled": True,
    "welcome_text": "Welcome {user} to {group}! Please read the rules.",
    "warning_escalation": 3,
    "memory_enabled": False,
    "auto_confirm_safe": True,
    "daily_request_limit": settings.daily_request_limit,
    "monthly_request_limit": settings.monthly_request_limit,
    "daily_bytes_limit": settings.daily_bytes_limit,
    "monthly_bytes_limit": settings.monthly_bytes_limit,
}


class Database:
    def __init__(self, path: str):
        self.path = path

    @asynccontextmanager
    async def connect(self):
        db = await aiosqlite.connect(self.path)
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode=WAL")
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
                    created_by INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    UNIQUE(chat_id, name)
                );
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
                """
            )
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
            return {**DEFAULT_SETTINGS, **values}

    async def update_chat_settings(self, chat_id: int, patch: dict[str, Any], title: str = "") -> dict[str, Any]:
        current = await self.get_chat_settings(chat_id, title)
        current.update(patch)
        async with self.connect() as db:
            await db.execute(
                "UPDATE chats SET settings_json=?,title=?,updated_at=? WHERE chat_id=?",
                (json.dumps(current), title, int(time.time()), chat_id),
            )
            await db.commit()
        return current

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

    async def save_skill(self, chat_id: int, created_by: int, name: str, trigger: dict[str, Any], action: dict[str, Any], confirmation: str = "risky", cooldown_seconds: int = 0) -> str:
        skill_id = uuid.uuid4().hex
        async with self.connect() as db:
            await db.execute(
                "INSERT INTO skills(id,chat_id,name,trigger_json,action_json,confirmation,cooldown_seconds,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (skill_id, chat_id, name, json.dumps(trigger), json.dumps(action), confirmation, cooldown_seconds, created_by, int(time.time())),
            )
            await db.commit()
        return skill_id

    async def list_skills(self, chat_id: int) -> list[dict[str, Any]]:
        async with self.connect() as db:
            rows = await (await db.execute("SELECT * FROM skills WHERE chat_id=? ORDER BY created_at", (chat_id,))).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                item["trigger"] = json.loads(item.pop("trigger_json"))
                item["action"] = json.loads(item.pop("action_json"))
                result.append(item)
            return result

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

    async def audit(self, chat_id: int | None, actor_id: int | None, event: str, detail: dict[str, Any]) -> None:
        async with self.connect() as db:
            await db.execute(
                "INSERT INTO audit_log(chat_id,actor_id,event,detail_json,created_at) VALUES(?,?,?,?,?)",
                (chat_id, actor_id, event, json.dumps(detail), int(time.time())),
            )
            await db.commit()


db = Database(settings.database_url)
