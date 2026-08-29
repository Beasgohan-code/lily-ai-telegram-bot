"""Constrained service lifecycle controls for explicitly registered managed bots.

This is intentionally not a shell. It invokes fixed systemd commands only for
allow-listed project slugs, is disabled by default, verifies registry ownership,
and redacts log content before it can be shown outside the host.
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Awaitable, Callable

from .bot_factory import SLUG_RE
from .config import Settings, settings
from .db import Database, db


_ACTIONS = {"start", "stop", "restart"}
_REDACTIONS = (
    (re.compile(r"(?i)(authorization:\s*bearer\s+)[^\s]+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)\b([a-z0-9_]*(?:token|api[_-]?key|secret|password|credential)[a-z0-9_]*\s*[=:]\s*)[^\s'\"]+"), r"\1[REDACTED]"),
    (re.compile(r"([?&](?:token|api[_-]?key|secret|password)=[^&\s]+)", re.I), "[REDACTED_QUERY]"),
)


class SupervisorError(ValueError):
    pass


@dataclass(frozen=True)
class ProcessResult:
    returncode: int
    stdout: str
    stderr: str


Runner = Callable[[list[str]], Awaitable[ProcessResult]]


def redact_log_text(value: str, limit: int = 4000) -> str:
    text = str(value or "").replace("\x00", " ")
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text[-max(200, min(limit, 12_000)):]


class ManagedServiceSupervisor:
    def __init__(self, database: Database = db, config: Settings = settings, runner: Runner | None = None) -> None:
        self.db = database
        self.settings = config
        self.runner = runner or self._run

    async def _run(self, command: list[str]) -> ProcessResult:
        process = await asyncio.create_subprocess_exec(*command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=20)
        return ProcessResult(process.returncode or 0, stdout.decode(errors="replace"), stderr.decode(errors="replace"))

    def _unit(self, slug: str) -> str:
        normalized = str(slug or "").strip().lower()
        if not SLUG_RE.fullmatch(normalized):
            raise SupervisorError("Managed service slug is invalid.")
        return f"lily-managed-{normalized}.service"

    async def _project(self, slug: str, owner_id: int) -> tuple[dict[str, object], str]:
        unit = self._unit(slug)
        project = await self.db.get_managed_project(str(slug).lower())
        if not project or int(project.get("owner_id") or 0) != int(owner_id):
            raise SupervisorError("That managed project is not registered to this operator.")
        if str(project.get("slug")) not in self.settings.allowed_managed_service_slugs:
            raise SupervisorError("This project is not in LILY_ALLOWED_MANAGED_SERVICES.")
        return project, unit

    def _enabled(self) -> None:
        if not self.settings.enable_managed_service_supervisor:
            raise SupervisorError("Managed service supervision is disabled. Enable it only on a hardened persistent Ubuntu host.")

    async def status(self, slug: str, owner_id: int) -> dict[str, object]:
        project, unit = await self._project(slug, owner_id)
        if not self.settings.enable_managed_service_supervisor:
            return {"service": unit, "project": project["slug"], "enabled": False, "state": "disabled", "detail": "Supervisor is disabled by configuration."}
        result = await self.runner(["systemctl", "--user", "show", unit, "--property=ActiveState,SubState,LoadState", "--value"])
        detail = redact_log_text(result.stdout or result.stderr, 500).replace("\n", "; ").strip()
        return {"service": unit, "project": project["slug"], "enabled": True, "state": "available" if result.returncode == 0 else "unavailable", "detail": detail}

    async def control(self, slug: str, owner_id: int, action: str) -> dict[str, object]:
        if action not in _ACTIONS:
            raise SupervisorError("Choose start, stop, or restart.")
        self._enabled()
        project, unit = await self._project(slug, owner_id)
        result = await self.runner(["systemctl", "--user", action, unit])
        if result.returncode != 0:
            await self.db.update_managed_project(str(project["slug"]), {"state": "supervisor_error", "last_error": "systemd control request failed"})
            raise SupervisorError("The systemd control request failed. Check protected host logs.")
        state = "stopped" if action == "stop" else "starting" if action == "start" else "restarting"
        await self.db.update_managed_project(str(project["slug"]), {"state": state, "last_error": ""})
        await self.db.audit(None, owner_id, "managed_service_control", {"slug": project["slug"], "action": action})
        return {"service": unit, "project": project["slug"], "action": action, "state": state}

    async def logs(self, slug: str, owner_id: int, limit: int = 50) -> dict[str, object]:
        self._enabled()
        project, unit = await self._project(slug, owner_id)
        count = max(1, min(int(limit), 200))
        result = await self.runner(["journalctl", "--user", "-u", unit, "-n", str(count), "--no-pager", "--output=short-iso"])
        if result.returncode != 0:
            raise SupervisorError("The service logs are unavailable. Check protected host logs.")
        return {"service": unit, "project": project["slug"], "lines": redact_log_text(result.stdout, 6000)}


service_supervisor = ManagedServiceSupervisor()
