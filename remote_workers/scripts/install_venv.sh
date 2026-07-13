#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

cd "$ROOT_DIR"
if [ ! -x .venv/bin/python ]; then
    "$PYTHON_BIN" -m venv .venv
fi
. .venv/bin/activate

if [ "${UPDATE_DEPS:-0}" = "1" ] || [ ! -f .venv/.remote_worker_deps_installed ]; then
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
    date -Iseconds > .venv/.remote_worker_deps_installed
fi

echo "Remote worker venv is ready: $ROOT_DIR/.venv"
