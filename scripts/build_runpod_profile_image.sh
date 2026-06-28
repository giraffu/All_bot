#!/usr/bin/env bash
set -euo pipefail

PROFILE="img2img_lora"
IMAGE_REF="${RUNPOD_PROFILE_IMAGE_REF:-}"
BASE_IMAGE="${RUNPOD_PROFILE_BASE_IMAGE:-}"
COMFYUI_REF="${RUNPOD_PROFILE_COMFYUI_REF:-}"
KJNODES_REF="${RUNPOD_PROFILE_KJNODES_REF:-7967a946c296a74901606e6a8d1195aa2b6f9215}"
KJNODES_SOURCE="${RUNPOD_PROFILE_KJNODES_SOURCE:-}"
NODE_SOURCE_IMAGE="${RUNPOD_PROFILE_NODE_SOURCE_IMAGE:-}"
REUSE_BASE_CUSTOM_NODES="${RUNPOD_PROFILE_REUSE_BASE_CUSTOM_NODES:-false}"
DOCKER_BUILD_NETWORK="${RUNPOD_PROFILE_DOCKER_BUILD_NETWORK:-}"
PUSH="false"
SMOKE="true"

default_base_image_for_profile() {
    case "$1" in
        i2i_pro)
            printf '%s\n' "yanwk/comfyui-boot:cu128-slim"
            ;;
        pornmaster_flux2_edit)
            printf '%s\n' "192.168.1.115:5000/allbot/comfy-runpod-i2i-pro:20260614-i2ipro-b75c6a9-cu128-min5-ssh"
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
        scail2)
            printf '%s\n' "f026b01ba576d98442839861a0eb0046bc2250d3"
            ;;
        ltx_video)
            printf '%s\n' "f026b01ba576d98442839861a0eb0046bc2250d3"
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
  --profile <name>       Profile to build: img2img_lora, wan22_aio_video, i2i_pro, scail2, ltx_video, or pornmaster_flux2_edit.
  --image-ref <ref>      Target image ref. Defaults to a local allbot/comfy-runpod-* tag.
  --base-image <ref>     Base image. Defaults per profile; i2i_pro uses yanwk/comfyui-boot:cu128-slim.
  --comfyui-ref <ref>    ComfyUI git ref used when the base image does not include ComfyUI.
  --kjnodes-ref <sha>    ComfyUI-KJNodes git ref pinned into the image.
  --kjnodes-source <dir> Build from an existing local ComfyUI-KJNodes directory instead of GitHub.
  --node-source-image <ref>
                         Source image for profile Dockerfiles that copy baked custom nodes.
  --reuse-base-custom-nodes
                         Reuse custom nodes already baked into the base image and only apply final Wan22 fix layers.
  --build-network <mode> Docker build network mode, for example host when using a local proxy.
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
        --node-source-image)
            NODE_SOURCE_IMAGE="${2:?missing value for --node-source-image}"
            shift 2
            ;;
        --reuse-base-custom-nodes)
            REUSE_BASE_CUSTOM_NODES="true"
            shift
            ;;
        --build-network)
            DOCKER_BUILD_NETWORK="${2:?missing value for --build-network}"
            shift 2
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
    pornmaster_flux2_edit)
        IMAGE_REF="${IMAGE_REF:-allbot/comfy-runpod-pornmaster-flux2-edit:local}"
        ;;
    scail2)
        IMAGE_REF="${IMAGE_REF:-allbot/comfy-runpod-scail2:local}"
        ;;
    ltx_video)
        IMAGE_REF="${IMAGE_REF:-allbot/comfy-runpod-ltx-video:local}"
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
elif [ "$PROFILE" = "scail2" ] || [ "$PROFILE" = "ltx_video" ]; then
    context_for_build="."
elif [ "$PROFILE" = "pornmaster_flux2_edit" ]; then
    context_for_build="$context_dir"
elif [ "$PROFILE" = "wan22_aio_video" ] || [ "$PROFILE" = "i2i_pro" ] || [ "$PROFILE" = "img2img_lora" ]; then
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
docker_build_args=()
if [ -n "$DOCKER_BUILD_NETWORK" ]; then
    docker_build_args+=(--network "$DOCKER_BUILD_NETWORK")
fi
if [ -n "$NODE_SOURCE_IMAGE" ]; then
    docker_build_args+=(--build-arg "NODE_SOURCE_IMAGE=${NODE_SOURCE_IMAGE}")
fi
for proxy_env in \
    HTTP_PROXY HTTPS_PROXY ALL_PROXY NO_PROXY \
    http_proxy https_proxy all_proxy no_proxy; do
    if [ -n "${!proxy_env:-}" ]; then
        docker_build_args+=(--build-arg "${proxy_env}=${!proxy_env}")
    fi
done
docker build \
    "${docker_build_args[@]}" \
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
test -s "${comfyui_dir}/custom_nodes/ComfyUI_Fill-Nodes/nodes/cache/rife_models/rife49.pth"
test -s "${comfyui_dir}/custom_nodes/ComfyUI-Frame-Interpolation/ckpts/rife/rife49.pth"
test -x /opt/allbot/runpod_bootstrap_from_git.sh
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
    elif [ "$PROFILE" = "ltx_video" ]; then
        docker run --rm --entrypoint bash "$IMAGE_REF" -lc '
set -euo pipefail
comfyui_dir="$(cat /opt/allbot-comfyui-dir)"
test -f "${comfyui_dir}/main.py"
test -d "${comfyui_dir}/custom_nodes/ComfyUI-KJNodes"
test -d "${comfyui_dir}/custom_nodes/ComfyUI-VideoHelperSuite"
test -d "${comfyui_dir}/custom_nodes/rgthree-comfy"
test -d "${comfyui_dir}/custom_nodes/ComfyUI-LTXVideo"
test -d "${comfyui_dir}/custom_nodes/allbot_ltx_min_nodes"
test -x /opt/allbot/runpod_bootstrap_from_git.sh
python3 -c '"'"'import fastapi, minio, uvicorn, websockets'"'"'
python3 -c '"'"'from sageattention import sageattn; assert callable(sageattn)'"'"'
COMFYUI_DIR="${comfyui_dir}" LTXVIDEO_NODE_DIR="${comfyui_dir}/custom_nodes/ComfyUI-LTXVideo" PYTHONPATH="${comfyui_dir}:${PYTHONPATH:-}" python3 -c '"'"'import importlib.util, os, sys; from pathlib import Path; root = Path(os.environ["COMFYUI_DIR"]); node_dir = Path(os.environ["LTXVIDEO_NODE_DIR"]); spec = importlib.util.spec_from_file_location("allbot_ltxvideo_smoke", node_dir / "__init__.py", submodule_search_locations=[str(node_dir)]); module = importlib.util.module_from_spec(spec); assert spec.loader is not None; sys.modules[spec.name] = module; spec.loader.exec_module(module); assert "LTXVSpatioTemporalTiledVAEDecode" in module.NODE_CLASS_MAPPINGS; core_text = (root / "comfy_extras" / "nodes_lt.py").read_text(encoding="utf-8"); assert "LTXVScheduler" in core_text and "LTXVConditioning" in core_text; kj_text = (root / "custom_nodes" / "ComfyUI-KJNodes" / "__init__.py").read_text(encoding="utf-8"); assert "LTXVImgToVideoInplaceKJ" in kj_text'"'"'
LTX_MIN_NODE_DIR="${comfyui_dir}/custom_nodes/allbot_ltx_min_nodes" python3 -c '"'"'import importlib.util, os; from pathlib import Path; spec = importlib.util.spec_from_file_location("allbot_ltx_min_nodes_smoke", Path(os.environ["LTX_MIN_NODE_DIR"]) / "__init__.py"); module = importlib.util.module_from_spec(spec); assert spec.loader is not None; spec.loader.exec_module(module); expected = {"ImpactDummyInput", "TwoWaySwitch", "easy int", "mxSlider", "RAMCleanup", "VRAMCleanup", "Float", "IntToFloat", "Sigmas Sigmoid", "MathExpression|pysssss"}; assert expected <= set(module.NODE_CLASS_MAPPINGS)'"'"'
command -v ffmpeg >/dev/null
command -v ffprobe >/dev/null
if find "${comfyui_dir}/models" -type f -name "*.safetensors" -print -quit | grep -q .; then
  echo "LTX model files must stay out of the profile image" >&2
  exit 1
fi
echo "COMFYUI_DIR=${comfyui_dir}"
echo "LTX_MINIMAL_CUSTOM_NODES_PRESENT=true"
'
    elif [ "$PROFILE" = "scail2" ]; then
        docker run --rm --entrypoint bash "$IMAGE_REF" -lc '
set -euo pipefail
comfyui_dir="$(cat /opt/allbot-comfyui-dir)"
test -f "${comfyui_dir}/main.py"
test -f "${comfyui_dir}/comfy_extras/nodes_scail.py"
grep -R "WanSCAILToVideo" "${comfyui_dir}/comfy_extras/nodes_scail.py" >/dev/null
grep -R "SCAIL2ColoredMask" "${comfyui_dir}/comfy_extras/nodes_scail.py" >/dev/null
test -d "${comfyui_dir}/custom_nodes/ComfyUI-KJNodes"
test -d "${comfyui_dir}/custom_nodes/ComfyUI-VideoHelperSuite"
test -d "${comfyui_dir}/custom_nodes/rgthree-comfy"
test -d "${comfyui_dir}/custom_nodes/ComfyUI-Frame-Interpolation"
test -d "${comfyui_dir}/custom_nodes/ComfyUI_Fill-Nodes"
test -x /opt/allbot/runpod_bootstrap_from_git.sh
test -x /opt/allbot/lan_scail2_comfyui_entrypoint.sh
test -f /opt/allbot/scail2-workflows/SCAIL-2_Animation.json
python3 -c '"'"'import fastapi, minio, uvicorn, websockets'"'"'
command -v ffmpeg >/dev/null
command -v ssh-keygen >/dev/null
if ! command -v sshd >/dev/null && [ ! -x /usr/sbin/sshd ]; then
  echo "sshd must be available for RunPod direct TCP diagnostics" >&2
  exit 1
fi
if find "${comfyui_dir}/models" -type f -name "*.safetensors" -print -quit | grep -q .; then
  echo "SCAIL-2 model files must stay out of the profile image" >&2
  exit 1
fi
echo "SCAIL2_CORE_AND_CUSTOM_NODES_PRESENT=true"
'
    elif [ "$PROFILE" = "pornmaster_flux2_edit" ]; then
        docker run --rm --entrypoint bash "$IMAGE_REF" -lc '
set -euo pipefail
comfyui_dir="$(cat /opt/allbot-comfyui-dir)"
test -f "${comfyui_dir}/main.py"
command -v ffmpeg >/dev/null
command -v curl >/dev/null
command -v git >/dev/null
command -v ssh-keygen >/dev/null
if ! command -v sshd >/dev/null && [ ! -x /usr/sbin/sshd ]; then
  echo "sshd must be available for RunPod direct TCP diagnostics" >&2
  exit 1
fi
COMFYUI_DIR="${comfyui_dir}" python3 -c '"'"'from pathlib import Path; import os, sys; root=Path(os.environ["COMFYUI_DIR"]); checks={root/"nodes.py":("UNETLoader","CLIPLoader","VAELoader"),root/"comfy_extras"/"nodes_custom_sampler.py":("SamplerCustomAdvanced",),root/"comfy_extras"/"nodes_edit_model.py":("ReferenceLatent",),root/"comfy_extras"/"nodes_flux.py":("EmptyFlux2LatentImage","Flux2Scheduler")}; missing=[]; [missing.append(f"{path}:{name}") for path,names in checks.items() for name in names if name not in path.read_text(encoding="utf-8")]; sys.exit("missing PornMaster Flux2 edit node sources: "+",".join(missing)) if missing else None'"'"'
COMFYUI_DIR="${comfyui_dir}" python3 -c '"'"'from pathlib import Path; import os; root=Path(os.environ["COMFYUI_DIR"]); auto=(root/"comfy/ldm/models/autoencoder.py").read_text(encoding="utf-8"); sd=(root/"comfy/sd.py").read_text(encoding="utf-8"); assert "decoder_ddconfig = kwargs.pop" in auto; assert "decoder_ch = sd[" in sd'"'"'
if find "${comfyui_dir}/models" -type f \( \
  -name "PornMaster_flux2_klein_9b_turbo_fp8_V4.safetensors" -o \
  -name "pornmasterFlux2Klein_v4TurboFp8.safetensors" -o \
  -name "qwen_3_8b_fp8mixed.safetensors" -o \
  -name "full_encoder_small_decoder.safetensors" \
  \) -print -quit | grep -q .; then
  echo "PornMaster Flux2 business model files must stay out of the profile image" >&2
  exit 1
fi
echo "COMFYUI_DIR=${comfyui_dir}"
echo "PORNMASTER_FLUX2_EDIT_CORE_NODES_PRESENT=true"
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
    if ! docker push "$IMAGE_REF"; then
        case "$IMAGE_REF" in
            192.168.1.115:5000/*)
                fallback_ref="localhost:5000/${IMAGE_REF#192.168.1.115:5000/}"
                echo "Direct push to ${IMAGE_REF} failed; retrying via ${fallback_ref}"
                docker tag "$IMAGE_REF" "$fallback_ref"
                docker push "$fallback_ref"
                ;;
            *)
                exit 1
                ;;
        esac
    fi
fi
