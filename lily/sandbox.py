"""Bounded local-runtime inspection for Lily operators.

This module deliberately does not execute caller-supplied shell commands. It
reports the availability of Lily's fixed local capabilities so an operator can
choose a documented launcher or a supervised production service.
"""
from __future__ import annotations

import platform
import shutil
import sys
from pathlib import Path
from typing import Any

from .config import settings


TERMINAL_OPTIONS = (
    {"name": "doctor", "purpose": "Redacted local configuration and model health"},
    {"name": "status", "purpose": "Configured model/provider health"},
    {"name": "search", "purpose": "Configured web search for a supplied query"},
    {"name": "workspace", "purpose": "Create, edit, validate, and ZIP Lily-owned code workspaces"},
    {"name": "agent", "purpose": "Non-executing local plan and public stages"},
    {"name": "check", "purpose": "Compile and run Lily's regression suite"},
    {"name": "bot", "purpose": "Start Lily's Telegram worker in the foreground"},
    {"name": "api", "purpose": "Start Lily's FastAPI service in the foreground"},
)


def _directory_status(path: Path) -> dict[str, bool]:
    return {"configured": bool(path), "exists": path.exists(), "writable": path.exists() and path.is_dir()}


def sandbox_status() -> dict[str, Any]:
    """Return a redacted, fixed schema of local runtime capabilities."""
    return {
        "runtime": "ubuntu-local",
        "persistent_service": False,
        "python": platform.python_version(),
        "platform": platform.system(),
        "tools": {"ffmpeg": bool(shutil.which("ffmpeg")), "ffprobe": bool(shutil.which("ffprobe"))},
        "storage": {"work_dir": _directory_status(settings.work_dir), "download_dir": _directory_status(settings.download_dir)},
        "web_search": {"provider": settings.web_search_provider, "configured": bool(settings.web_search_url), "api_key_configured": bool(settings.web_search_api_key)},
        "terminal_options": [option["name"] for option in TERMINAL_OPTIONS],
        "arbitrary_shell_execution": False,
        "note": "This local runtime can hibernate. Use supervised Ubuntu hosting for a 24/7 Lily service.",
    }
