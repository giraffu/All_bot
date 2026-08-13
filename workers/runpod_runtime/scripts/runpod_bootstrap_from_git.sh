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
    local sshd_bin
    sshd_bin="$(command -v sshd 2>/dev/null || true)"
    if [ -z "$sshd_bin" ] && [ -x /usr/sbin/sshd ]; then
        sshd_bin=/usr/sbin/sshd
    fi
    if [ -z "$sshd_bin" ]; then
        if [ "${RUNPOD_INSTALL_SSHD_IF_MISSING:-true}" = "true" ] && command -v apt-get >/dev/null 2>&1; then
            log "sshd not found; installing openssh-server for direct TCP diagnostics"
            apt-get update
            DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends openssh-server
            rm -rf /var/lib/apt/lists/*
        elif [ "${RUNPOD_INSTALL_SSHD_IF_MISSING:-true}" = "true" ] && command -v zypper >/dev/null 2>&1; then
            log "sshd not found; installing openssh for direct TCP diagnostics"
            zypper --non-interactive --gpg-auto-import-keys install --no-recommends openssh
            zypper clean --all
        fi
        sshd_bin="$(command -v sshd 2>/dev/null || true)"
        if [ -z "$sshd_bin" ] && [ -x /usr/sbin/sshd ]; then
            sshd_bin=/usr/sbin/sshd
        fi
        if [ -z "$sshd_bin" ]; then
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
        "$sshd_bin"
        log "sshd started for direct TCP diagnostics"
    fi
}
start_sshd_for_diagnostics

ROOT_DIR="${ALLBOT_RUNPOD_ROOT:-/workspace/allbot}"
REPO_DIR="${ALLBOT_RUNPOD_REPO_DIR:-/opt/allbot/runtime}"
RUNPOD_WORKER_DIR="${ALLBOT_RUNPOD_WORKER_DIR:-${REPO_DIR}/workers/runpod_runtime}"
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

shutdown_children() {
    local status="${1:-0}"
    trap - INT TERM
    cleanup
    for pid in "${AGENT_PID:-}" "${RELAY_PID:-}" "${COMFY_PID:-}"; do
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
if [ -d "${RUNPOD_WORKER_DIR}/comfy_agent" ] && [ -f "${RUNPOD_WORKER_DIR}/requirements.txt" ]; then
    log "using baked AllBot RunPod worker bundle at ${RUNPOD_WORKER_DIR}"
else
    echo "baked AllBot RunPod worker bundle is missing: ${RUNPOD_WORKER_DIR}" >&2
    exit 66
fi

cd "$RUNPOD_WORKER_DIR"
export PYTHONPATH="${RUNPOD_WORKER_DIR}:${REPO_DIR}:${PYTHONPATH:-}"

verify_worker_dependencies() {
    python3 - <<'PY'
import importlib

for module_name in (
    "asgi_correlation_id",
    "boto3",
    "dotenv",
    "fastapi",
    "httpx",
    "minio",
    "PIL",
    "pydantic",
    "uvicorn",
    "websockets",
):
    importlib.import_module(module_name)
PY
}

dependency_mode="${RUNPOD_WORKER_DEPENDENCY_MODE:-auto}"
if verify_worker_dependencies; then
    log "baked Worker dependencies are ready; skipping pip install"
elif [ "$dependency_mode" = "baked" ]; then
    echo "baked Worker dependencies are incomplete; refusing runtime network install" >&2
    exit 78
elif [ "$dependency_mode" = "auto" ] || [ "$dependency_mode" = "install" ]; then
    log "installing Worker dependencies at runtime (mode=${dependency_mode})"
    python3 -m pip install -r requirements.txt
    verify_worker_dependencies
else
    echo "invalid RUNPOD_WORKER_DEPENDENCY_MODE: ${dependency_mode}" >&2
    exit 78
fi
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

if [ "${RUNPOD_PREPARE_COMFYUI_ON_VOLUME:-false}" = "true" ] \
    && [ ! -f "${VOLUME_COMFYUI_DIR}/main.py" ]; then
    seed_comfyui_dir=""
    if [ -f /default-comfyui-bundle/ComfyUI/main.py ]; then
        seed_comfyui_dir="/default-comfyui-bundle/ComfyUI"
    elif seed_comfyui_dir="$(resolve_baked_comfyui_dir)"; then
        true
    fi
    if [ -n "$seed_comfyui_dir" ]; then
        log "seeding ComfyUI bundle into ${VOLUME_COMFYUI_DIR}"
        mkdir -p "$VOLUME_COMFYUI_DIR"
        cp -a "${seed_comfyui_dir}/." "$VOLUME_COMFYUI_DIR/"
    fi
fi

resolve_comfyui_dir_for_models() {
    if [ -n "${COMFYUI_DIR:-}" ] && [ -f "${COMFYUI_DIR}/main.py" ]; then
        printf '%s\n' "$COMFYUI_DIR"
    elif [ -f "${VOLUME_COMFYUI_DIR}/main.py" ]; then
        printf '%s\n' "$VOLUME_COMFYUI_DIR"
    elif baked_comfyui_dir="$(resolve_baked_comfyui_dir)"; then
        printf '%s\n' "$baked_comfyui_dir"
    elif [ -f /workspace/ComfyUI/main.py ]; then
        printf '%s\n' "/workspace/ComfyUI"
    elif [ -f /default-comfyui-bundle/ComfyUI/main.py ]; then
        printf '%s\n' "/default-comfyui-bundle/ComfyUI"
    else
        return 1
    fi
}

install_comfyui_custom_nodes() {
    if [ "${RUNPOD_COMFY_CUSTOM_NODES_ENABLED:-true}" != "true" ]; then
        log "RunPod ComfyUI custom node install disabled"
        return
    fi

    local comfyui_dir="${RUNPOD_COMFY_CUSTOM_NODES_DIR:-}"
    if [ -z "$comfyui_dir" ]; then
        if resolved_comfy_dir="$(resolve_comfyui_dir_for_models)"; then
            comfyui_dir="$resolved_comfy_dir"
        fi
    fi
    if [ -z "$comfyui_dir" ] || [ ! -f "${comfyui_dir}/main.py" ]; then
        echo "RUNPOD_COMFY_CUSTOM_NODES_ENABLED=true but no ComfyUI directory was found." >&2
        exit 75
    fi

    if [ "${RUNPOD_COMFY_KJNODES_ENABLED:-true}" = "true" ]; then
        local repo_url="${RUNPOD_COMFY_KJNODES_REPO_URL:-https://github.com/kijai/ComfyUI-KJNodes.git}"
        local repo_ref="${RUNPOD_COMFY_KJNODES_REF:-}"
        local target_dir="${comfyui_dir%/}/custom_nodes/ComfyUI-KJNodes"
        mkdir -p "${comfyui_dir%/}/custom_nodes"
        if [ -d "${target_dir}/.git" ]; then
            log "updating ComfyUI-KJNodes in ${target_dir}"
            git -C "$target_dir" fetch --depth 1 origin "${repo_ref:-HEAD}"
            if [ -n "$repo_ref" ]; then
                git -C "$target_dir" checkout --force FETCH_HEAD
            else
                git -C "$target_dir" reset --hard FETCH_HEAD
            fi
        elif [ -d "$target_dir" ]; then
            log "ComfyUI-KJNodes already exists at ${target_dir}; leaving non-git directory unchanged"
        else
            log "installing ComfyUI-KJNodes into ${target_dir}"
            if [ -n "$repo_ref" ]; then
                git clone --depth 1 --branch "$repo_ref" "$repo_url" "$target_dir"
            else
                git clone --depth 1 "$repo_url" "$target_dir"
            fi
        fi
        if [ -f "${target_dir}/requirements.txt" ]; then
            python3 -m pip install -r "${target_dir}/requirements.txt"
        fi
    fi
}

ensure_wan22_rife_cache() {
    local comfyui_dir="${RUNPOD_RIFE_COMFYUI_DIR:-}"
    if [ -z "$comfyui_dir" ]; then
        if resolved_comfy_dir="$(resolve_comfyui_dir_for_models)"; then
            comfyui_dir="$resolved_comfy_dir"
        fi
    fi
    if [ -z "$comfyui_dir" ]; then
        python3 "$RUNPOD_WORKER_DIR/scripts/ensure_wan22_rife_cache.py"
        return
    fi
    python3 "$RUNPOD_WORKER_DIR/scripts/ensure_wan22_rife_cache.py" \
        --comfyui-dir "$comfyui_dir" \
        --model-target-dir "${RUNPOD_MODEL_TARGET_DIR:-${comfyui_dir%/}/models}"
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
    python3 "$RUNPOD_WORKER_DIR/scripts/runpod_sync_models_from_r2.py" \
        --bucket "${RUNPOD_MODEL_BUCKET:-}" \
        --prefix "${RUNPOD_MODEL_PREFIX:-img2img_lora/2026-06-10}" \
        --target-dir "$RUNPOD_MODEL_TARGET_DIR"
fi

ensure_wan22_rife_cache
install_comfyui_custom_nodes

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
elif baked_comfyui_dir="$(resolve_baked_comfyui_dir)"; then
    log "starting ComfyUI from ${baked_comfyui_dir}"
    (
        cd "$baked_comfyui_dir"
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

log "ComfyUI ready; starting RunPod relay"
RUNPOD_WORKER_ENV_FILE="${RUNPOD_WORKER_ENV_FILE:-}" python3 -m runpod_relay.relay_main &
RELAY_PID="$!"

relay_deadline=$(( $(date +%s) + RELAY_READY_TIMEOUT_SECONDS ))
until curl -fsS "http://${LOCAL_RELAY_HOST}:${LOCAL_RELAY_PORT}${RELAY_READY_PATH}" >/dev/null 2>&1; do
    if [ "$(date +%s)" -ge "$relay_deadline" ]; then
        echo "RunPod relay did not become ready before timeout: ${RELAY_READY_PATH}" >&2
        exit 75
    fi
    sleep 2
done

log "RunPod relay ready; starting comfy agent"
python3 "$RUNPOD_WORKER_DIR/comfy_agent/agent_main.py" &
AGENT_PID="$!"

log "process supervisor watching agent=${AGENT_PID} relay=${RELAY_PID} comfy=${COMFY_PID}"
set +e
wait -n "$AGENT_PID" "$RELAY_PID" "$COMFY_PID"
supervised_status="$?"
set -e

log "managed process exited with status ${supervised_status}; stopping container for restart policy"
shutdown_children "$supervised_status"
