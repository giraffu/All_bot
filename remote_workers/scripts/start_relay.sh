#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${1:-$ROOT_DIR/env/worker_remote_01.relay.env}"

if [ ! -f "$ENV_FILE" ]; then
    echo "Env file not found: $ENV_FILE"
    echo "Copy env/*.example to a real .env file first."
    exit 1
fi

if [ ! -x "$ROOT_DIR/.venv/bin/python" ]; then
    echo "Venv not found. Run: bash scripts/install_venv.sh"
    exit 1
fi

cd "$ROOT_DIR"
set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a
export REMOTE_WORKER_ENV_FILE="$ENV_FILE"

mkdir -p "${RESULT_SPOOL_DIR:-./spool}" logs
exec "$ROOT_DIR/.venv/bin/python" -m remote_relay.relay_main

