"""Lily command-line interface — planning, diagnostics, and operator tools."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

from .agent import AIClient, ai
from .agent_roles import assign_roles, catalog as agent_role_catalog
from .agent_team import public_team_summary
from .bot_factory import ManagedBotFactory
from .briefing_digest import build_briefing
from .code_workspace import code_workspace
from .config import settings
from .db import db
from .free_tools import FreeToolsError, free_tools
from .knowledge_library import catalog as skills_catalog
from .rag_diagnostics import diagnose, public_report
from .rag_router import route as rag_route
from .sandbox import sandbox_status
from .scenario_runbooks import catalog as scenario_catalog, get as scenario_get
from .service_supervisor import ManagedServiceSupervisor
from .skill_engine import select_skill
from .web_media import web_search
from .cli_output import CLIOutput, format_model_table, format_plan_report, redacted_config

__version__ = "2.1.0"

_CLI_CONTEXT = {"chat_type": "cli", "reply": {}, "origin": "cli"}
_CHAT_SETTINGS = {"memory_enabled": False}


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
        "roles": assign_roles(plan).public_dict(),
        "agent_team": public_team_summary(plan),
        "executes": False,
    }


async def _agent_plan(text: str, *, team: bool = False) -> dict[str, object]:
    planner = ai.team_plan if team else ai.plan
    plan = await planner(text, _CLI_CONTEXT, [], _CHAT_SETTINGS)
    return public_agent_report(plan)


def _heuristic_route(text: str) -> dict[str, object]:
    plan = AIClient().heuristic_plan(text, _CLI_CONTEXT)
    collections = rag_route(text)
    return {
        "action": plan.action,
        "risk": plan.risk,
        "summary": plan.summary,
        "confidence": plan.confidence,
        "requires_confirmation": plan.requires_confirmation,
        "missing": plan.missing,
        "knowledge_collections": collections,
        "executes": False,
    }


async def _skill_orchestrator(text: str, chat_id: int, user_id: int) -> dict[str, object]:
    match = select_skill(await db.list_skills(chat_id), text)
    if match:
        return {"source": "automatic_skill", "match": match.public_dict(), "executes": False}
    return {"source": "llm_agent", "plan": await _agent_plan(text), "executes": False}


async def _run_free_tool(name: str, query: str) -> str:
    tool = name.strip().lower()
    query = query.strip()
    if tool in {"catalog", "list"}:
        return json.dumps(free_tools.catalog(), ensure_ascii=False, indent=2)
    if tool == "weather":
        return await free_tools.weather(query)
    if tool == "crypto":
        return await free_tools.crypto_price(query or "bitcoin")
    if tool == "wiki":
        return await free_tools.wikipedia(query)
    if tool == "define":
        return await free_tools.define_word(query)
    if tool == "anime":
        return await free_tools.anime_search(query)
    if tool == "github":
        return await free_tools.github_repo(query)
    if tool == "time":
        return await free_tools.world_time(query)
    if tool == "quote":
        return await free_tools.daily_quote()
    if tool == "hn":
        return await free_tools.hackernews(query or "top")
    if tool == "fact":
        return await free_tools.random_fact()
    if tool == "joke":
        return await free_tools.dad_joke()
    if tool == "cat":
        return await free_tools.cat_fact()
    if tool == "nasa":
        return await free_tools.nasa_apod()
    if tool == "country":
        return await free_tools.country_info(query)
    if tool == "ip":
        return await free_tools.ip_lookup(query)
    if tool == "qr":
        return await free_tools.qr_code(query)
    if tool == "number":
        return await free_tools.number_fact(query)
    if tool == "translate":
        parts = query.split(" to ", 1)
        if len(parts) != 2:
            raise FreeToolsError("Use: lily tools translate \"hello\" to Spanish")
        return await free_tools.translate(parts[0].strip().strip('"'), parts[1].strip())
    if tool == "fx":
        parts = query.split()
        if len(parts) < 3:
            raise FreeToolsError("Use: lily tools fx 100 USD EUR")
        return await free_tools.exchange_rate(parts[1], parts[2], float(parts[0]))
    raise FreeToolsError(f"Unknown tool “{name}”. Run: lily tools catalog")


async def _interactive_chat(out: CLIOutput, *, initial_mode: str = "plan") -> int:
    mode = initial_mode
    print("Lily CLI chat — non-executing. Modes: ask, plan, build, route, tools")
    print("Commands: /mode <ask|plan|build|route|tools>, /json, /help, /quit")
    while True:
        try:
            value = input(f"lily:{mode}> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not value:
            continue
        low = value.lower()
        if low in {"/quit", "/exit", "quit", "exit"}:
            return 0
        if low.startswith("/mode "):
            mode = low.split(maxsplit=1)[1].strip()
            if mode not in {"ask", "plan", "build", "route", "tools"}:
                print("Modes: ask, plan, build, route, tools")
            else:
                print(f"Mode set to {mode}")
            continue
        if low == "/json":
            out.json_mode = not out.json_mode
            print(f"JSON output: {'on' if out.json_mode else 'off'}")
            continue
        if low in {"/help", "help"}:
            print("ask — conversational answer | plan — action plan | build — team plan")
            print("route — fast heuristic routing | tools <name> <query> — free API lookup")
            continue
        if low.startswith("/tools "):
            try:
                parts = value.split(maxsplit=2)
                tool_name = parts[1] if len(parts) > 1 else "catalog"
                tool_query = parts[2] if len(parts) > 2 else ""
                result = await _run_free_tool(tool_name, tool_query)
                out.emit(result, text=result if not out.json_mode else None)
            except FreeToolsError as exc:
                print(str(exc))
            continue
        try:
            if mode == "ask":
                answer = await ai.answer(value, _CLI_CONTEXT, [], _CHAT_SETTINGS)
                out.emit(answer, text=answer if not out.json_mode else None)
            elif mode == "build":
                report = await _agent_plan(value, team=True)
                out.emit(report, text=format_plan_report(report) if not out.json_mode else None)
            elif mode == "route":
                report = _heuristic_route(value)
                out.emit(report, text=format_plan_report(report) if not out.json_mode else None)
            elif mode == "tools":
                try:
                    parts = value.split(maxsplit=1)
                    tool_name = parts[0]
                    tool_query = parts[1] if len(parts) > 1 else ""
                    result = await _run_free_tool(tool_name, tool_query)
                    out.emit(result, text=result if not out.json_mode else None)
                except FreeToolsError as exc:
                    print(str(exc))
            else:
                report = await _agent_plan(value)
                out.emit(report, text=format_plan_report(report) if not out.json_mode else None)
        except Exception as exc:
            print(f"Error: {exc.__class__.__name__}")


_DB_COMMANDS = {
    "usage", "skill-match", "skill-runs", "service", "projects", "briefing", "run-profiles",
}


async def run(args: argparse.Namespace) -> int:
    out = CLIOutput(json_mode=args.json, quiet=args.quiet)
    command = args.command
    if command in _DB_COMMANDS:
        await db.init()

    if command == "version":
        out.emit({"name": "lily-cli", "version": __version__}, text=f"Lily CLI {__version__}")
        return 0

    if command == "status" or command == "models":
        models = await ai.status()
        if command == "models" and not args.json:
            out.emit(models, text=format_model_table(models))
        else:
            out.emit(models)
        return 0

    if command == "config":
        out.emit(redacted_config(settings))
        return 0

    if command == "sandbox":
        out.emit(sandbox_status())
        return 0

    if command == "doctor":
        models = await ai.status()
        report = {
            **redacted_config(settings),
            "model_profiles": len(models),
            "available_models": sum(bool(item.get("available")) for item in models),
            "database_ready": True,
            "free_tools": settings.enable_free_tools,
            "cli_version": __version__,
        }
        out.emit(report)
        return 0

    if command == "usage":
        summary = await db.usage_summary(args.user_id, args.chat_id)
        out.emit(summary)
        return 0

    if command == "route":
        report = _heuristic_route(args.text)
        out.emit(report, text=format_plan_report(report) if not out.json_mode else None)
        return 0

    if command == "search":
        results = await web_search.search(args.query, args.limit)
        out.emit({"query": args.query, "results": results})
        return 0

    if command == "tools":
        try:
            if args.tool_command == "catalog":
                rows = [[item["name"], item["summary"][:48], item["example"][:40]] for item in free_tools.catalog()]
                if out.json_mode:
                    out.emit(free_tools.catalog())
                else:
                    out.table(["Tool", "Summary", "Example"], rows, title="Free API tools")
                return 0
            result = await _run_free_tool(args.tool_command, args.query or "")
            out.emit(result, text=result if not out.json_mode else None)
        except FreeToolsError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        return 0

    if command == "scenarios":
        if args.scenario_command == "list":
            books = scenario_catalog()
            if out.json_mode:
                out.emit(books)
            else:
                rows = [[book["slug"], book["title"], book["mode"], book["duration"]] for book in books]
                out.table(["Slug", "Title", "Mode", "Duration"], rows, title="Scenario runbooks")
            return 0
        book = scenario_get(args.slug)
        if not book:
            print(f"Unknown scenario: {args.slug}", file=sys.stderr)
            return 1
        payload = book.public_dict()
        out.emit(payload, text=None if out.json_mode else f"{book.title}\n{book.summary}\nPhases: {len(book.phases)}")
        return 0

    if command == "briefing":
        payload = await build_briefing(db, args.chat_id)
        out.emit(payload, text=str(payload.get("text")) if not out.json_mode else None)
        return 0

    if command == "rag-debug":
        findings = diagnose(args.text)
        report = public_report(findings)
        out.emit({"findings": findings, "report": report}, text=report if not out.json_mode else None)
        return 0

    if command == "workspace":
        owner = args.owner
        if args.workspace_command == "create":
            output = code_workspace.create_project(owner, args.project, args.language, args.brief)
        elif args.workspace_command == "mkdir":
            output = code_workspace.mkdir(owner, args.project, args.directory)
        elif args.workspace_command == "write":
            output = code_workspace.write_file(owner, args.project, args.path, args.content)
        elif args.workspace_command == "tree":
            output = {"owner": owner, "project": args.project, "files": code_workspace.tree(owner, args.project)}
        elif args.workspace_command == "zip":
            output = {"owner": owner, "project": args.project, "archive": str(code_workspace.archive(owner, args.project))}
        else:
            output = code_workspace.validate(owner, args.project)
        out.emit(output)
        return 0

    if command == "skill-match":
        out.emit(await _skill_orchestrator(args.text, args.chat_id, args.user_id))
        return 0

    if command == "skill-runs":
        out.emit(await db.list_skill_runs(args.chat_id, args.user_id, args.limit))
        return 0

    if command == "service":
        supervisor = ManagedServiceSupervisor()
        if args.service_command == "status":
            output = await supervisor.status(args.slug, args.owner)
        elif args.service_command == "logs":
            output = await supervisor.logs(args.slug, args.owner, args.limit)
        else:
            output = await supervisor.control(args.slug, args.owner, args.service_command)
        out.emit(output)
        return 0

    if command == "plan":
        plan = await ai.plan(args.text, _CLI_CONTEXT, [], _CHAT_SETTINGS)
        if args.json:
            out.emit(plan.__dict__)
        else:
            out.emit(public_agent_report(plan), text=format_plan_report(public_agent_report(plan)))
        return 0

    if command == "team":
        report = await _agent_plan(args.text, team=True)
        out.emit(report, text=format_plan_report(report) if not out.json_mode else None)
        return 0

    if command == "ask":
        answer = await ai.answer(args.text, _CLI_CONTEXT, [], _CHAT_SETTINGS)
        out.emit(answer, text=answer if not out.json_mode else None)
        return 0

    if command == "preview":
        report = await _agent_plan(args.text)
        out.emit(report, text=format_plan_report(report) if not out.json_mode else None)
        return 0

    if command == "chat":
        return await _interactive_chat(out, initial_mode=args.mode)

    if command == "agent":
        if not args.text:
            return await _interactive_chat(out, initial_mode="plan" if not args.ask else "ask")
        if args.ask:
            answer = await ai.answer(args.text, _CLI_CONTEXT, [], _CHAT_SETTINGS)
            out.emit(answer, text=answer if not out.json_mode else None)
            return 0
        report = await _agent_plan(args.text)
        out.emit(report, text=format_plan_report(report) if not out.json_mode else None)
        return 0

    if command == "skills":
        out.emit(skills_catalog())
        return 0

    if command == "roles":
        out.emit(agent_role_catalog(args.division))
        return 0

    if command == "projects":
        out.emit(await db.list_managed_projects())
        return 0

    if command == "run-profiles":
        out.emit(ManagedBotFactory(db).run_profiles())
        return 0

    return 2


def _epilog() -> str:
    return """
Examples:
  lily chat                          Interactive multi-mode session
  lily route "Lily weather in Tokyo" Fast heuristic routing (no LLM)
  lily tools weather "Tokyo"         Free API lookup
  lily scenarios list                NEXUS runbook catalog
  lily doctor --json                 Redacted health snapshot
  lily plan "Lily ban user 123"      Structured action plan
  lily team "Ship moderation inbox"  Bounded specialist review preview

Nothing executed from the CLI reaches Telegram without explicit confirmation there.
""".strip()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lily",
        description="Lily operator CLI — plan, diagnose, and preview without executing Telegram actions.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_epilog(),
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    parser.add_argument("-q", "--quiet", action="store_true", help="Suppress decorative output.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("version", help="Print CLI version.")
    sub.add_parser("status", help="Print configured model health (JSON table).")
    sub.add_parser("models", help="Pretty-print model availability.")
    sub.add_parser("config", help="Show redacted configuration flags.")
    sub.add_parser("sandbox", help="Print redacted local Ubuntu runtime capabilities.")
    sub.add_parser("doctor", help="Deployment and capability diagnostics.")

    usage = sub.add_parser("usage", help="Show request quota usage for a user/chat.")
    usage.add_argument("--user-id", type=int, default=0)
    usage.add_argument("--chat-id", type=int, default=0)

    route = sub.add_parser("route", help="Fast heuristic action routing without calling the LLM.")
    route.add_argument("text")

    search = sub.add_parser("search", help="Search the web through Lily's configured provider.")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=None)

    tools = sub.add_parser("tools", help="No-key public API lookups.")
    tools_sub = tools.add_subparsers(dest="tool_command", required=True)
    tools_sub.add_parser("catalog", help="List available free tools.")
    for name in (
        "weather", "crypto", "wiki", "define", "anime", "github", "time", "quote",
        "hn", "fact", "joke", "cat", "nasa", "country", "ip", "qr", "number",
        "translate", "fx",
    ):
        item = tools_sub.add_parser(name)
        item.add_argument("query", nargs="?", default="")

    scenarios = sub.add_parser("scenarios", help="NEXUS scenario runbooks.")
    scenario_sub = scenarios.add_subparsers(dest="scenario_command", required=True)
    scenario_sub.add_parser("list", help="List runbooks.")
    show = scenario_sub.add_parser("show", help="Show one runbook.")
    show.add_argument("slug")

    briefing = sub.add_parser("briefing", help="Operational digest (encoding queue, reports).")
    briefing.add_argument("--chat-id", type=int, default=None)

    rag_debug = sub.add_parser("rag-debug", help="Diagnose knowledge routing issues (P01–P12).")
    rag_debug.add_argument("text")

    workspace = sub.add_parser("workspace", help="Bounded code workspaces (never executes project code).")
    workspace.add_argument("--owner", default="local")
    workspace_sub = workspace.add_subparsers(dest="workspace_command", required=True)
    create = workspace_sub.add_parser("create")
    create.add_argument("project")
    create.add_argument("language", choices=("python", "javascript", "typescript", "html", "css", "json", "yaml", "bash", "java", "csharp", "go", "rust"))
    create.add_argument("brief", nargs="?", default="")
    mkdir = workspace_sub.add_parser("mkdir")
    mkdir.add_argument("project")
    mkdir.add_argument("directory")
    write = workspace_sub.add_parser("write")
    write.add_argument("project")
    write.add_argument("path")
    write.add_argument("content")
    tree = workspace_sub.add_parser("tree")
    tree.add_argument("project")
    archive = workspace_sub.add_parser("zip")
    archive.add_argument("project")
    validate = workspace_sub.add_parser("validate")
    validate.add_argument("project")

    skill_match = sub.add_parser("skill-match", help="Preview auto-skill matching.")
    skill_match.add_argument("chat_id", type=int)
    skill_match.add_argument("user_id", type=int)
    skill_match.add_argument("text")

    skill_runs = sub.add_parser("skill-runs", help="List redacted automatic-skill outcomes.")
    skill_runs.add_argument("chat_id", type=int)
    skill_runs.add_argument("--user-id", type=int, default=None)
    skill_runs.add_argument("--limit", type=int, default=20)

    service = sub.add_parser("service", help="Inspect or control an allowed managed systemd service.")
    service_sub = service.add_subparsers(dest="service_command", required=True)
    for name in ("status", "start", "stop", "restart"):
        item = service_sub.add_parser(name)
        item.add_argument("slug")
        item.add_argument("--owner", type=int, required=True)
    logs = service_sub.add_parser("logs")
    logs.add_argument("slug")
    logs.add_argument("--owner", type=int, required=True)
    logs.add_argument("--limit", type=int, default=50)

    sub.add_parser("skills", help="List Lily operating skills.")
    roles = sub.add_parser("roles", help="List specialist agent roles.")
    roles.add_argument("--division", default=None)
    sub.add_parser("projects", help="List managed bot registry records.")
    sub.add_parser("run-profiles", help="List approved managed-bot runtime profiles.")

    for name, help_text in (("plan", "Return Lily's structured action plan."), ("ask", "Ask Lily a conversational question.")):
        child = sub.add_parser(name, help=help_text)
        child.add_argument("text")

    preview = sub.add_parser("preview", help="Non-executing public action preview.")
    preview.add_argument("text")
    team = sub.add_parser("team", help="Bounded agent-team review preview.")
    team.add_argument("text")

    chat = sub.add_parser("chat", help="Interactive multi-mode CLI session.")
    chat.add_argument("--mode", choices=("ask", "plan", "build", "route", "tools"), default="plan")

    agent = sub.add_parser("agent", help="Alias for chat/plan (legacy).")
    agent.add_argument("text", nargs="?")
    agent.add_argument("--ask", action="store_true")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
