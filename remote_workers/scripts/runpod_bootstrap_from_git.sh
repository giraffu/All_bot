#!/usr/bin/env bash
set -euo pipefail

LOG_FILE="${RUNPOD_BOOTSTRAP_LOG_FILE:-/tmp/allbot-runpod-bootstrap.log}"
touch "$LOG_FILE"
exec > >(tee -a "$LOG_FILE") 2>&1

log() {
    printf '[runpod-bootstrap] %s\n' "$*"
}

keepalive_on_failure() {
    local status="$1"
    log "bootstrap failed with exit status ${status}"
    if [ "${RUNPOD_KEEPALIVE_ON_BOOTSTRAP_FAILURE:-false}" = "true" ]; then
        log "RUNPOD_KEEPALIVE_ON_BOOTSTRAP_FAILURE=true; keeping container alive for SSH diagnostics"
        while true; do
            sleep 3600
        done
    fi
    exit "$status"
}
trap 'keepalive_on_failure "$?"' ERR

start_sshd_for_diagnostics() {
    if [ "${RUNPOD_START_SSHD:-true}" != "true" ]; then
        return
    fi
    if ! command -v sshd >/dev/null 2>&1; then
        if [ "${RUNPOD_INSTALL_SSHD_IF_MISSING:-true}" = "true" ] && command -v apt-get >/dev/null 2>&1; then
            log "sshd not found; installing openssh-server for direct TCP diagnostics"
            apt-get update
            DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends openssh-server
            rm -rf /var/lib/apt/lists/*
        fi
        if ! command -v sshd >/dev/null 2>&1; then
            log "sshd still unavailable; direct TCP SSH will be unavailable"
            return
        fi
    fi

    mkdir -p /root/.ssh /run/sshd
    chmod 700 /root/.ssh
    if [ -n "${PUBLIC_KEY:-}" ]; then
        printf '%s\n' "${PUBLIC_KEY}" | awk '/^ssh-/' > /root/.ssh/authorized_keys
        chmod 600 /root/.ssh/authorized_keys
    fi
    if command -v ssh-keygen >/dev/null 2>&1; then
        ssh-keygen -A >/dev/null 2>&1 || true
    fi
    if pgrep -x sshd >/dev/null 2>&1; then
        log "sshd already running"
    else
        /usr/sbin/sshd
        log "sshd started for direct TCP diagnostics"
    fi
}
start_sshd_for_diagnostics

ROOT_DIR="${ALLBOT_RUNPOD_ROOT:-/workspace/allbot}"
REPO_URL="${ALLBOT_RUNPOD_GIT_URL:-https://github.com/giraffu/All_bot.git}"
REPO_BRANCH="${ALLBOT_RUNPOD_GIT_BRANCH:-deploy}"
REPO_DIR="${ALLBOT_RUNPOD_REPO_DIR:-${ROOT_DIR}/repo}"
REMOTE_WORKERS_DIR="${ALLBOT_RUNPOD_REMOTE_WORKERS_DIR:-${REPO_DIR}/remote_workers}"
WORKSPACE_DIR="${RUNPOD_WORKSPACE_DIR:-/workspace}"
VOLUME_COMFYUI_DIR="${RUNPOD_VOLUME_COMFYUI_DIR:-${WORKSPACE_DIR}/ComfyUI}"
PIP_CACHE_DIR="${PIP_CACHE_DIR:-${WORKSPACE_DIR}/.cache/pip}"
COMFY_READY_TIMEOUT_SECONDS="${RUNPOD_COMFY_READY_TIMEOUT_SECONDS:-900}"
COMFY_READY_INTERVAL_SECONDS="${RUNPOD_COMFY_READY_INTERVAL_SECONDS:-5}"
RELAY_READY_TIMEOUT_SECONDS="${RUNPOD_RELAY_READY_TIMEOUT_SECONDS:-120}"
RELAY_READY_PATH="${RUNPOD_RELAY_READY_PATH:-/health}"
LOCAL_RELAY_HOST="${LOCAL_RELAY_HOST:-127.0.0.1}"
LOCAL_RELAY_PORT="${LOCAL_RELAY_PORT:-8013}"
RUNPOD_POD_ID_SAFE="${RUNPOD_POD_ID:-${POD_ID:-$(hostname 2>/dev/null || echo pending)}}"

cleanup() {
    if [ -n "${RELAY_PID:-}" ]; then
        kill "$RELAY_PID" >/dev/null 2>&1 || true
    fi
    if [ -n "${COMFY_PID:-}" ]; then
        kill "$COMFY_PID" >/dev/null 2>&1 || true
    fi
}
trap cleanup INT TERM

if [ -z "${AGENT_ID:-}" ] || [[ "${AGENT_ID}" == *'${RUNPOD_POD_ID'* ]] || [[ "${AGENT_ID}" == *'${POD_ID'* ]]; then
    export AGENT_ID="${AGENT_ID_PREFIX:-runpod_test_img2img_lora}_${RUNPOD_POD_ID_SAFE}"
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
export PIP_CACHE_DIR

mkdir -p "$ROOT_DIR"
if [ -d "${REMOTE_WORKERS_DIR}/comfy_agent" ] && [ -f "${REMOTE_WORKERS_DIR}/requirements.txt" ]; then
    log "using existing AllBot remote worker bundle at ${REMOTE_WORKERS_DIR}"
else
    log "cloning AllBot remote worker bundle"
    rm -rf "$REPO_DIR"
    git clone --depth 1 --branch "$REPO_BRANCH" "$REPO_URL" "$REPO_DIR"
fi

cd "$REMOTE_WORKERS_DIR"
export PYTHONPATH="${REMOTE_WORKERS_DIR}:${REPO_DIR}:${PYTHONPATH:-}"
python3 - <<'PY'
from pathlib import Path

relay_path = Path("remote_relay/relay_main.py")
if relay_path.exists():
    text = relay_path.read_text(encoding="utf-8")
    text = text.replace(
        "async def update_status(request: Request) -> dict[str, str] | JSONResponse:",
        "async def update_status(request: Request):",
    )
    relay_path.write_text(text, encoding="utf-8")
PY
python3 -m pip install -r requirements.txt
mkdir -p "$COMFY_INPUT_DIR" "$COMFY_OUTPUT_DIR" "$RESULT_SPOOL_DIR" "$PREFETCH_CACHE_DIR" logs

if [ "${RUNPOD_PREPARE_COMFYUI_ON_VOLUME:-false}" = "true" ] \
    && [ ! -f "${VOLUME_COMFYUI_DIR}/main.py" ] \
    && [ -f /default-comfyui-bundle/ComfyUI/main.py ]; then
    log "seeding ComfyUI bundle into ${VOLUME_COMFYUI_DIR}"
    mkdir -p "$VOLUME_COMFYUI_DIR"
    cp -a /default-comfyui-bundle/ComfyUI/. "$VOLUME_COMFYUI_DIR/"
fi

resolve_comfyui_dir_for_models() {
    if [ -n "${COMFYUI_DIR:-}" ] && [ -f "${COMFYUI_DIR}/main.py" ]; then
        printf '%s\n' "$COMFYUI_DIR"
    elif [ -f "${VOLUME_COMFYUI_DIR}/main.py" ]; then
        printf '%s\n' "$VOLUME_COMFYUI_DIR"
    elif [ -f /workspace/ComfyUI/main.py ]; then
        printf '%s\n' "/workspace/ComfyUI"
    elif [ -f /default-comfyui-bundle/ComfyUI/main.py ]; then
        printf '%s\n' "/default-comfyui-bundle/ComfyUI"
    else
        return 1
    fi
}

if [ "${RUNPOD_MODEL_SYNC_ENABLED:-false}" = "true" ]; then
    COMFYUI_MODEL_SYNC_DIR="${RUNPOD_MODEL_COMFYUI_DIR:-}"
    if [ -z "$COMFYUI_MODEL_SYNC_DIR" ]; then
        if resolved_comfy_dir="$(resolve_comfyui_dir_for_models)"; then
            COMFYUI_MODEL_SYNC_DIR="$resolved_comfy_dir"
        fi
    fi
    if [ -z "$COMFYUI_MODEL_SYNC_DIR" ]; then
        echo "RUNPOD_MODEL_SYNC_ENABLED=true but no ComfyUI directory was found." >&2
        exit 75
    fi
    export RUNPOD_MODEL_TARGET_DIR="${RUNPOD_MODEL_TARGET_DIR:-${COMFYUI_MODEL_SYNC_DIR%/}/models}"
    log "syncing RunPod model bundle into ${RUNPOD_MODEL_TARGET_DIR}"
    python3 "$REMOTE_WORKERS_DIR/scripts/runpod_sync_models_from_r2.py" \
        --bucket "${RUNPOD_MODEL_BUCKET:-}" \
        --prefix "${RUNPOD_MODEL_PREFIX:-img2img_lora/2026-06-10}" \
        --target-dir "$RUNPOD_MODEL_TARGET_DIR"
fi

if [ -n "${COMFYUI_DIR:-}" ] && [ -f "${COMFYUI_DIR}/main.py" ]; then
    log "starting ComfyUI from COMFYUI_DIR"
    (
        cd "$COMFYUI_DIR"
        python3 main.py --listen 0.0.0.0 --port 8188 ${COMFY_EXTRA_ARGS:-}
    ) &
    COMFY_PID="$!"
elif [ -n "${COMFY_START_CMD:-}" ]; then
    log "starting ComfyUI from COMFY_START_CMD"
    bash -lc "$COMFY_START_CMD" &
    COMFY_PID="$!"
elif [ -f "${VOLUME_COMFYUI_DIR}/main.py" ]; then
    log "starting ComfyUI from ${VOLUME_COMFYUI_DIR}"
    (
        cd "$VOLUME_COMFYUI_DIR"
        python3 main.py --listen 0.0.0.0 --port 8188 ${COMFY_EXTRA_ARGS:-}
    ) &
    COMFY_PID="$!"
elif [ -f /workspace/ComfyUI/main.py ]; then
    log "starting ComfyUI from /workspace/ComfyUI"
    (
        cd /workspace/ComfyUI
        python3 main.py --listen 0.0.0.0 --port 8188 ${COMFY_EXTRA_ARGS:-}
    ) &
    COMFY_PID="$!"
elif [ -f /default-comfyui-bundle/ComfyUI/main.py ]; then
    log "starting ComfyUI from /default-comfyui-bundle/ComfyUI"
    (
        cd /default-comfyui-bundle/ComfyUI
        python3 main.py --listen 0.0.0.0 --port 8188 ${COMFY_EXTRA_ARGS:-}
    ) &
    COMFY_PID="$!"
else
    echo "No known ComfyUI main.py path found and COMFY_START_CMD is not set." >&2
    exit 75
fi

deadline=$(( $(date +%s) + COMFY_READY_TIMEOUT_SECONDS ))
until curl -fsS "${COMFY_API_URL%/}/system_stats" >/dev/null 2>&1; do
    if [ "$(date +%s)" -ge "$deadline" ]; then
        echo "ComfyUI did not become ready before timeout: ${COMFY_API_URL}" >&2
        exit 75
    fi
    sleep "$COMFY_READY_INTERVAL_SECONDS"
done

log "ComfyUI ready; starting remote relay"
REMOTE_WORKER_ENV_FILE="${REMOTE_WORKER_ENV_FILE:-}" python3 -m remote_relay.relay_main &
RELAY_PID="$!"

relay_deadline=$(( $(date +%s) + RELAY_READY_TIMEOUT_SECONDS ))
until curl -fsS "http://${LOCAL_RELAY_HOST}:${LOCAL_RELAY_PORT}${RELAY_READY_PATH}" >/dev/null 2>&1; do
    if [ "$(date +%s)" -ge "$relay_deadline" ]; then
        echo "Remote relay did not become ready before timeout: ${RELAY_READY_PATH}" >&2
        exit 75
    fi
    sleep 2
done

log "remote relay ready; starting comfy agent"
python3 "$REMOTE_WORKERS_DIR/comfy_agent/agent_main.py"
agent_status="$?"
if [ "${RUNPOD_KEEPALIVE_ON_BOOTSTRAP_FAILURE:-false}" = "true" ]; then
    log "comfy agent exited with status ${agent_status}; keeping container alive for SSH diagnostics"
    while true; do
        sleep 3600
    done
fi
exit "$agent_status"
