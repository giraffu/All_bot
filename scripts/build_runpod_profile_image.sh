#!/usr/bin/env bash
set -euo pipefail

PROFILE="img2img_lora"
IMAGE_REF="${RUNPOD_PROFILE_IMAGE_REF:-}"
BASE_IMAGE="${RUNPOD_PROFILE_BASE_IMAGE:-}"
COMFYUI_REF="${RUNPOD_PROFILE_COMFYUI_REF:-}"
KJNODES_REF="${RUNPOD_PROFILE_KJNODES_REF:-7967a946c296a74901606e6a8d1195aa2b6f9215}"
KJNODES_SOURCE="${RUNPOD_PROFILE_KJNODES_SOURCE:-}"
REUSE_BASE_CUSTOM_NODES="${RUNPOD_PROFILE_REUSE_BASE_CUSTOM_NODES:-false}"
PUSH="false"
SMOKE="true"

default_base_image_for_profile() {
    case "$1" in
        i2i_pro)
            printf '%s\n' "yanwk/comfyui-boot:cu128-slim"
            ;;
        *)
            printf '%s\n' "yanwk/comfyui-boot:cu128-slim"
            ;;
    esac
}

default_comfyui_ref_for_profile() {
    case "$1" in
        i2i_pro)
            printf '%s\n' "16cd8d8a8f5f16ce7e5f929fdba9f783990254ea"
            ;;
        *)
            printf '%s\n' "master"
            ;;
    esac
}

usage() {
    cat <<'USAGE'
Usage:
  scripts/build_runpod_profile_image.sh [options]

Options:
  --profile <name>       Profile to build: img2img_lora, wan22_aio_video, or i2i_pro.
  --image-ref <ref>      Target image ref. Defaults to a local allbot/comfy-runpod-* tag.
  --base-image <ref>     Base image. Defaults per profile; i2i_pro uses yanwk/comfyui-boot:cu128-slim.
  --comfyui-ref <ref>    ComfyUI git ref used when the base image does not include ComfyUI.
  --kjnodes-ref <sha>    ComfyUI-KJNodes git ref pinned into the image.
  --kjnodes-source <dir> Build from an existing local ComfyUI-KJNodes directory instead of GitHub.
  --reuse-base-custom-nodes
                         Reuse custom nodes already baked into the base image and only apply final Wan22 fix layers.
  --no-smoke             Skip local smoke test after build.
  --push                 Push image after a successful build and smoke test.
  -h, --help             Show this help.

Model files are intentionally not baked into this image. RunPod Pods should keep
RUNPOD_MODEL_SYNC_ENABLED=true and sync models from the R2 manifest at startup.
USAGE
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --profile)
            PROFILE="${2:?missing value for --profile}"
            shift 2
            ;;
        --image-ref)
            IMAGE_REF="${2:?missing value for --image-ref}"
            shift 2
            ;;
        --base-image)
            BASE_IMAGE="${2:?missing value for --base-image}"
            shift 2
            ;;
        --comfyui-ref)
            COMFYUI_REF="${2:?missing value for --comfyui-ref}"
            shift 2
            ;;
        --kjnodes-ref)
            KJNODES_REF="${2:?missing value for --kjnodes-ref}"
            shift 2
            ;;
        --kjnodes-source)
            KJNODES_SOURCE="${2:?missing value for --kjnodes-source}"
            shift 2
            ;;
        --reuse-base-custom-nodes)
            REUSE_BASE_CUSTOM_NODES="true"
            shift
            ;;
        --no-smoke)
            SMOKE="false"
            shift
            ;;
        --push)
            PUSH="true"
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

case "$PROFILE" in
    img2img_lora)
        IMAGE_REF="${IMAGE_REF:-allbot/comfy-runpod-img2img-lora:local}"
        ;;
    wan22_aio_video)
        IMAGE_REF="${IMAGE_REF:-allbot/comfy-runpod-wan22-aio-video:local}"
        ;;
    i2i_pro)
        IMAGE_REF="${IMAGE_REF:-allbot/comfy-runpod-i2i-pro:local}"
        ;;
    *)
        echo "Unsupported RunPod profile: ${PROFILE}" >&2
        exit 2
        ;;
esac

if [ -z "$BASE_IMAGE" ]; then
    BASE_IMAGE="$(default_base_image_for_profile "$PROFILE")"
fi
if [ -z "$COMFYUI_REF" ]; then
    COMFYUI_REF="$(default_comfyui_ref_for_profile "$PROFILE")"
fi

dockerfile="remote_workers/docker/runpod_profiles/${PROFILE}/Dockerfile"
if [ ! -f "$dockerfile" ]; then
    echo "Dockerfile not found: ${dockerfile}" >&2
    exit 2
fi
context_dir="$(dirname "$dockerfile")"
dockerfile_for_build="$dockerfile"
context_for_build="$context_dir"
cleanup_dir=""
if [ -n "$KJNODES_SOURCE" ]; then
    if [ ! -d "$KJNODES_SOURCE" ]; then
        echo "KJNodes source directory not found: ${KJNODES_SOURCE}" >&2
        exit 2
    fi
    local_dockerfile="${context_dir}/Dockerfile.local-kjnodes"
    if [ ! -f "$local_dockerfile" ]; then
        echo "Local KJNodes Dockerfile not found: ${local_dockerfile}" >&2
        exit 2
    fi
    cleanup_dir="$(mktemp -d)"
    trap 'rm -rf "$cleanup_dir"' EXIT
    cp "$local_dockerfile" "${cleanup_dir}/Dockerfile"
    cp -a "$KJNODES_SOURCE" "${cleanup_dir}/ComfyUI-KJNodes"
    dockerfile_for_build="${cleanup_dir}/Dockerfile"
    context_for_build="$cleanup_dir"
elif [ "$PROFILE" = "i2i_pro" ] || [ "$PROFILE" = "img2img_lora" ]; then
    cleanup_dir="$(mktemp -d)"
    trap 'rm -rf "$cleanup_dir"' EXIT
    mkdir -p \
        "${cleanup_dir}/remote_workers/docker/runpod_profiles/${PROFILE}" \
        "${cleanup_dir}/remote_workers/scripts"
    cp "$dockerfile" \
        "${cleanup_dir}/remote_workers/docker/runpod_profiles/${PROFILE}/Dockerfile"
    cp "remote_workers/scripts/runpod_bootstrap_from_git.sh" \
        "${cleanup_dir}/remote_workers/scripts/runpod_bootstrap_from_git.sh"
    dockerfile_for_build="${cleanup_dir}/remote_workers/docker/runpod_profiles/${PROFILE}/Dockerfile"
    context_for_build="$cleanup_dir"
fi

echo "Building ${IMAGE_REF}"
docker build \
    -f "$dockerfile_for_build" \
    --build-arg "BASE_IMAGE=${BASE_IMAGE}" \
    --build-arg "COMFYUI_REF=${COMFYUI_REF}" \
    --build-arg "KJNODES_REF=${KJNODES_REF}" \
    --build-arg "REUSE_BASE_CUSTOM_NODES=${REUSE_BASE_CUSTOM_NODES}" \
    --label "allbot.runpod.profile=${PROFILE}" \
    --label "allbot.runpod.model_sync=external-r2-manifest" \
    -t "$IMAGE_REF" \
    "$context_for_build"

if [ "$SMOKE" = "true" ]; then
    echo "Smoke testing ${IMAGE_REF}"
    if [ "$PROFILE" = "img2img_lora" ]; then
        docker run --rm --entrypoint bash "$IMAGE_REF" -lc '
set -euo pipefail
if [ -f /opt/allbot-comfyui-dir ]; then
  comfyui_dir="$(cat /opt/allbot-comfyui-dir)"
elif [ -f /default-comfyui-bundle/ComfyUI/main.py ]; then
  comfyui_dir=/default-comfyui-bundle/ComfyUI
elif [ -f /workspace/ComfyUI/main.py ]; then
  comfyui_dir=/workspace/ComfyUI
elif [ -f /root/ComfyUI/main.py ]; then
  comfyui_dir=/root/ComfyUI
else
  echo "ComfyUI main.py not found" >&2
  exit 75
fi
test -f "${comfyui_dir}/main.py"
test -d "${comfyui_dir}/custom_nodes/ComfyUI-KJNodes"
test -f "${comfyui_dir}/custom_nodes/ComfyUI-KJNodes/requirements.txt"
test -x /opt/allbot/runpod_bootstrap_from_git.sh
if find "${comfyui_dir}/models" -type f \( -name "Qwen-Rapid-AIO-NSFW-v23.safetensors" -o -path "*/loras/qwen/*.safetensors" \) -print -quit | grep -q .; then
  echo "Business model files must stay out of the profile image" >&2
  exit 1
fi
echo "COMFYUI_DIR=${comfyui_dir}"
echo "KJNODES_PRESENT=true"
'
    elif [ "$PROFILE" = "wan22_aio_video" ]; then
        docker run --rm --entrypoint bash "$IMAGE_REF" -lc '
set -euo pipefail
if [ -f /opt/allbot-comfyui-dir ]; then
  comfyui_dir="$(cat /opt/allbot-comfyui-dir)"
elif [ -f /default-comfyui-bundle/ComfyUI/main.py ]; then
  comfyui_dir=/default-comfyui-bundle/ComfyUI
elif [ -f /workspace/ComfyUI/main.py ]; then
  comfyui_dir=/workspace/ComfyUI
elif [ -f /root/ComfyUI/main.py ]; then
  comfyui_dir=/root/ComfyUI
else
  echo "ComfyUI main.py not found" >&2
  exit 75
fi
test -f "${comfyui_dir}/main.py"
test -d "${comfyui_dir}/custom_nodes/ComfyUI-KJNodes"
test -d "${comfyui_dir}/custom_nodes/ComfyUI-VideoHelperSuite"
test -d "${comfyui_dir}/custom_nodes/rgthree-comfy"
test -d "${comfyui_dir}/custom_nodes/ComfyUI-Frame-Interpolation"
test -d "${comfyui_dir}/custom_nodes/ComfyUI_Fill-Nodes"
test -d "${comfyui_dir}/custom_nodes/ComfyUI-LTXVideo"
LTXVIDEO_NODE_DIR="${comfyui_dir}/custom_nodes/ComfyUI-LTXVideo" PYTHONPATH="${comfyui_dir}:${PYTHONPATH:-}" python3 -c '"'"'import importlib.util, os, sys; from pathlib import Path; node_dir = Path(os.environ["LTXVIDEO_NODE_DIR"]); spec = importlib.util.spec_from_file_location("allbot_ltxvideo_smoke", node_dir / "__init__.py", submodule_search_locations=[str(node_dir)]); module = importlib.util.module_from_spec(spec); assert spec.loader is not None; sys.modules[spec.name] = module; spec.loader.exec_module(module); assert "LTXVSpatioTemporalTiledVAEDecode" in module.NODE_CLASS_MAPPINGS'"'"'
test -d "${comfyui_dir}/custom_nodes/ComfyUI-GGUF"
test -d "${comfyui_dir}/custom_nodes/ComfyUI-DaSiWa-Nodes"
test -d "${comfyui_dir}/custom_nodes/comfyui-WhiteRabbit"
command -v ffmpeg >/dev/null
command -v ffprobe >/dev/null
if find "${comfyui_dir}/models" -type f \( \
  -name "wan22EnhancedNSFWSVICamera_nsfwFASTMOVEV2FP8H.safetensors" -o \
  -name "wan22EnhancedNSFWSVICamera_nsfwFASTMOVEV2FP8L.safetensors" -o \
  -name "DasiwaWAN22I2V14BLightspeed_snatchkissHighV11.safetensors" -o \
  -name "DasiwaWAN22I2V14BLightspeed_snatchkissLowV11.safetensors" -o \
  -path "*/loras/*_high_noise.safetensors" -o \
  -path "*/loras/*_low_noise.safetensors" \
  \) -print -quit | grep -q .; then
  echo "Business model files must stay out of the profile image" >&2
  exit 1
fi
echo "COMFYUI_DIR=${comfyui_dir}"
echo "WAN22_CUSTOM_NODES_PRESENT=true"
'
    else
        docker run --rm --entrypoint bash "$IMAGE_REF" -lc '
set -euo pipefail
if [ -f /opt/allbot-comfyui-dir ]; then
  comfyui_dir="$(cat /opt/allbot-comfyui-dir)"
elif [ -f /opt/ComfyUI/main.py ]; then
  comfyui_dir=/opt/ComfyUI
elif [ -f /default-comfyui-bundle/ComfyUI/main.py ]; then
  comfyui_dir=/default-comfyui-bundle/ComfyUI
elif [ -f /workspace/ComfyUI/main.py ]; then
  comfyui_dir=/workspace/ComfyUI
elif [ -f /root/ComfyUI/main.py ]; then
  comfyui_dir=/root/ComfyUI
else
  echo "ComfyUI main.py not found" >&2
  exit 75
fi
test -f "${comfyui_dir}/main.py"
command -v ffmpeg >/dev/null
command -v curl >/dev/null
command -v git >/dev/null
command -v ssh-keygen >/dev/null
if ! command -v sshd >/dev/null && [ ! -x /usr/sbin/sshd ]; then
  echo "sshd must be available for RunPod direct TCP diagnostics" >&2
  exit 1
fi
COMFYUI_DIR="${comfyui_dir}" python3 -c '"'"'from pathlib import Path; import os, sys; root=Path(os.environ["COMFYUI_DIR"]); checks={root/"nodes.py":("UNETLoader","CLIPLoader","VAELoader"),root/"comfy_extras"/"nodes_custom_sampler.py":("SamplerCustomAdvanced",),root/"comfy_extras"/"nodes_edit_model.py":("ReferenceLatent",),root/"comfy_extras"/"nodes_flux.py":("EmptyFlux2LatentImage","Flux2Scheduler")}; missing=[]; [missing.append(f"{path}:{name}") for path,names in checks.items() for name in names if name not in path.read_text(encoding="utf-8")]; sys.exit("missing ComfyUI i2i_pro node sources: "+",".join(missing)) if missing else None'"'"'
if find "${comfyui_dir}/models" -type f \( \
  -name "qwen_3_8b_fp8mixed.safetensors" -o \
  -name "flux2-vae.safetensors" -o \
  -name "DarkBeast-Klein9b-V2-BFS-FP8-ComfyUI.safetensors" -o \
  -name "qwen_3_4b.safetensors" -o \
  -name "ae.safetensors" -o \
  -name "DarkBeastZ6-BlitZ-BF16-ComfyUI.safetensors" \
  \) -print -quit | grep -q .; then
  echo "Business model files must stay out of the profile image" >&2
  exit 1
fi
echo "COMFYUI_DIR=${comfyui_dir}"
echo "I2I_PRO_CORE_NODES_PRESENT=true"
'
    fi
fi

if [ "$PUSH" = "true" ]; then
    echo "Pushing ${IMAGE_REF}"
    docker push "$IMAGE_REF"
fi
