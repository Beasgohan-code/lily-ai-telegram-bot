#!/usr/bin/env bash
# Professional Lily host control: install | start | stop | restart | status | logs | guide
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [[ -f .env ]]; then set -a; source .env; set +a; fi
PY="${LILY_PYTHON_BIN:-python3}"
exec "$PY" -m lily.cli host "$@"
