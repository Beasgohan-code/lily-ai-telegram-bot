#!/usr/bin/env bash
# Full install agent: dirs → .env → pip → optional start
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [[ -f .env ]]; then set -a; source .env; set +a; fi
PY="${LILY_PYTHON_BIN:-python3}"
exec "$PY" -m lily.cli deploy "$@"
