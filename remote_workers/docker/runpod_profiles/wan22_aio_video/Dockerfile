ARG BASE_IMAGE=runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404
FROM ${BASE_IMAGE}

ARG COMFYUI_REPO=https://github.com/comfyanonymous/ComfyUI.git
ARG COMFYUI_REF=master
ARG COMFYUI_INSTALL_DIR=/opt/ComfyUI
ARG KJNODES_REPO=https://github.com/kijai/ComfyUI-KJNodes.git
ARG KJNODES_REF=7967a946c296a74901606e6a8d1195aa2b6f9215
ARG VIDEOHELPERSUITE_REPO=https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git
ARG VIDEOHELPERSUITE_REF=main
ARG RGTHREE_REPO=https://github.com/rgthree/rgthree-comfy.git
ARG RGTHREE_REF=main
ARG FRAME_INTERPOLATION_REPO=https://github.com/Fannovel16/ComfyUI-Frame-Interpolation.git
ARG FRAME_INTERPOLATION_REF=main
ARG FILL_NODES_REPO=https://github.com/filliptm/ComfyUI_Fill-Nodes.git
ARG FILL_NODES_REF=main
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

ENV PIP_NO_CACHE_DIR=1

RUN set -euo pipefail; \
    if command -v apt-get >/dev/null 2>&1; then \
      packages="ca-certificates curl ffmpeg git openssh-server"; \
      if ! python3 -m pip --version >/dev/null 2>&1; then \
        packages="${packages} python3-pip"; \
      fi; \
      apt-get update; \
      DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ${packages}; \
      rm -rf /var/lib/apt/lists/*; \
    fi

RUN set -euo pipefail; \
    find_comfyui_dir() { \
      for candidate in \
        /default-comfyui-bundle/ComfyUI \
        /workspace/ComfyUI \
        /root/ComfyUI \
        "${COMFYUI_INSTALL_DIR}"; do \
        if [ -f "${candidate}/main.py" ]; then \
          printf '%s\n' "${candidate}"; \
          return 0; \
        fi; \
      done; \
      return 1; \
    }; \
    if comfyui_dir="$(find_comfyui_dir)"; then \
      echo "Using existing ComfyUI at ${comfyui_dir}"; \
    else \
      comfyui_dir="${COMFYUI_INSTALL_DIR}"; \
      rm -rf "${comfyui_dir}"; \
      git clone --filter=blob:none "${COMFYUI_REPO}" "${comfyui_dir}"; \
      git -C "${comfyui_dir}" checkout --force "${COMFYUI_REF}"; \
      if [ -f "${comfyui_dir}/requirements.txt" ]; then \
        python3 -m pip install --no-cache-dir -r "${comfyui_dir}/requirements.txt"; \
      fi; \
      rm -rf "${comfyui_dir}/.git"; \
    fi; \
    mkdir -p "${comfyui_dir}/custom_nodes"; \
    git config --global http.version HTTP/1.1; \
    clone_node() { \
      local repo="$1"; \
      local ref="$2"; \
      local target="$3"; \
      rm -rf "${target}"; \
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
      rm -rf "${target}/.git"; \
    }; \
    clone_node "${KJNODES_REPO}" "${KJNODES_REF}" "${comfyui_dir}/custom_nodes/ComfyUI-KJNodes"; \
    clone_node "${VIDEOHELPERSUITE_REPO}" "${VIDEOHELPERSUITE_REF}" "${comfyui_dir}/custom_nodes/ComfyUI-VideoHelperSuite"; \
    clone_node "${RGTHREE_REPO}" "${RGTHREE_REF}" "${comfyui_dir}/custom_nodes/rgthree-comfy"; \
    clone_node "${FRAME_INTERPOLATION_REPO}" "${FRAME_INTERPOLATION_REF}" "${comfyui_dir}/custom_nodes/ComfyUI-Frame-Interpolation"; \
    clone_node "${GGUF_REPO}" "${GGUF_REF}" "${comfyui_dir}/custom_nodes/ComfyUI-GGUF"; \
    clone_node "${DASIWA_REPO}" "${DASIWA_REF}" "${comfyui_dir}/custom_nodes/ComfyUI-DaSiWa-Nodes"; \
    clone_node "${WHITERABBIT_REPO}" "${WHITERABBIT_REF}" "${comfyui_dir}/custom_nodes/comfyui-WhiteRabbit"; \
    python3 -m pip install --no-cache-dir packaging torchlanc; \
    if [ -d "${comfyui_dir}/models" ]; then \
      find "${comfyui_dir}/models" -type f \( \
        -name 'wan22EnhancedNSFWSVICamera_nsfwFASTMOVEV2FP8H.safetensors' -o \
        -name 'wan22EnhancedNSFWSVICamera_nsfwFASTMOVEV2FP8L.safetensors' -o \
        -name 'DasiwaWAN22I2V14BLightspeed_snatchkissHighV11.safetensors' -o \
        -name 'DasiwaWAN22I2V14BLightspeed_snatchkissLowV11.safetensors' -o \
        -path '*/loras/*_high_noise.safetensors' -o \
        -path '*/loras/*_low_noise.safetensors' \
        \) -print -quit | \
        awk 'NF { print "Business model file unexpectedly present in image: " $0; exit 1 }'; \
    fi; \
    find "${comfyui_dir}" -type d -name __pycache__ -prune -exec rm -rf {} +; \
    python3 -m pip cache purge >/dev/null 2>&1 || true; \
    rm -rf /root/.cache/pip /tmp/* /var/tmp/*; \
    echo "${comfyui_dir}" > /opt/allbot-comfyui-dir

# Keep the FL_RIFE provider in a final small layer so Wan22 node fixes do not
# invalidate the heavier baked custom-node layer.
RUN set -euo pipefail; \
    if [ -s /opt/allbot-comfyui-dir ]; then \
      comfyui_dir="$(cat /opt/allbot-comfyui-dir)"; \
    elif [ -f /default-comfyui-bundle/ComfyUI/main.py ]; then \
      comfyui_dir=/default-comfyui-bundle/ComfyUI; \
    elif [ -f /workspace/ComfyUI/main.py ]; then \
      comfyui_dir=/workspace/ComfyUI; \
    elif [ -f /root/ComfyUI/main.py ]; then \
      comfyui_dir=/root/ComfyUI; \
    else \
      comfyui_dir="${COMFYUI_INSTALL_DIR}"; \
    fi; \
    test -f "${comfyui_dir}/main.py"; \
    mkdir -p "${comfyui_dir}/custom_nodes"; \
    target="${comfyui_dir}/custom_nodes/ComfyUI_Fill-Nodes"; \
    rm -rf "${target}"; \
    git config --global http.version HTTP/1.1; \
    for attempt in 1 2 3 4 5; do \
      git clone --filter=blob:none "${FILL_NODES_REPO}" "${target}" && break; \
      rm -rf "${target}"; \
      if [ "$attempt" = "5" ]; then \
        echo "Failed to clone ${FILL_NODES_REPO} after ${attempt} attempts" >&2; \
        exit 128; \
      fi; \
      sleep $((attempt * 3)); \
    done; \
    git -C "${target}" checkout --force "${FILL_NODES_REF}"; \
    if [ -f "${target}/requirements.txt" ]; then \
      python3 -m pip install --no-cache-dir -r "${target}/requirements.txt"; \
    fi; \
    rm -rf "${target}/.git"; \
    find "${target}" -type d -name __pycache__ -prune -exec rm -rf {} +; \
    python3 -m pip cache purge >/dev/null 2>&1 || true; \
    rm -rf /root/.cache/pip /tmp/* /var/tmp/*

ARG LTXVIDEO_REPO=https://github.com/Lightricks/ComfyUI-LTXVideo.git
ARG LTXVIDEO_REF=master

# Wan22AioV82 uses LTXVSpatioTemporalTiledVAEDecode for video VAE decode.
RUN set -euo pipefail; \
    if [ -s /opt/allbot-comfyui-dir ]; then \
      comfyui_dir="$(cat /opt/allbot-comfyui-dir)"; \
    elif [ -f /default-comfyui-bundle/ComfyUI/main.py ]; then \
      comfyui_dir=/default-comfyui-bundle/ComfyUI; \
    elif [ -f /workspace/ComfyUI/main.py ]; then \
      comfyui_dir=/workspace/ComfyUI; \
    elif [ -f /root/ComfyUI/main.py ]; then \
      comfyui_dir=/root/ComfyUI; \
    else \
      comfyui_dir="${COMFYUI_INSTALL_DIR}"; \
    fi; \
    test -f "${comfyui_dir}/main.py"; \
    mkdir -p "${comfyui_dir}/custom_nodes"; \
    target="${comfyui_dir}/custom_nodes/ComfyUI-LTXVideo"; \
    rm -rf "${target}"; \
    git config --global http.version HTTP/1.1; \
    for attempt in 1 2 3 4 5; do \
      git clone --filter=blob:none "${LTXVIDEO_REPO}" "${target}" && break; \
      rm -rf "${target}"; \
      if [ "$attempt" = "5" ]; then \
        echo "Failed to clone ${LTXVIDEO_REPO} after ${attempt} attempts" >&2; \
        exit 128; \
      fi; \
      sleep $((attempt * 3)); \
    done; \
    git -C "${target}" checkout --force "${LTXVIDEO_REF}"; \
    if [ -f "${target}/requirements.txt" ]; then \
      python3 -m pip install --no-cache-dir -r "${target}/requirements.txt"; \
    fi; \
    grep -R "LTXVSpatioTemporalTiledVAEDecode" "${target}" >/dev/null; \
    rm -rf "${target}/.git"; \
    find "${target}" -type d -name __pycache__ -prune -exec rm -rf {} +; \
    python3 -m pip cache purge >/dev/null 2>&1 || true; \
    rm -rf /root/.cache/pip /tmp/* /var/tmp/*
