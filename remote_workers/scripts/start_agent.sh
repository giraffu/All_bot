#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${1:-$ROOT_DIR/env/worker_remote_01.agent.env}"
BASE_ENV_FILE="${2:-${ENV_FILE/.agent.env/.relay.env}}"

if [ ! -x "$ROOT_DIR/.venv/bin/python" ]; then
    bash "$ROOT_DIR/scripts/install_venv.sh"
fi

cd "$ROOT_DIR"

if [ -f "$BASE_ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$BASE_ENV_FILE"
    set +a
fi

if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$ENV_FILE"
    set +a
fi

RELAY_PORT="${LOCAL_RELAY_PORT:-8013}"
export AGENT_ID="${AGENT_ID:-${REMOTE_WORKER_ID:-worker_remote_01}}"
export MASTER_API_URL="${MASTER_API_URL:-http://127.0.0.1:$RELAY_PORT}"
export UPLOAD_SIDECAR_URL="${UPLOAD_SIDECAR_URL:-http://127.0.0.1:$RELAY_PORT}"
export SUPPORTED_TASK_TYPES="${SUPPORTED_TASK_TYPES:-img2img}"
export COMFY_API_URL="${COMFY_API_URL:-http://127.0.0.1:8111/}"
export COMFY_WS_URL="${COMFY_WS_URL:-ws://127.0.0.1:8111/ws}"
export COMFY_INPUT_DIR="${COMFY_INPUT_DIR:-./input}"
export COMFY_OUTPUT_DIR="${COMFY_OUTPUT_DIR:-./output}"
export MINIO_INPUT_BUCKET="${MINIO_INPUT_BUCKET:-user-data-prod}"
export MINIO_RESULT_BUCKET="${MINIO_RESULT_BUCKET:-user-data-prod}"
export MINIO_TEMPLATE_BUCKET="${MINIO_TEMPLATE_BUCKET:-user-data-prod}"
export MINIO_SECURE="${MINIO_SECURE:-true}"
export RESULT_SPOOL_DIR="${RESULT_SPOOL_DIR:-./spool/$AGENT_ID}"
export PREFETCH_CACHE_DIR="${PREFETCH_CACHE_DIR:-./prefetch-cache/$AGENT_ID}"
export AGENT_LOG_DIR="${AGENT_LOG_DIR:-./logs}"
export PREFETCH_ENABLED="${PREFETCH_ENABLED:-false}"
export PIPELINE_ENABLED="${PIPELINE_ENABLED:-false}"
export CANCEL_LOCK_ON_POP="${CANCEL_LOCK_ON_POP:-true}"
export NO_PROXY="*"
export no_proxy="*"

mkdir -p "$COMFY_INPUT_DIR" "$COMFY_OUTPUT_DIR" "$RESULT_SPOOL_DIR" "$PREFETCH_CACHE_DIR" "$AGENT_LOG_DIR"

exec "$ROOT_DIR/.venv/bin/python" "$ROOT_DIR/comfy_agent/agent_main.py"
