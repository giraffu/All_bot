#!/usr/bin/env bash
set -euo pipefail

log() {
    printf '[runpod-volume-seed] %s\n' "$*"
}

WORKSPACE_DIR="${RUNPOD_WORKSPACE_DIR:-/workspace}"
ROOT_DIR="${ALLBOT_RUNPOD_ROOT:-${WORKSPACE_DIR}/allbot}"
REPO_URL="${ALLBOT_RUNPOD_GIT_URL:-https://github.com/giraffu/All_bot.git}"
REPO_BRANCH="${ALLBOT_RUNPOD_GIT_BRANCH:-deploy}"
REPO_DIR="${ALLBOT_RUNPOD_REPO_DIR:-${ROOT_DIR}/repo}"
REMOTE_WORKERS_DIR="${ALLBOT_RUNPOD_REMOTE_WORKERS_DIR:-${REPO_DIR}/remote_workers}"
COMFYUI_DIR="${RUNPOD_VOLUME_COMFYUI_DIR:-${WORKSPACE_DIR}/ComfyUI}"
PIP_CACHE_DIR="${PIP_CACHE_DIR:-${WORKSPACE_DIR}/.cache/pip}"

export PIP_CACHE_DIR

mkdir -p "$WORKSPACE_DIR" "$ROOT_DIR" "$PIP_CACHE_DIR"

if [ ! -f "${COMFYUI_DIR}/main.py" ] && [ -f /default-comfyui-bundle/ComfyUI/main.py ]; then
    log "seeding ComfyUI bundle into ${COMFYUI_DIR}"
    mkdir -p "$COMFYUI_DIR"
    cp -a /default-comfyui-bundle/ComfyUI/. "$COMFYUI_DIR/"
else
    log "ComfyUI bundle already present or base bundle unavailable"
fi

if [ -d "${REPO_DIR}/.git" ]; then
    log "updating AllBot remote worker bundle at ${REPO_DIR}"
    git -C "$REPO_DIR" fetch --depth 1 origin "$REPO_BRANCH"
    git -C "$REPO_DIR" checkout "$REPO_BRANCH"
    git -C "$REPO_DIR" reset --hard "origin/${REPO_BRANCH}"
else
    log "cloning AllBot remote worker bundle into ${REPO_DIR}"
    rm -rf "$REPO_DIR"
    git clone --depth 1 --branch "$REPO_BRANCH" "$REPO_URL" "$REPO_DIR"
fi

if [ -f "${REMOTE_WORKERS_DIR}/requirements.txt" ]; then
    log "warming remote worker python dependencies"
    cd "$REMOTE_WORKERS_DIR"
    python3 -m pip install -r requirements.txt
fi

mkdir -p \
    "${COMFYUI_DIR}/models/checkpoints" \
    "${COMFYUI_DIR}/models/loras/qwen" \
    "${COMFYUI_DIR}/models/controlnet" \
    "${COMFYUI_DIR}/models/vae" \
    "${COMFYUI_DIR}/input" \
    "${COMFYUI_DIR}/output" \
    "${COMFYUI_DIR}/temp" \
    "${WORKSPACE_DIR}/runtime"

log "volume seed complete"
du -sh "$WORKSPACE_DIR" "$COMFYUI_DIR" "$ROOT_DIR" 2>/dev/null || true
