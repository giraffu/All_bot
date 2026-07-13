#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${1:-$ROOT_DIR/env/worker_remote_01.relay.env}"

if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$ENV_FILE"
    set +a
fi

HOST="${LOCAL_RELAY_HOST:-127.0.0.1}"
PORT="${LOCAL_RELAY_PORT:-8013}"
curl --noproxy '*' -fsS "http://${HOST}:${PORT}/health"
echo

