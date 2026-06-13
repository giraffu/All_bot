#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${RUNPOD_REMOTE_WORKER_ROOT:-/opt/allbot/remote_workers}"
COMFY_READY_TIMEOUT_SECONDS="${RUNPOD_COMFY_READY_TIMEOUT_SECONDS:-900}"
COMFY_READY_INTERVAL_SECONDS="${RUNPOD_COMFY_READY_INTERVAL_SECONDS:-5}"
RELAY_READY_TIMEOUT_SECONDS="${RUNPOD_RELAY_READY_TIMEOUT_SECONDS:-120}"
LOCAL_RELAY_HOST="${LOCAL_RELAY_HOST:-127.0.0.1}"
LOCAL_RELAY_PORT="${LOCAL_RELAY_PORT:-8013}"
RUNPOD_POD_ID_SAFE="${RUNPOD_POD_ID:-${POD_ID:-pending}}"

if [ -z "${AGENT_ID:-}" ] || [[ "${AGENT_ID}" == *'${RUNPOD_POD_ID'* ]] || [[ "${AGENT_ID}" == *'${POD_ID'* ]]; then
    export AGENT_ID="${AGENT_ID_PREFIX:-runpod_test_img2img_lora}_${RUNPOD_POD_ID_SAFE}"
else
    export AGENT_ID
fi

export NO_PROXY="${NO_PROXY:-*}"
export no_proxy="${no_proxy:-*}"
export MASTER_API_URL="${MASTER_API_URL:-http://${LOCAL_RELAY_HOST}:${LOCAL_RELAY_PORT}}"
export UPLOAD_SIDECAR_URL="${UPLOAD_SIDECAR_URL:-http://${LOCAL_RELAY_HOST}:${LOCAL_RELAY_PORT}}"
export SUPPORTED_TASK_TYPES="${SUPPORTED_TASK_TYPES:-img2img,img2img_lora}"
export COMFY_API_URL="${COMFY_API_URL:-http://127.0.0.1:8188}"
export COMFY_WS_URL="${COMFY_WS_URL:-ws://127.0.0.1:8188/ws}"
export COMFY_INPUT_DIR="${COMFY_INPUT_DIR:-./input}"
export COMFY_OUTPUT_DIR="${COMFY_OUTPUT_DIR:-./output}"
export MINIO_INPUT_BUCKET="${MINIO_INPUT_BUCKET:-user-data-test}"
export MINIO_RESULT_BUCKET="${MINIO_RESULT_BUCKET:-user-data-test}"
export MINIO_TEMPLATE_BUCKET="${MINIO_TEMPLATE_BUCKET:-user-data-test}"
export MINIO_SECURE="${MINIO_SECURE:-true}"
export PIPELINE_ENABLED="${PIPELINE_ENABLED:-true}"
export PIPELINE_MAX_RUNNING_TASKS="${PIPELINE_MAX_RUNNING_TASKS:-1}"
export PREFETCH_ENABLED="${PREFETCH_ENABLED:-false}"
export CANCEL_LOCK_ON_POP="${CANCEL_LOCK_ON_POP:-true}"
export RESULT_SPOOL_DIR="${RESULT_SPOOL_DIR:-./spool/${AGENT_ID:-runpod_worker}}"
export PREFETCH_CACHE_DIR="${PREFETCH_CACHE_DIR:-./prefetch-cache/${AGENT_ID:-runpod_worker}}"

cd "$ROOT_DIR"
mkdir -p "$COMFY_INPUT_DIR" "$COMFY_OUTPUT_DIR" "$RESULT_SPOOL_DIR" "$PREFETCH_CACHE_DIR" logs

resolve_baked_comfyui_dir() {
    if [ -f /opt/allbot-comfyui-dir ]; then
        local baked_dir
        baked_dir="$(cat /opt/allbot-comfyui-dir)"
        if [ -n "$baked_dir" ] && [ -f "${baked_dir}/main.py" ]; then
            printf '%s\n' "$baked_dir"
            return 0
        fi
    fi
    return 1
}

if [ -n "${COMFYUI_DIR:-}" ] && [ -f "${COMFYUI_DIR}/main.py" ]; then
    (
        cd "$COMFYUI_DIR"
        python3 main.py --listen 0.0.0.0 --port 8188 ${COMFY_EXTRA_ARGS:-}
    ) &
    COMFY_PID="$!"
elif [ -n "${COMFY_START_CMD:-}" ]; then
    bash -lc "$COMFY_START_CMD" &
    COMFY_PID="$!"
elif baked_comfyui_dir="$(resolve_baked_comfyui_dir)"; then
    (
        cd "$baked_comfyui_dir"
        python3 main.py --listen 0.0.0.0 --port 8188 ${COMFY_EXTRA_ARGS:-}
    ) &
    COMFY_PID="$!"
elif [ -f /workspace/ComfyUI/main.py ]; then
    (
        cd /workspace/ComfyUI
        python3 main.py --listen 0.0.0.0 --port 8188 ${COMFY_EXTRA_ARGS:-}
    ) &
    COMFY_PID="$!"
elif [ -f /default-comfyui-bundle/ComfyUI/main.py ]; then
    (
        cd /default-comfyui-bundle/ComfyUI
        python3 main.py --listen 0.0.0.0 --port 8188 ${COMFY_EXTRA_ARGS:-}
    ) &
    COMFY_PID="$!"
else
    echo "COMFY_START_CMD is not set and no known ComfyUI main.py path was found; assuming template starts ComfyUI."
    COMFY_PID=""
fi

deadline=$(( $(date +%s) + COMFY_READY_TIMEOUT_SECONDS ))
until curl -fsS "${COMFY_API_URL%/}/system_stats" >/dev/null 2>&1; do
    if [ "$(date +%s)" -ge "$deadline" ]; then
        echo "ComfyUI did not become ready before timeout: ${COMFY_API_URL}" >&2
        if [ -n "${COMFY_PID:-}" ]; then
            kill "$COMFY_PID" >/dev/null 2>&1 || true
        fi
        exit 75
    fi
    sleep "$COMFY_READY_INTERVAL_SECONDS"
done

REMOTE_WORKER_ENV_FILE="${REMOTE_WORKER_ENV_FILE:-}" python3 -m remote_relay.relay_main &
RELAY_PID="$!"

relay_deadline=$(( $(date +%s) + RELAY_READY_TIMEOUT_SECONDS ))
until curl -fsS "http://${LOCAL_RELAY_HOST}:${LOCAL_RELAY_PORT}/ready" >/dev/null 2>&1; do
    if [ "$(date +%s)" -ge "$relay_deadline" ]; then
        echo "Remote relay did not become ready before timeout." >&2
        kill "$RELAY_PID" >/dev/null 2>&1 || true
        if [ -n "${COMFY_PID:-}" ]; then
            kill "$COMFY_PID" >/dev/null 2>&1 || true
        fi
        exit 75
    fi
    sleep 2
done

python3 "$ROOT_DIR/comfy_agent/agent_main.py"
