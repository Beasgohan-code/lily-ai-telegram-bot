#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
"${LILY_PYTHON_BIN:-python3}" -m compileall -q lily
"${LILY_PYTHON_BIN:-python3}" -m unittest discover -s tests -v
