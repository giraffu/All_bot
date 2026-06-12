ARG BASE_IMAGE=yanwk/comfyui-boot:cu128-slim
FROM ${BASE_IMAGE}

ARG KJNODES_REPO=https://github.com/kijai/ComfyUI-KJNodes.git
ARG KJNODES_REF=7967a946c296a74901606e6a8d1195aa2b6f9215
ARG VIDEOHELPERSUITE_REPO=https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git
ARG VIDEOHELPERSUITE_REF=main
ARG RGTHREE_REPO=https://github.com/rgthree/rgthree-comfy.git
ARG RGTHREE_REF=main
ARG FRAME_INTERPOLATION_REPO=https://github.com/Fannovel16/ComfyUI-Frame-Interpolation.git
ARG FRAME_INTERPOLATION_REF=main
ARG GGUF_REPO=https://github.com/city96/ComfyUI-GGUF.git
ARG GGUF_REF=main
ARG DASIWA_REPO=https://github.com/darksidewalker/ComfyUI-DaSiWa-Nodes.git
ARG DASIWA_REF=main
ARG WHITERABBIT_REPO=https://github.com/Artificial-Sweetener/comfyui-WhiteRabbit.git
ARG WHITERABBIT_REF=master

LABEL org.opencontainers.image.title="AllBot RunPod wan22_aio_video ComfyUI profile"
LABEL org.opencontainers.image.description="ComfyUI runtime profile with Wan22 AIO custom nodes baked in; model files are synced from R2 at Pod startup."
LABEL allbot.runpod.profile="wan22_aio_video"
LABEL allbot.runpod.models="external-r2-manifest"

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN if command -v apt-get >/dev/null 2>&1; then \
      apt-get update && \
      DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        ffmpeg \
        git \
        openssh-server \
        python3-pip && \
      rm -rf /var/lib/apt/lists/*; \
    fi

RUN set -euo pipefail; \
    if [ -f /default-comfyui-bundle/ComfyUI/main.py ]; then \
      comfyui_dir=/default-comfyui-bundle/ComfyUI; \
    elif [ -f /workspace/ComfyUI/main.py ]; then \
      comfyui_dir=/workspace/ComfyUI; \
    elif [ -f /root/ComfyUI/main.py ]; then \
      comfyui_dir=/root/ComfyUI; \
    else \
      echo "No ComfyUI main.py found in known image paths" >&2; \
      exit 75; \
    fi; \
    mkdir -p "${comfyui_dir}/custom_nodes"; \
    git config --global http.version HTTP/1.1; \
    clone_node() { \
      local repo="$1"; \
      local ref="$2"; \
      local target="$3"; \
      for attempt in 1 2 3 4 5; do \
        git clone --filter=blob:none "${repo}" "${target}" && break; \
        rm -rf "${target}"; \
        if [ "$attempt" = "5" ]; then \
          echo "Failed to clone ${repo} after ${attempt} attempts" >&2; \
          exit 128; \
        fi; \
        sleep $((attempt * 3)); \
      done; \
      git -C "${target}" checkout --force "${ref}"; \
      if [ -f "${target}/requirements.txt" ]; then \
        python3 -m pip install --no-cache-dir -r "${target}/requirements.txt"; \
      fi; \
    }; \
    clone_node "${KJNODES_REPO}" "${KJNODES_REF}" "${comfyui_dir}/custom_nodes/ComfyUI-KJNodes"; \
    clone_node "${VIDEOHELPERSUITE_REPO}" "${VIDEOHELPERSUITE_REF}" "${comfyui_dir}/custom_nodes/ComfyUI-VideoHelperSuite"; \
    clone_node "${RGTHREE_REPO}" "${RGTHREE_REF}" "${comfyui_dir}/custom_nodes/rgthree-comfy"; \
    clone_node "${FRAME_INTERPOLATION_REPO}" "${FRAME_INTERPOLATION_REF}" "${comfyui_dir}/custom_nodes/ComfyUI-Frame-Interpolation"; \
    clone_node "${GGUF_REPO}" "${GGUF_REF}" "${comfyui_dir}/custom_nodes/ComfyUI-GGUF"; \
    clone_node "${DASIWA_REPO}" "${DASIWA_REF}" "${comfyui_dir}/custom_nodes/ComfyUI-DaSiWa-Nodes"; \
    clone_node "${WHITERABBIT_REPO}" "${WHITERABBIT_REF}" "${comfyui_dir}/custom_nodes/comfyui-WhiteRabbit"; \
    python3 -m pip install --no-cache-dir packaging torchlanc; \
    find "${comfyui_dir}/models" -type f \( \
      -name 'wan22EnhancedNSFWSVICamera_nsfwFASTMOVEV2FP8H.safetensors' -o \
      -name 'wan22EnhancedNSFWSVICamera_nsfwFASTMOVEV2FP8L.safetensors' -o \
      -name 'DasiwaWAN22I2V14BLightspeed_snatchkissHighV11.safetensors' -o \
      -name 'DasiwaWAN22I2V14BLightspeed_snatchkissLowV11.safetensors' -o \
      -path '*/loras/*_high_noise.safetensors' -o \
      -path '*/loras/*_low_noise.safetensors' \
      \) -print -quit | \
      awk 'NF { print "Business model file unexpectedly present in image: " $0; exit 1 }'; \
    echo "${comfyui_dir}" > /opt/allbot-comfyui-dir
