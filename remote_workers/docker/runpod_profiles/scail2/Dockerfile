ARG BASE_IMAGE=yanwk/comfyui-boot:cu128-slim
FROM ${BASE_IMAGE}

ARG COMFYUI_REPO=https://github.com/Comfy-Org/ComfyUI.git
ARG COMFYUI_REF=f026b01ba576d98442839861a0eb0046bc2250d3
ARG COMFYUI_INSTALL_DIR=/opt/ComfyUI
ARG KJNODES_REPO=https://github.com/kijai/ComfyUI-KJNodes.git
ARG KJNODES_REF=7967a946c296a74901606e6a8d1195aa2b6f9215
ARG VIDEOHELPERSUITE_REPO=https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git
ARG VIDEOHELPERSUITE_REF=2984ec4c4b93292421888f38db74a5e8802a8ff8
ARG RGTHREE_REPO=https://github.com/rgthree/rgthree-comfy.git
ARG RGTHREE_REF=683836c46e898668936c433502504cc0627482c5
ARG FRAME_INTERPOLATION_REPO=https://github.com/Fannovel16/ComfyUI-Frame-Interpolation.git
ARG FRAME_INTERPOLATION_REF=26545cc2dd95bc3d27f056016300673bdeee78f5
ARG FILL_NODES_REPO=https://github.com/filliptm/ComfyUI_Fill-Nodes.git
ARG FILL_NODES_REF=2c94c3b675e7832ae18986e7062365c7d025b802
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG ALL_PROXY
ARG NO_PROXY

LABEL org.opencontainers.image.title="AllBot LAN SCAIL-2 ComfyUI test profile"
LABEL org.opencontainers.image.description="Test-only ComfyUI runtime for Nomadoor SCAIL-2 workflows; model files are synced from the LAN model cache at startup."
LABEL allbot.runpod.profile="scail2"
LABEL allbot.runpod.models="external-lan-manifest"
LABEL allbot.runpod.business_agent="false"

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ENV PIP_NO_CACHE_DIR=1

RUN set -euo pipefail; \
    if command -v apt-get >/dev/null 2>&1; then \
      apt-get update; \
      DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        ffmpeg \
        git \
        python3-pip; \
      rm -rf /var/lib/apt/lists/*; \
    elif command -v zypper >/dev/null 2>&1; then \
      zypper --non-interactive --gpg-auto-import-keys install --no-recommends \
        ca-certificates \
        curl \
        ffmpeg \
        git \
        python3-pip; \
      zypper clean --all; \
    fi

RUN set -euo pipefail; \
    git config --global http.version HTTP/1.1; \
    rm -rf "${COMFYUI_INSTALL_DIR}"; \
    for attempt in 1 2 3 4 5; do \
      git clone --filter=blob:none "${COMFYUI_REPO}" "${COMFYUI_INSTALL_DIR}" && break; \
      rm -rf "${COMFYUI_INSTALL_DIR}"; \
      if [ "$attempt" = "5" ]; then \
        echo "Failed to clone ComfyUI after ${attempt} attempts" >&2; \
        exit 128; \
      fi; \
      sleep $((attempt * 3)); \
    done; \
    git -C "${COMFYUI_INSTALL_DIR}" checkout --force "${COMFYUI_REF}"; \
    python3 -m pip install --no-cache-dir -r "${COMFYUI_INSTALL_DIR}/requirements.txt"; \
    test -f "${COMFYUI_INSTALL_DIR}/comfy_extras/nodes_scail.py"; \
    grep -R "WanSCAILToVideo" "${COMFYUI_INSTALL_DIR}/comfy_extras/nodes_scail.py" >/dev/null; \
    grep -R "SCAIL2ColoredMask" "${COMFYUI_INSTALL_DIR}/comfy_extras/nodes_scail.py" >/dev/null; \
    mkdir -p "${COMFYUI_INSTALL_DIR}/custom_nodes"; \
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
    clone_node "${KJNODES_REPO}" "${KJNODES_REF}" "${COMFYUI_INSTALL_DIR}/custom_nodes/ComfyUI-KJNodes"; \
    clone_node "${VIDEOHELPERSUITE_REPO}" "${VIDEOHELPERSUITE_REF}" "${COMFYUI_INSTALL_DIR}/custom_nodes/ComfyUI-VideoHelperSuite"; \
    clone_node "${RGTHREE_REPO}" "${RGTHREE_REF}" "${COMFYUI_INSTALL_DIR}/custom_nodes/rgthree-comfy"; \
    clone_node "${FRAME_INTERPOLATION_REPO}" "${FRAME_INTERPOLATION_REF}" "${COMFYUI_INSTALL_DIR}/custom_nodes/ComfyUI-Frame-Interpolation"; \
    clone_node "${FILL_NODES_REPO}" "${FILL_NODES_REF}" "${COMFYUI_INSTALL_DIR}/custom_nodes/ComfyUI_Fill-Nodes"; \
    python3 -m pip install --no-cache-dir minio packaging; \
    find "${COMFYUI_INSTALL_DIR}" -type d -name __pycache__ -prune -exec rm -rf {} +; \
    python3 -m pip cache purge >/dev/null 2>&1 || true; \
    rm -rf /root/.cache/pip /tmp/* /var/tmp/*; \
    echo "${COMFYUI_INSTALL_DIR}" > /opt/allbot-comfyui-dir

COPY remote_workers/scripts/runpod_sync_models_from_r2.py /opt/allbot/remote_workers/scripts/runpod_sync_models_from_r2.py
COPY remote_workers/scripts/lan_scail2_comfyui_entrypoint.sh /opt/allbot/lan_scail2_comfyui_entrypoint.sh
COPY remote_workers/comfy_agent/workflows/SCAIL-2_*.json /opt/allbot/scail2-workflows/

RUN set -euo pipefail; \
    chmod +x /opt/allbot/lan_scail2_comfyui_entrypoint.sh; \
    test -f /opt/allbot/scail2-workflows/SCAIL-2_Animation.json; \
    if find "$(cat /opt/allbot-comfyui-dir)/models" -type f \( \
      -name "wan2.1_14B_SCAIL_2_fp8_scaled.safetensors" -o \
      -name "sam3.1_multiplex_fp16.safetensors" -o \
      -name "clip_vision_h.safetensors" -o \
      -name "wan_2.1_vae.safetensors" -o \
      -name "umt5_xxl_fp8_e4m3fn_scaled.safetensors" -o \
      -name "Wan21_I2V_14B_lightx2v_cfg_step_distill_lora_rank64.safetensors" \
      \) -print -quit | grep -q .; then \
      echo "SCAIL-2 model files must stay out of the profile image" >&2; \
      exit 1; \
    fi

CMD ["bash", "/opt/allbot/lan_scail2_comfyui_entrypoint.sh"]
