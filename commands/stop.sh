#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
exec "${LILY_PYTHON_BIN:-python3}" -m lily.cli host stop "$@"
