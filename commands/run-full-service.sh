#!/usr/bin/env bash
# Starts the request-driven bridge and Telegram bot together on a platform that
# offers one persistent service and one mounted data volume.
set -euo pipefail

: "${PORT:?The hosting platform must provide PORT.}"

api_pid=""
bot_pid=""

shutdown() {
  for pid in "$api_pid" "$bot_pid"; do
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      kill -TERM "$pid" 2>/dev/null || true
    fi
  done
  wait || true
}

trap shutdown EXIT INT TERM

python3 -m uvicorn lily.web_media:create_app --factory --host 0.0.0.0 --port "$PORT" &
api_pid="$!"
python3 -m lily.main &
bot_pid="$!"

# A shared-state deployment is not healthy when either the bot or bridge exits.
wait -n "$api_pid" "$bot_pid"
