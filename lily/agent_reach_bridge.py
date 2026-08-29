"""Optional Agent-Reach integration and free zero-key web helpers.

Agent-Reach (https://github.com/Panniantong/Agent-Reach) is an installer/doctor
for upstream free platform tools. Lily does not vendor its full CLI stack, but
adopts the same philosophy:

* Prefer free, no-key backends when possible (Jina Reader for pages, public APIs).
* Expose a health snapshot so operators know what is available.
* Never require Agent-Reach to be installed for core Lily features.
"""
from __future__ import annotations

import asyncio
import shutil
import subprocess
from typing import Any

import httpx

from .config import settings


def agent_reach_installed() -> bool:
    return shutil.which("agent-reach") is not None


async def doctor_snapshot() -> dict[str, Any]:
    """Run `agent-reach doctor --json` when the CLI is on PATH; else return Lily-native status."""
    if not agent_reach_installed():
        return {
            "agent_reach": False,
            "message": "Agent-Reach CLI not installed. Core Lily free tools still work.",
            "install": "pip install agent-reach  # or follow https://github.com/Panniantong/Agent-Reach",
            "lily_free_tools": bool(getattr(settings, "enable_free_tools", True)),
        }
    try:
        proc = await asyncio.create_subprocess_exec(
            "agent-reach", "doctor", "--json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=45)
        text = (stdout or b"").decode("utf-8", errors="replace").strip()
        if proc.returncode != 0:
            return {
                "agent_reach": True,
                "ok": False,
                "detail": (stderr.decode("utf-8", errors="replace") or text)[:500],
            }
        import json
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = {"raw": text[:2000]}
        return {"agent_reach": True, "ok": True, "report": payload}
    except Exception as exc:
        return {"agent_reach": True, "ok": False, "detail": str(exc)[:300]}


async def read_page_jina(url: str, *, max_chars: int = 6000) -> str:
    """Read a public URL as clean markdown via Jina Reader (free, no API key).

    Same approach Agent-Reach documents for generic web reading.
    """
    url = (url or "").strip()
    if not url.startswith(("http://", "https://")):
        raise ValueError("Provide a full http(s) URL.")
    # Jina Reader: https://r.jina.ai/<url>
    endpoint = f"https://r.jina.ai/{url}"
    timeout = httpx.Timeout(45.0, connect=12.0)
    headers = {
        "User-Agent": "LilyBot/2.2 (+https://github.com/Beasgohan-code/lily-ai-telegram-bot)",
        "Accept": "text/plain, text/markdown, */*",
    }
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers) as client:
        response = await client.get(endpoint)
        response.raise_for_status()
        text = (response.text or "").strip()
    if not text:
        raise ValueError("Jina Reader returned an empty page.")
    if len(text) > max_chars:
        text = text[: max_chars - 1].rsplit(" ", 1)[0] + "…"
    return text


async def lily_free_capability_report() -> dict[str, Any]:
    """Operator-facing snapshot of free tools + optional Agent-Reach + LLM presets."""
    from .free_models import PRESETS, CATALOG
    from .free_tools import free_tools
    import os

    preset_status = []
    for slug, meta in PRESETS.items():
        env_name = str(meta.get("env") or "")
        configured = bool(os.getenv(env_name)) if env_name else False
        preset_status.append({
            "preset": slug,
            "provider": meta.get("provider"),
            "env": env_name,
            "configured": configured,
            "default_model": meta.get("default"),
            "tier": meta.get("tier"),
        })
    return {
        "free_tools_enabled": bool(getattr(settings, "enable_free_tools", True)),
        "free_tool_count": len(free_tools.catalog()),
        "agent_reach_installed": agent_reach_installed(),
        "jina_reader": "https://r.jina.ai/{url}",
        "llm_presets": preset_status,
        "catalog_providers": len(CATALOG),
    }
