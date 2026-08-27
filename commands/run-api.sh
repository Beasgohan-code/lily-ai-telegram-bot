#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [[ -f .env ]]; then set -a; source .env; set +a; fi
export LILY_STREAM_EMBEDDED=false
exec "${LILY_PYTHON_BIN:-python3}" -m uvicorn lily.web_media:app --host "${LILY_STREAM_BIND_HOST:-127.0.0.1}" --port "${LILY_STREAM_PORT:-8090}"
