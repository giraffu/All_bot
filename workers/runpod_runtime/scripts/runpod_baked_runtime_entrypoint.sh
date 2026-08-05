#!/usr/bin/env bash
set -euo pipefail

runtime_root="${ALLBOT_RUNPOD_REPO_DIR:-/opt/allbot/runtime}"
worker_root="${ALLBOT_RUNPOD_WORKER_DIR:-${runtime_root}/runpod_worker}"

test -f "${worker_root}/comfy_agent/agent_main.py"
test -d "${worker_root}/comfy_agent/workflows"
test -f "${worker_root}/requirements.txt"

prepare_baked_model_target() {
    local model_target="${RUNPOD_MODEL_TARGET_DIR:-}"
    local comfyui_dir_file="${RUNPOD_BAKED_COMFYUI_DIR_FILE:-/opt/allbot-comfyui-dir}"
    if [ -z "$model_target" ] || [ ! -f "$comfyui_dir_file" ]; then
        return 0
    fi

    local baked_dir baked_models unexpected_weight preview_dir preview_file
    baked_dir="$(cat "$comfyui_dir_file")"
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
        unexpected_weight="$({
            find "$baked_models" -type f \( \
                -name "*.safetensors" -o -name "*.ckpt" -o -name "*.pt" -o \
                -name "*.pth" -o -name "*.bin" -o -name "*.onnx" \
            \) -print
        } | while IFS= read -r preview_file; do
            case "${preview_file#"$baked_models"/}" in
                vae_approx/tae*_encoder.pth|vae_approx/tae*_decoder.pth) ;;
                *) printf '%s\n' "$preview_file"; break ;;
            esac
        done)"
        if [ -n "$unexpected_weight" ]; then
            echo "baked ComfyUI models directory contains weights; refusing to replace it" >&2
            exit 78
        fi
        preview_dir="$baked_models/vae_approx"
        if [ -d "$preview_dir" ]; then
            mkdir -p "$model_target/vae_approx"
            find "$preview_dir" -maxdepth 1 -type f \( \
                -name "tae*_encoder.pth" -o -name "tae*_decoder.pth" \
            \) -exec cp -pn {} "$model_target/vae_approx/" \;
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
exec bash "${RUNPOD_BOOTSTRAP_SCRIPT:-/opt/allbot/runpod_bootstrap_from_git.sh}"
