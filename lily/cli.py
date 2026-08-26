from __future__ import annotations

import argparse
import asyncio
import json

from .agent import ai
from .db import db


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
    return 2


def main() -> None:
    parser = argparse.ArgumentParser(prog="lily-agent", description="Run Lily's model-aware agent from a shell.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="Print configured model health.")
    for name, help_text in (("plan", "Return Lily's structured action plan."), ("ask", "Ask Lily a conversational question.")):
        child = sub.add_parser(name, help=help_text)
        child.add_argument("text")
    raise SystemExit(asyncio.run(run(parser.parse_args())))


if __name__ == "__main__":
    main()
