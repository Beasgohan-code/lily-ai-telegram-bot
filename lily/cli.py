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
from .agent_swarm import build_swarm, enrich_plan_with_swarm
from .deploy_agent import (
    clone_and_setup_guide,
    format_steps_markdown,
    full_install_agent,
    restart_all,
    start_api,
    start_bot,
    status_snapshot,
    stop_all,
    LOG_API,
    LOG_BOT,
)

__version__ = "2.2.0"

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
        settings.prepare()
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
        out.emit(redacted_config())
        return 0

    if command == "sandbox":
        out.emit(sandbox_status())
        return 0

    if command == "doctor":
        settings.prepare()
        await db.init()
        from .observability import build_observability
        obs = build_observability(ai.router_instance, db)
        obs_report = await obs.report(limit=50)
        models = await ai.status()
        report = {
            **redacted_config(settings),
            "model_profiles": len(models),
            "available_models": sum(bool(item.get("available")) for item in models),
            "provider_requests": obs_report["total_requests"],
            "provider_successes": obs_report["total_successes"],
            "provider_failures": obs_report["total_failures"],
            "provider_tokens": obs_report["total_tokens"],
            "database_ready": True,
            "free_tools": settings.enable_free_tools,
            "cli_version": __version__,
        }
        if out.json_mode:
            out.emit(report)
        else:
            out.banner(f"Lily Doctor  v{__version__}", "health check")
            out.section("Config")
            for key, value in report.items():
                out.kv(str(key), value)
            token_ok = bool(settings.bot_token)
            (out.success if token_ok else out.warn)(
                "TELEGRAM_BOT_TOKEN configured" if token_ok else "TELEGRAM_BOT_TOKEN missing — edit .env"
            )
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

    if command == "host":
        out.banner(f"Lily Host  v{__version__}", "local process control")
        sub = args.host_command
        if sub == "guide":
            lines = clone_and_setup_guide()
            out.emit({"guide": lines}, text=chr(10).join(lines) if not out.json_mode else None)
            return 0
        if sub == "install":
            report = full_install_agent(with_deps=True, start=False)
            text = format_steps_markdown(report)
            out.emit(report.public_dict(), text=text if not out.json_mode else None)
            return 0 if report.ok else 1
        if sub == "status":
            snap = status_snapshot()
            if out.json_mode:
                out.emit(snap)
            else:
                out.section("Environment")
                out.kv("root", snap["root"])
                out.kv("env", "ok" if snap["env_ok"] else "MISSING / incomplete")
                out.section("Processes")
                bot = snap["bot"]
                api = snap["api"]
                out.kv("bot", f"{'running' if bot['running'] else 'stopped'}  pid={bot['pid'] or '—'}")
                out.kv("api", f"{'running' if api['running'] else 'stopped'}  pid={api['pid'] or '—'}")
                out.kv("bot log", bot["log"])
                out.kv("api log", api["log"])
            return 0
        if sub == "start":
            bot = start_bot()
            if out.json_mode:
                payload = {"bot": {"ok": bot.ok, "detail": bot.detail}}
            else:
                (out.success if bot.ok else out.error)(f"bot: {bot.detail}")
            if not bot.ok:
                out.emit({"ok": False, "bot": bot.detail} if out.json_mode else None)
                return 1
            if getattr(args, "api", False):
                api = start_api(port=getattr(args, "port", None))
                if out.json_mode:
                    payload["api"] = {"ok": api.ok, "detail": api.detail}
                    out.emit(payload)
                else:
                    (out.success if api.ok else out.error)(f"api: {api.detail}")
                return 0 if api.ok else 1
            if out.json_mode:
                out.emit({"ok": True, "bot": bot.detail})
            return 0
        if sub == "stop":
            steps = stop_all()
            if out.json_mode:
                out.emit({"steps": [{"name": s.name, "detail": s.detail} for s in steps]})
            else:
                for s in steps:
                    out.success(s.detail)
            return 0
        if sub == "restart":
            report = restart_all(with_api=getattr(args, "api", False), port=getattr(args, "port", None))
            text = format_steps_markdown(report)
            out.emit(report.public_dict(), text=text if not out.json_mode else None)
            return 0 if report.ok else 1
        if sub == "logs":
            log_path = LOG_API if getattr(args, "api", False) else LOG_BOT
            tail_n = max(1, min(int(getattr(args, "tail", 40) or 40), 500))
            if not log_path.exists():
                out.warn(f"No log yet at {log_path}")
                return 0
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-tail_n:]
            out.emit({"path": str(log_path), "lines": lines}, text=chr(10).join(lines) if not out.json_mode else None)
            return 0
        out.error(f"Unknown host command: {sub}")
        return 2

    if command == "swarm":
        out.banner(f"Lily Agent Swarm  v{__version__}", "specialist squad preview")
        plan = await _agent_plan(args.text, team=True)
        # rebuild a Plan-like object is heavy; use heuristic + swarm from action
        from .agent import AIClient
        raw = AIClient().heuristic_plan(args.text, _CLI_CONTEXT)
        plan_obj = raw
        plan_obj, swarm_obj = enrich_plan_with_swarm(plan_obj, args.text)
        payload = {
            "plan": plan,
            "swarm": swarm_obj.public_dict(),
            "stages": swarm_obj.stages(),
        }
        if out.json_mode:
            out.emit(payload)
        else:
            out.section("Lead")
            out.kv("lead", swarm_obj.lead)
            out.kv("specialists", len(swarm_obj.members))
            out.section("Squad")
            rows = [[m.role.name, m.role.division, m.role.deliverable[:36]] for m in swarm_obj.members]
            out.table(["Agent", "Division", "Deliverable"], rows)
            out.section("Stages")
            for i, s in enumerate(swarm_obj.stages(), 1):
                print(f"  {i}. {s}")
        return 0

    if command == "deploy":
        out.banner(f"Lily Deploy Agent  v{__version__}", "install → configure → run")
        report = full_install_agent(
            with_deps=not getattr(args, "no_deps", False),
            start=bool(getattr(args, "start", False)),
            with_api=bool(getattr(args, "api", False)),
        )
        text = format_steps_markdown(report)
        if not out.json_mode:
            print(text)
            if report.ok and not getattr(args, "start", False):
                out.success("Next: python3 -m lily.cli host start")
        else:
            out.emit(report.public_dict())
        return 0 if report.ok else 1

    return 2


def _epilog() -> str:
    return """
Examples:
  lily host guide                 Full git clone + VPS deploy steps
  lily deploy --start             Install deps, ensure .env, start bot
  lily host start                 Background bot (logs: .lily_run/bot.log)
  lily host start --api           Bot + FastAPI bridge
  lily host status                Process + env snapshot
  lily host logs --tail 80        Tail bot log
  lily host stop | restart        Lifecycle control
  lily plan "mute this user 15m"  Non-executing action plan
  lily chat                       Interactive operator session
"""


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
    swarm = sub.add_parser("swarm", help="Advanced multi-agent swarm preview for a request.")
    swarm.add_argument("text")

    chat = sub.add_parser("chat", help="Interactive multi-mode CLI session.")
    chat.add_argument("--mode", choices=("ask", "plan", "build", "route", "tools"), default="plan")

    agent = sub.add_parser("agent", help="Alias for chat/plan (legacy).")
    agent.add_argument("text", nargs="?")
    agent.add_argument("--ask", action="store_true")

    # Professional hosting / deploy operator commands
    host = sub.add_parser("host", help="Install, start, stop, restart, and status for local Lily hosting.")
    host_sub = host.add_subparsers(dest="host_command", required=True)
    host_sub.add_parser("install", help="Create dirs, .env, install Python deps.")
    host_start = host_sub.add_parser("start", help="Start Lily bot in background (optional API bridge).")
    host_start.add_argument("--api", action="store_true", help="Also start the FastAPI bridge.")
    host_start.add_argument("--port", type=int, default=None, help="API port (default PORT or 8080).")
    host_sub.add_parser("stop", help="Stop background bot and API processes Lily started.")
    host_restart = host_sub.add_parser("restart", help="Stop then start Lily.")
    host_restart.add_argument("--api", action="store_true")
    host_restart.add_argument("--port", type=int, default=None)
    host_sub.add_parser("status", help="Show process and environment status.")
    host_logs = host_sub.add_parser("logs", help="Tail bot/API logs.")
    host_logs.add_argument("--tail", type=int, default=40)
    host_logs.add_argument("--api", action="store_true", help="Show API log instead of bot log.")
    host_sub.add_parser("guide", help="Print full git clone + deploy steps for a VPS.")

    deploy = sub.add_parser("deploy", help="Run the full install agent (dirs, env, deps, optional start).")
    deploy.add_argument("--start", action="store_true", help="Start the bot after install.")
    deploy.add_argument("--api", action="store_true", help="Also start the API bridge.")
    deploy.add_argument("--no-deps", action="store_true", help="Skip pip install.")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
