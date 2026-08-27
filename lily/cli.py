from __future__ import annotations

import argparse
import asyncio
import json

from .agent import ai
from .bot_factory import ManagedBotFactory
from .config import settings
from .db import db
from .knowledge_library import catalog


async def run(args: argparse.Namespace) -> int:
    await db.init()
    if args.command == "status":
        print(json.dumps(await ai.status(), indent=2))
        return 0
    if args.command == "plan":
        plan = await ai.plan(args.text, {"chat_type": "cli", "reply": {}}, [], {"memory_enabled": False})
        print(json.dumps(plan.__dict__, ensure_ascii=False, indent=2))
        return 0
    if args.command == "ask":
        answer = await ai.answer(args.text, {"chat_type": "cli", "reply": {}}, [], {"memory_enabled": False})
        print(answer)
        return 0
    if args.command == "preview":
        plan = await ai.plan(args.text, {"chat_type": "cli", "reply": {}}, [], {"memory_enabled": False})
        print(json.dumps({"plan": plan.__dict__, "public_stages": plan.public_stages(), "executes": False}, ensure_ascii=False, indent=2))
        return 0
    if args.command == "skills":
        print(json.dumps(catalog(), ensure_ascii=False, indent=2))
        return 0
    if args.command == "projects":
        print(json.dumps(await db.list_managed_projects(), ensure_ascii=False, indent=2))
        return 0
    if args.command == "run-profiles":
        print(json.dumps(ManagedBotFactory(db).run_profiles(), ensure_ascii=False, indent=2))
        return 0
    if args.command == "doctor":
        statuses = await ai.status()
        report = {
            "bot_token_configured": bool(settings.bot_token),
            "local_bot_api": settings.use_local_bot_api,
            "rich_live_previews": settings.rich_live_previews,
            "rich_visible_progress": settings.rich_visible_progress,
            "managed_provisioning_enabled": settings.enable_managed_project_provisioning and not settings.bot_factory_dry_run,
            "model_profiles": len(statuses),
            "available_models": sum(bool(item.get("available")) for item in statuses),
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    return 2


def main() -> None:
    parser = argparse.ArgumentParser(prog="lily-agent", description="Run Lily's model-aware agent from a shell.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="Print configured model health.")
    sub.add_parser("skills", help="List Lily’s curated operating skills.")
    sub.add_parser("projects", help="List managed bot registry records (no secrets).")
    sub.add_parser("run-profiles", help="List approved managed-bot runtime profiles.")
    sub.add_parser("doctor", help="Print redacted deployment and capability diagnostics.")
    for name, help_text in (("plan", "Return Lily's structured action plan."), ("ask", "Ask Lily a conversational question.")):
        child = sub.add_parser(name, help=help_text)
        child.add_argument("text")
    preview = sub.add_parser("preview", help="Show a non-executing public action preview.")
    preview.add_argument("text")
    raise SystemExit(asyncio.run(run(parser.parse_args())))


if __name__ == "__main__":
    main()
