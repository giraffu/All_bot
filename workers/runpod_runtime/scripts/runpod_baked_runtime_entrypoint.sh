#!/usr/bin/env bash
set -euo pipefail

runtime_root="${ALLBOT_RUNPOD_REPO_DIR:-/opt/allbot/runtime}"
worker_root="${ALLBOT_RUNPOD_WORKER_DIR:-${runtime_root}/runpod_worker}"

test -f "${worker_root}/comfy_agent/agent_main.py"
test -d "${worker_root}/comfy_agent/workflows"
test -f "${worker_root}/requirements.txt"

prepare_baked_model_target() {
    local model_target="${RUNPOD_MODEL_TARGET_DIR:-}"
    if [ -z "$model_target" ] || [ ! -f /opt/allbot-comfyui-dir ]; then
        return 0
    fi

    local baked_dir baked_models
    baked_dir="$(cat /opt/allbot-comfyui-dir)"
    if [ -z "$baked_dir" ] || [ ! -f "${baked_dir}/main.py" ]; then
        return 0
    fi
    baked_models="${baked_dir%/}/models"
    if [ "$model_target" = "$baked_models" ]; then
        return 0
    fi

    mkdir -p "$model_target"
    if [ -L "$baked_models" ]; then
        rm -f "$baked_models"
    elif [ -d "$baked_models" ]; then
        if find "$baked_models" -type f \( \
            -name "*.safetensors" -o -name "*.ckpt" -o -name "*.pt" -o \
            -name "*.pth" -o -name "*.bin" -o -name "*.onnx" \
        \) -print -quit | grep -q .; then
            echo "baked ComfyUI models directory contains weights; refusing to replace it" >&2
            exit 78
        fi
        rm -rf "$baked_models"
    elif [ -e "$baked_models" ]; then
        echo "baked ComfyUI models path is not a directory or symlink" >&2
        exit 78
    fi
    ln -s "$model_target" "$baked_models"
}

prepare_baked_model_target

export ALLBOT_RUNPOD_REPO_DIR="$runtime_root"
export ALLBOT_RUNPOD_WORKER_DIR="$worker_root"
exec bash /opt/allbot/runpod_bootstrap_from_git.sh
