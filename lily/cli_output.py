"""Human-friendly CLI output helpers for Lily."""

from __future__ import annotations

import json
import sys
from typing import Any


# ANSI (disabled when not a TTY or NO_COLOR is set)
def _color_enabled() -> bool:
    import os
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


class Style:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    CYAN = "\033[36m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"

    @classmethod
    def paint(cls, text: str, *codes: str) -> str:
        if not _color_enabled():
            return text
        return "".join(codes) + text + cls.RESET


class CLIOutput:
    def __init__(self, *, json_mode: bool = False, quiet: bool = False) -> None:
        self.json_mode = json_mode
        self.quiet = quiet

    def emit(self, payload: Any, *, text: str | None = None) -> None:
        if self.json_mode:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return
        if text is not None:
            print(text)
        elif isinstance(payload, str):
            print(payload)
        elif payload is not None:
            print(json.dumps(payload, ensure_ascii=False, indent=2))

    def banner(self, title: str = "Lily", subtitle: str = "AI-first Telegram backend") -> None:
        if self.json_mode or self.quiet:
            return
        line = "─" * 56
        print(Style.paint(line, Style.DIM))
        print(Style.paint(f"  {title}", Style.BOLD, Style.CYAN) + Style.paint(f"  ·  {subtitle}", Style.DIM))
        print(Style.paint(line, Style.DIM))

    def success(self, message: str) -> None:
        if self.json_mode:
            self.emit({"ok": True, "message": message})
            return
        print(Style.paint("✔ ", Style.GREEN) + message)

    def warn(self, message: str) -> None:
        if self.json_mode:
            self.emit({"ok": False, "warning": message})
            return
        print(Style.paint("⚠ ", Style.YELLOW) + message, file=sys.stderr)

    def error(self, message: str) -> None:
        if self.json_mode:
            self.emit({"ok": False, "error": message})
            return
        print(Style.paint("✖ ", Style.RED) + message, file=sys.stderr)

    def step(self, index: int, total: int, message: str) -> None:
        if self.json_mode or self.quiet:
            return
        prefix = Style.paint(f"[{index}/{total}]", Style.BOLD, Style.BLUE)
        print(f"{prefix} {message}")

    def kv(self, key: str, value: Any) -> None:
        if self.json_mode:
            return
        print(f"  {Style.paint(str(key).ljust(18), Style.DIM)} {value}")

    def table(self, headers: list[str], rows: list[list[str]], *, title: str | None = None) -> None:
        if self.json_mode:
            self.emit({"title": title, "headers": headers, "rows": rows})
            return
        if title and not self.quiet:
            print(Style.paint(title, Style.BOLD))
        widths = [len(header) for header in headers]
        for row in rows:
            for index, cell in enumerate(row):
                widths[index] = max(widths[index], len(str(cell)))
        line = "  ".join(header.ljust(widths[index]) for index, header in enumerate(headers))
        print(Style.paint(line, Style.BOLD))
        print(Style.paint("  ".join("-" * widths[index] for index in range(len(headers))), Style.DIM))
        for row in rows:
            print("  ".join(str(row[index]).ljust(widths[index]) for index in range(len(headers))))

    def section(self, title: str) -> None:
        if self.json_mode or self.quiet:
            return
        print()
        print(Style.paint(title, Style.BOLD, Style.CYAN))
        print(Style.paint("─" * min(len(title), 72), Style.DIM))


def is_tty() -> bool:
    return sys.stdout.isatty()


def format_plan_report(report: dict[str, Any]) -> str:
    lines = [
        f"Action: {report.get('action', 'none')}",
        f"Risk: {report.get('risk', 'safe')}",
        f"Summary: {report.get('summary', '')}",
    ]
    if report.get("confirmation_required") or report.get("requires_confirmation"):
        lines.append("Confirmation: required in Telegram")
    missing = report.get("missing") or []
    if missing:
        lines.append("Missing: " + "; ".join(str(item) for item in missing))
    stages = report.get("public_stages") or []
    if stages:
        lines.append("Stages:")
        for stage in stages:
            lines.append(f"  • {stage}")
    team = report.get("agent_team") or {}
    if isinstance(team, dict) and team.get("reviewed_count"):
        roles = ", ".join(
            str(item.get("role") or "")
            for item in (team.get("roles") or [])
            if isinstance(item, dict)
        )
        lines.append(f"Team review: {team.get('reviewed_count')} role(s)" + (f" — {roles}" if roles else ""))
    return "\n".join(lines)


def format_model_table(models: list[dict[str, Any]]) -> list[list[str]]:
    rows: list[list[str]] = []
    for model in models:
        rows.append([
            str(model.get("name") or model.get("id") or "—")[:28],
            str(model.get("provider") or "—")[:16],
            str(model.get("tier") or "—")[:12],
        ])
    return rows


def redacted_config(settings_obj: Any = None) -> dict[str, Any]:
    from .config import settings as _default_settings
    settings = settings_obj if settings_obj is not None else _default_settings

    def mask(value: str) -> str:
        if not value:
            return "(empty)"
        if len(value) <= 8:
            return "***"
        return value[:4] + "…" + value[-2:]

    return {
        "bot_token": mask(getattr(settings, "bot_token", "")),
        "bot_api_base": getattr(settings, "bot_api_base", ""),
        "database": str(getattr(settings, "database_url", "")),
        "work_dir": str(getattr(settings, "work_dir", "")),
        "ai_keys_configured": len(getattr(settings, "ai_keys", ()) or ()),
        "enable_free_tools": bool(getattr(settings, "enable_free_tools", False)),
        "agent_team": bool(getattr(settings, "enable_agent_team", False)),
        "rich_live_previews": bool(getattr(settings, "rich_live_previews", False)),
        "ephemeral_confirmations": bool(getattr(settings, "enable_ephemeral_confirmations", False)),
        "compact_responses": bool(getattr(settings, "compact_responses", False)),
    }
