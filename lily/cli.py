from __future__ import annotations

import argparse
import asyncio
import json

from .agent import ai
from .bot_factory import ManagedBotFactory
from .config import settings
from .db import db
from .knowledge_library import catalog
from .sandbox import sandbox_status
from .web_media import web_search


def public_agent_report(plan) -> dict[str, object]:
    """Return only deliberate operator-facing plan information, never hidden reasoning."""
    return {
        "intent": plan.intent,
        "summary": plan.summary,
        "action": plan.action,
        "risk": plan.risk,
        "confirmation_required": plan.requires_confirmation,
        "missing": plan.missing,
        "public_stages": plan.public_stages(),
        "executes": False,
    }


async def _agent_plan(text: str) -> dict[str, object]:
    plan = await ai.plan(text, {"chat_type": "cli", "reply": {}}, [], {"memory_enabled": False})
    return public_agent_report(plan)


async def _interactive_agent() -> int:
    print("Lily Ubuntu Agent — planning mode only. Nothing runs from this prompt.")
    print("Enter a request, use /ask <question> for conversation, or /quit to exit.")
    while True:
        try:
            value = input("lily> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not value:
            continue
        if value.lower() in {"/quit", "/exit", "quit", "exit"}:
            return 0
        if value.lower() in {"/help", "help"}:
            print("Requests produce a non-executing plan. Use /ask <question> for a normal AI answer.")
            continue
        if value.startswith("/ask "):
            print(await ai.answer(value[5:], {"chat_type": "cli", "reply": {}}, [], {"memory_enabled": False}))
            continue
        print(json.dumps(await _agent_plan(value), ensure_ascii=False, indent=2))


async def run(args: argparse.Namespace) -> int:
    await db.init()
    if args.command == "status":
        print(json.dumps(await ai.status(), indent=2))
        return 0
    if args.command == "sandbox":
        print(json.dumps(sandbox_status(), ensure_ascii=False, indent=2))
        return 0
    if args.command == "search":
        results = await web_search.search(args.query, args.limit)
        print(json.dumps({"query": args.query, "results": results}, ensure_ascii=False, indent=2))
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
        print(json.dumps(await _agent_plan(args.text), ensure_ascii=False, indent=2))
        return 0
    if args.command == "agent":
        if not args.text:
            return await _interactive_agent()
        if args.ask:
            print(await ai.answer(args.text, {"chat_type": "cli", "reply": {}}, [], {"memory_enabled": False}))
            return 0
        print(json.dumps(await _agent_plan(args.text), ensure_ascii=False, indent=2))
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
    sub.add_parser("sandbox", help="Print redacted local Ubuntu runtime capabilities.")
    search = sub.add_parser("search", help="Search the web through Lily’s configured provider.")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=None, help="Return 1–10 results (provider-capped).")
    sub.add_parser("skills", help="List Lily’s curated operating skills.")
    sub.add_parser("projects", help="List managed bot registry records (no secrets).")
    sub.add_parser("run-profiles", help="List approved managed-bot runtime profiles.")
    sub.add_parser("doctor", help="Print redacted deployment and capability diagnostics.")
    for name, help_text in (("plan", "Return Lily's structured action plan."), ("ask", "Ask Lily a conversational question.")):
        child = sub.add_parser(name, help=help_text)
        child.add_argument("text")
    preview = sub.add_parser("preview", help="Show a non-executing public action preview.")
    preview.add_argument("text")
    agent = sub.add_parser("agent", help="Run a safe local planning agent; it never executes actions.")
    agent.add_argument("text", nargs="?", help="Optional request to plan; omit for an interactive prompt.")
    agent.add_argument("--ask", action="store_true", help="Answer the supplied text conversationally instead of planning it.")
    raise SystemExit(asyncio.run(run(parser.parse_args())))


if __name__ == "__main__":
    main()
