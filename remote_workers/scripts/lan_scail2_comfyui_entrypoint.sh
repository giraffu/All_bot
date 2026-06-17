#!/usr/bin/env bash
set -euo pipefail

LOG_FILE="${SCAIL2_COMFYUI_LOG_FILE:-/tmp/allbot-scail2-comfyui.log}"
touch "$LOG_FILE"
exec > >(tee -a "$LOG_FILE") 2>&1

log() {
    printf '[scail2-comfyui] %s\n' "$*"
}

keepalive_on_failure() {
    local status="$1"
    log "startup failed with exit status ${status}"
    if [ "${RUNPOD_KEEPALIVE_ON_BOOTSTRAP_FAILURE:-true}" = "true" ]; then
        log "keeping container alive for diagnostics"
        while true; do
            sleep 3600
        done
    fi
    exit "$status"
}
trap 'keepalive_on_failure "$?"' ERR

find_comfyui_dir() {
    local candidate
    for candidate in \
        "${COMFYUI_DIR:-}" \
        "$(cat /opt/allbot-comfyui-dir 2>/dev/null || true)" \
        /opt/ComfyUI \
        /default-comfyui-bundle/ComfyUI \
        /workspace/ComfyUI \
        /root/ComfyUI; do
        if [ -n "$candidate" ] && [ -f "${candidate}/main.py" ]; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    return 1
}

link_runtime_dir() {
    local name="$1"
    local target="$2"
    mkdir -p "$target"
    if [ -L "${COMFYUI_DIR}/${name}" ]; then
        rm -f "${COMFYUI_DIR}/${name}"
    elif [ -e "${COMFYUI_DIR}/${name}" ]; then
        rm -rf "${COMFYUI_DIR:?}/${name}"
    fi
    ln -s "$target" "${COMFYUI_DIR}/${name}"
}

COMFYUI_DIR="$(find_comfyui_dir)"
WORKSPACE_DIR="${RUNPOD_WORKSPACE_DIR:-/workspace}"
VOLUME_COMFYUI_DIR="${RUNPOD_VOLUME_COMFYUI_DIR:-${WORKSPACE_DIR}/ComfyUI}"
MODEL_TARGET_DIR="${RUNPOD_MODEL_TARGET_DIR:-${VOLUME_COMFYUI_DIR}/models}"
WORKFLOW_SOURCE_DIR="${SCAIL2_WORKFLOW_SOURCE_DIR:-/opt/allbot/scail2-workflows}"
WORKFLOW_OVERRIDE_DIR="${SCAIL2_WORKFLOW_OVERRIDE_DIR:-${WORKSPACE_DIR}/scail2-workflows}"

log "using ComfyUI at ${COMFYUI_DIR}"
mkdir -p \
    "$MODEL_TARGET_DIR" \
    "${VOLUME_COMFYUI_DIR}/input" \
    "${VOLUME_COMFYUI_DIR}/output" \
    "${VOLUME_COMFYUI_DIR}/temp" \
    "${VOLUME_COMFYUI_DIR}/user/default/workflows"

link_runtime_dir models "$MODEL_TARGET_DIR"
link_runtime_dir input "${VOLUME_COMFYUI_DIR}/input"
link_runtime_dir output "${VOLUME_COMFYUI_DIR}/output"
link_runtime_dir temp "${VOLUME_COMFYUI_DIR}/temp"
link_runtime_dir user "${VOLUME_COMFYUI_DIR}/user"

if [ "${RUNPOD_MODEL_SYNC_ENABLED:-true}" = "true" ]; then
    log "syncing SCAIL-2 model bundle into ${MODEL_TARGET_DIR}"
    python3 /opt/allbot/remote_workers/scripts/runpod_sync_models_from_r2.py \
        --bucket "${RUNPOD_MODEL_BUCKET:-}" \
        --prefix "${RUNPOD_MODEL_PREFIX:-scail2/2026-06-17-test}" \
        --target-dir "$MODEL_TARGET_DIR"
fi

if compgen -G "${WORKFLOW_SOURCE_DIR}/SCAIL-2_*.json" >/dev/null; then
    cp -f "${WORKFLOW_SOURCE_DIR}"/SCAIL-2_*.json \
        "${VOLUME_COMFYUI_DIR}/user/default/workflows/"
fi
if compgen -G "${WORKFLOW_OVERRIDE_DIR}/SCAIL-2_*.json" >/dev/null; then
    cp -f "${WORKFLOW_OVERRIDE_DIR}"/SCAIL-2_*.json \
        "${VOLUME_COMFYUI_DIR}/user/default/workflows/"
fi
log "SCAIL-2 workflows available in ${VOLUME_COMFYUI_DIR}/user/default/workflows"

cd "$COMFYUI_DIR"
COMFY_ARGS=(
    --listen "${COMFY_HOST:-0.0.0.0}"
    --port "${COMFY_PORT:-8188}"
)
if [ -n "${COMFY_EXTRA_ARGS:-}" ]; then
    # shellcheck disable=SC2206
    EXTRA_ARGS=(${COMFY_EXTRA_ARGS})
    COMFY_ARGS+=("${EXTRA_ARGS[@]}")
fi

log "starting ComfyUI on ${COMFY_HOST:-0.0.0.0}:${COMFY_PORT:-8188}"
exec python3 main.py "${COMFY_ARGS[@]}"
