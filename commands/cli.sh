#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [[ -f .env ]]; then set -a; source .env; set +a; fi
if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]] && [[ $# -eq 1 ]]; then
  exec "${LILY_PYTHON_BIN:-python3}" -m lily.cli --help
fi
exec "${LILY_PYTHON_BIN:-python3}" -m lily.cli "$@"
