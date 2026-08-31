#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${RUNPOD_WORKER_ROOT:-/opt/allbot/runpod_worker}"
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

shutdown_children() {
    local status="${1:-0}"
    trap - INT TERM
    for pid in "${EMBEDDED_TEST_AGENT_PID:-}" "${AGENT_PID:-}" "${RELAY_PID:-}" "${COMFY_PID:-}"; do
        if [ -n "$pid" ] && kill -0 "$pid" >/dev/null 2>&1; then
            kill "$pid" >/dev/null 2>&1 || true
        fi
    done
    for pid in "${EMBEDDED_TEST_AGENT_PID:-}" "${AGENT_PID:-}" "${RELAY_PID:-}" "${COMFY_PID:-}"; do
        if [ -n "$pid" ]; then
            wait "$pid" >/dev/null 2>&1 || true
        fi
    done
    exit "$status"
}

handle_signal() {
    shutdown_children 143
}

trap handle_signal INT TERM

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

ensure_wan22_rife_cache() {
    if [ ! -f "$ROOT_DIR/scripts/ensure_wan22_rife_cache.py" ]; then
        return
    fi
    local comfyui_dir="${RUNPOD_RIFE_COMFYUI_DIR:-}"
    if [ -z "$comfyui_dir" ]; then
        if [ -n "${COMFYUI_DIR:-}" ] && [ -f "${COMFYUI_DIR}/main.py" ]; then
            comfyui_dir="$COMFYUI_DIR"
        elif baked_comfyui_dir="$(resolve_baked_comfyui_dir)"; then
            comfyui_dir="$baked_comfyui_dir"
        elif [ -f /workspace/ComfyUI/main.py ]; then
            comfyui_dir=/workspace/ComfyUI
        elif [ -f /default-comfyui-bundle/ComfyUI/main.py ]; then
            comfyui_dir=/default-comfyui-bundle/ComfyUI
        elif [ -f /root/ComfyUI/main.py ]; then
            comfyui_dir=/root/ComfyUI
        fi
    fi
    if [ -n "$comfyui_dir" ]; then
        python3 "$ROOT_DIR/scripts/ensure_wan22_rife_cache.py" \
            --comfyui-dir "$comfyui_dir" \
            --model-target-dir "${RUNPOD_MODEL_TARGET_DIR:-${comfyui_dir%/}/models}"
    else
        python3 "$ROOT_DIR/scripts/ensure_wan22_rife_cache.py"
    fi
}

COMFY_RUNTIME_DIR="${COMFY_ARTIFACT_ROOT_DIR:-}"
ensure_wan22_rife_cache

if [ -n "${COMFYUI_DIR:-}" ] && [ -f "${COMFYUI_DIR}/main.py" ]; then
    COMFY_RUNTIME_DIR="${COMFY_RUNTIME_DIR:-$COMFYUI_DIR}"
    (
        cd "$COMFYUI_DIR"
        python3 main.py --listen 0.0.0.0 --port 8188 ${COMFY_EXTRA_ARGS:-}
    ) &
    COMFY_PID="$!"
elif [ -n "${COMFY_START_CMD:-}" ]; then
    bash -lc "$COMFY_START_CMD" &
    COMFY_PID="$!"
elif baked_comfyui_dir="$(resolve_baked_comfyui_dir)"; then
    COMFY_RUNTIME_DIR="${COMFY_RUNTIME_DIR:-$baked_comfyui_dir}"
    (
        cd "$baked_comfyui_dir"
        python3 main.py --listen 0.0.0.0 --port 8188 ${COMFY_EXTRA_ARGS:-}
    ) &
    COMFY_PID="$!"
elif [ -f /workspace/ComfyUI/main.py ]; then
    COMFY_RUNTIME_DIR="${COMFY_RUNTIME_DIR:-/workspace/ComfyUI}"
    (
        cd /workspace/ComfyUI
        python3 main.py --listen 0.0.0.0 --port 8188 ${COMFY_EXTRA_ARGS:-}
    ) &
    COMFY_PID="$!"
elif [ -f /default-comfyui-bundle/ComfyUI/main.py ]; then
    COMFY_RUNTIME_DIR="${COMFY_RUNTIME_DIR:-/default-comfyui-bundle/ComfyUI}"
    (
        cd /default-comfyui-bundle/ComfyUI
        python3 main.py --listen 0.0.0.0 --port 8188 ${COMFY_EXTRA_ARGS:-}
    ) &
    COMFY_PID="$!"
else
    echo "COMFY_START_CMD is not set and no known ComfyUI main.py path was found; assuming template starts ComfyUI."
    COMFY_PID=""
fi

if [ -n "$COMFY_RUNTIME_DIR" ]; then
    export COMFY_ARTIFACT_INPUT_DIR="${COMFY_ARTIFACT_INPUT_DIR:-${COMFY_RUNTIME_DIR%/}/input}"
    export COMFY_ARTIFACT_OUTPUT_DIR="${COMFY_ARTIFACT_OUTPUT_DIR:-${COMFY_RUNTIME_DIR%/}/output}"
    export COMFY_ARTIFACT_TEMP_DIR="${COMFY_ARTIFACT_TEMP_DIR:-${COMFY_RUNTIME_DIR%/}/temp}"
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

RUNPOD_WORKER_ENV_FILE="${RUNPOD_WORKER_ENV_FILE:-}" python3 -m runpod_relay.relay_main &
RELAY_PID="$!"

relay_deadline=$(( $(date +%s) + RELAY_READY_TIMEOUT_SECONDS ))
until curl -fsS "http://${LOCAL_RELAY_HOST}:${LOCAL_RELAY_PORT}/ready" >/dev/null 2>&1; do
    if [ "$(date +%s)" -ge "$relay_deadline" ]; then
        echo "RunPod relay did not become ready before timeout." >&2
        kill "$RELAY_PID" >/dev/null 2>&1 || true
        if [ -n "${COMFY_PID:-}" ]; then
            kill "$COMFY_PID" >/dev/null 2>&1 || true
        fi
        exit 75
    fi
    sleep 2
done

python3 "$ROOT_DIR/comfy_agent/agent_main.py" &
AGENT_PID="$!"

EMBEDDED_TEST_AGENT_PID=""
if [ "${RUNPOD_EMBEDDED_TEST_AGENT_ENABLED:-false}" = "true" ]; then
    bash "$ROOT_DIR/scripts/runpod_embedded_test_agent.sh" &
    EMBEDDED_TEST_AGENT_PID="$!"
fi

echo "Process supervisor watching agent=${AGENT_PID} relay=${RELAY_PID} comfy=${COMFY_PID:-external} embedded_test=${EMBEDDED_TEST_AGENT_PID:-disabled}"
managed_pids=("$AGENT_PID" "$RELAY_PID")
if [ -n "${COMFY_PID:-}" ]; then
    managed_pids+=("$COMFY_PID")
fi
if [ -n "$EMBEDDED_TEST_AGENT_PID" ]; then
    managed_pids+=("$EMBEDDED_TEST_AGENT_PID")
fi
set +e
wait -n "${managed_pids[@]}"
supervised_status="$?"
set -e

echo "A managed process exited with status ${supervised_status}; stopping container for restart policy"
shutdown_children "$supervised_status"
