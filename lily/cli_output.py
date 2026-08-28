"""Human-friendly CLI output helpers for Lily."""

from __future__ import annotations

import json
import sys
from typing import Any


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

    def table(self, headers: list[str], rows: list[list[str]], *, title: str | None = None) -> None:
        if self.json_mode:
            self.emit({"title": title, "headers": headers, "rows": rows})
            return
        if title and not self.quiet:
            print(title)
        widths = [len(header) for header in headers]
        for row in rows:
            for index, cell in enumerate(row):
                widths[index] = max(widths[index], len(cell))
        line = "  ".join(header.ljust(widths[index]) for index, header in enumerate(headers))
        print(line)
        print("  ".join("-" * widths[index] for index in range(len(headers))))
        for row in rows:
            print("  ".join(str(row[index]).ljust(widths[index]) for index in range(len(headers))))

    def section(self, title: str) -> None:
        if self.json_mode or self.quiet:
            return
        print(f"\n{title}")
        print("-" * min(len(title), 72))


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
    if team.get("enabled"):
        lines.append(f"Team review: {team.get('status', 'complete')}")
    return "\n".join(lines)


def format_model_table(models: list[dict[str, Any]]) -> str:
    if not models:
        return "Configured models:\n  (none)"
    lines = ["Configured models:", f"{'Name':<28} {'Model':<24} {'Family':<12} Status", "-" * 72]
    for item in models:
        status = "ok" if item.get("available") else "down"
        lines.append(
            f"{str(item.get('name') or 'model')[:28]:<28} "
            f"{str(item.get('model') or '')[:24]:<24} "
            f"{str(item.get('family') or '')[:12]:<12} {status}"
        )
    return "\n".join(lines)


def redacted_config(config: Any) -> dict[str, object]:
    """Return operator-safe configuration flags without secrets."""
    return {
        "bot_token_configured": bool(config.bot_token),
        "database": str(config.database_url),
        "local_bot_api": config.use_local_bot_api,
        "ai_model": config.ai_model,
        "openai_configured": bool(config.openai_api_key),
        "ai_key_count": len(config.ai_keys),
        "enable_agent_team": config.enable_agent_team,
        "enable_rag_routing": config.enable_rag_routing,
        "enable_free_tools": config.enable_free_tools,
        "enable_miniapp_bridge": config.enable_miniapp_bridge,
        "enable_scenario_runbooks": config.enable_scenario_runbooks,
        "enable_qa_loop": config.enable_qa_loop,
        "managed_provisioning": config.enable_managed_project_provisioning and not config.bot_factory_dry_run,
        "managed_supervisor": config.enable_managed_service_supervisor,
        "daily_request_limit": config.daily_request_limit,
        "monthly_request_limit": config.monthly_request_limit,
        "compact_responses": config.compact_responses,
        "message_drafts": config.enable_message_drafts,
        "ai_thinking": config.enable_ai_thinking_indicator,
    }
