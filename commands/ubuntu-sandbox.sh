#!/usr/bin/env bash
set -euo pipefail

# Safe local operator entrypoint. It intentionally provides only Lily's fixed
# controls and never interprets user input as an arbitrary shell command.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

usage() {
  cat <<'EOF'
Lily Ubuntu Console

Usage: ./commands/ubuntu-sandbox.sh <command> [arguments]

Safe controls:
  doctor                 Print redacted local diagnostics
  sandbox                Print bounded local-runtime capabilities
  status                 Print model/provider health
  profiles               List fixed approved managed-bot run profiles
  search <query>         Search through Lily's configured web-search provider
  workspace <action> …   Create, edit, list, ZIP, or validate an isolated code workspace
  skill-match <chat> <user> <text>  Preview automatic skill selection; never executes
  skill-runs <chat> [options]       List redacted automatic-skill outcomes
  plan <request>         Print a structured local plan
  preview <request>      Print public stages only; never executes
  agent [request]        Run Lily's safe planning agent (interactive when omitted)
  ask <question>         Ask Lily a local conversational question
  check                  Compile and run regression tests
  bot                    Start Lily's Telegram worker in this terminal
  api                    Start Lily's FastAPI service in this terminal

`bot` and `api` are foreground commands. Use systemd or Docker on a persistent
Ubuntu host for production supervision. This launcher accepts no shell commands.
EOF
}

command="${1:-help}"
case "$command" in
  help|-h|--help)
    usage
    ;;
  doctor|sandbox|status|profiles)
    case "$command" in
      profiles) exec ./commands/cli.sh run-profiles ;;
      *) exec ./commands/cli.sh "$command" ;;
    esac
    ;;
  plan|preview|ask|search)
    shift
    if [[ "$#" -eq 0 ]]; then
      echo "Error: $command needs a request." >&2
      exit 2
    fi
    if [[ "$command" == "ask" ]]; then
      exec ./commands/cli.sh ask "$*"
    fi
    if [[ "$command" == "search" ]]; then
      exec ./commands/cli.sh search "$*"
    fi
    exec ./commands/cli.sh "$command" "$*"
    ;;
  agent)
    shift
    exec ./commands/cli.sh agent "$@"
    ;;
  workspace)
    shift
    exec ./commands/cli.sh workspace "$@"
    ;;
  skill-match|skill-runs)
    shift
    exec ./commands/cli.sh "$command" "$@"
    ;;
  check)
    exec ./commands/check.sh
    ;;
  bot)
    exec ./commands/run-bot.sh
    ;;
  api)
    exec ./commands/run-api.sh
    ;;
  *)
    echo "Unknown command: $command" >&2
    usage >&2
    exit 2
    ;;
esac
