ARG BASE_IMAGE=yanwk/comfyui-boot:cu128-slim@sha256:4172d960fe57c630d33f6bd8891aa7ecf55e7768559565c6b74e8d57e44512a9
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
ARG XFORMERS_SOURCE_URL=https://github.com/facebookresearch/xformers.git
ARG XFORMERS_SOURCE_REF=
ARG XFORMERS_CUDA_ARCH_LIST=12.0
ARG XFORMERS_MAX_JOBS=16
ARG XFORMERS_NVCC_THREADS=4
ARG ALLBOT_GIT_SHA
ARG ALLBOT_RUNTIME_PACKAGE_SHA256
ARG ALLBOT_WORKFLOW_MAPPING_SHA256
ENV ALLBOT_GIT_SHA=$ALLBOT_GIT_SHA \
    ALLBOT_RUNTIME_PACKAGE_SHA256=$ALLBOT_RUNTIME_PACKAGE_SHA256 \
    ALLBOT_WORKFLOW_MAPPING_SHA256=$ALLBOT_WORKFLOW_MAPPING_SHA256

LABEL org.opencontainers.image.title="AllBot SCAIL-2 ComfyUI test profile"
LABEL org.opencontainers.image.description="Test-only ComfyUI runtime for Nomadoor SCAIL-2 workflows; model files are synced from the R2/LAN manifest at startup."
LABEL allbot.runpod.profile="scail2"
LABEL allbot.runpod.models="external-r2-manifest"
LABEL allbot.runpod.business_agent="false"
LABEL org.opencontainers.image.revision=$ALLBOT_GIT_SHA \
      io.allbot.runpod.agent-revision=$ALLBOT_GIT_SHA \
      io.allbot.runpod.workflow-revision=$ALLBOT_GIT_SHA

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ENV PIP_NO_CACHE_DIR=1
ENV PIP_BREAK_SYSTEM_PACKAGES=1

RUN set -euo pipefail; \
    if command -v apt-get >/dev/null 2>&1; then \
      packages="ca-certificates curl git openssh-client openssh-server python3-pip"; \
      if ! command -v ffmpeg >/dev/null 2>&1; then \
        packages="${packages} ffmpeg"; \
      fi; \
      apt-get update; \
      DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ${packages}; \
      rm -rf /var/lib/apt/lists/*; \
    elif command -v zypper >/dev/null 2>&1; then \
      packages="ca-certificates curl git openssh python3-pip"; \
      if ! command -v ffmpeg >/dev/null 2>&1; then \
        packages="${packages} ffmpeg"; \
      fi; \
      zypper --non-interactive --gpg-auto-import-keys install --no-recommends ${packages}; \
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
    if [ -n "${XFORMERS_SOURCE_REF}" ]; then \
      python3 -m pip install --no-cache-dir cmake ninja packaging; \
      TORCH_CUDA_ARCH_LIST="${XFORMERS_CUDA_ARCH_LIST}" \
      MAX_JOBS="${XFORMERS_MAX_JOBS}" \
      NVCC_THREADS="${XFORMERS_NVCC_THREADS}" \
        python3 -m pip install --no-cache-dir --no-build-isolation --no-deps --force-reinstall -v \
        "git+${XFORMERS_SOURCE_URL}@${XFORMERS_SOURCE_REF}#egg=xformers"; \
      python3 -m xformers.info; \
    fi; \
    python3 -m pip install --no-cache-dir minio packaging; \
    find "${COMFYUI_INSTALL_DIR}" -type d -name __pycache__ -prune -exec rm -rf {} +; \
    python3 -m pip cache purge >/dev/null 2>&1 || true; \
    rm -rf /root/.cache/pip /tmp/* /var/tmp/*; \
    echo "${COMFYUI_INSTALL_DIR}" > /opt/allbot-comfyui-dir

COPY workers/runpod_runtime/scripts/runpod_sync_models_from_r2.py /opt/allbot/runpod_worker/scripts/runpod_sync_models_from_r2.py
COPY workers/runpod_runtime /opt/allbot/runtime/runpod_worker
COPY workers/comfy_agent /opt/allbot/runtime/runpod_worker/comfy_agent
COPY src /opt/allbot/runtime/runpod_worker/src
RUN test -n "$ALLBOT_GIT_SHA" && \
    test -n "$ALLBOT_RUNTIME_PACKAGE_SHA256" && \
    test -n "$ALLBOT_WORKFLOW_MAPPING_SHA256"
COPY shared /opt/allbot/runtime/runpod_worker/shared
COPY workers/runpod_runtime/scripts/runpod_bootstrap_from_git.sh /opt/allbot/runpod_bootstrap_from_git.sh
COPY workers/runpod_runtime/scripts/runpod_baked_runtime_entrypoint.sh /opt/allbot/runpod_baked_runtime_entrypoint.sh
COPY workers/runpod_runtime/scripts/lan_scail2_comfyui_entrypoint.sh /opt/allbot/lan_scail2_comfyui_entrypoint.sh
COPY workers/comfy_agent/workflows/SCAIL-2_*.json /opt/allbot/scail2-workflows/
COPY workers/runpod_runtime/requirements.txt /opt/allbot/runpod_worker/requirements.txt

RUN set -euo pipefail; \
    chmod +x /opt/allbot/runpod_bootstrap_from_git.sh /opt/allbot/runpod_baked_runtime_entrypoint.sh; \
    chmod +x /opt/allbot/lan_scail2_comfyui_entrypoint.sh; \
    python3 -m pip install --no-cache-dir -r /opt/allbot/runpod_worker/requirements.txt; \
    python3 -c 'import fastapi, minio, uvicorn, websockets'; \
    PYTHONPATH=/opt/allbot/runtime/runpod_worker python3 -c 'from comfy_agent.workflow_task_patchers import TASK_SPECIFIC_PATCHERS; from shared.character_reference_sheet import compose_ingredients_character_panel; assert callable(compose_ingredients_character_panel)'; \
    command -v ssh-keygen >/dev/null; \
    if ! command -v sshd >/dev/null && [ ! -x /usr/sbin/sshd ]; then \
      echo "sshd must be available for RunPod direct TCP diagnostics" >&2; \
      exit 1; \
    fi; \
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

ENV ALLBOT_RUNPOD_REPO_DIR=/opt/allbot/runtime \
    ALLBOT_RUNPOD_WORKER_DIR=/opt/allbot/runtime/runpod_worker
CMD ["bash", "/opt/allbot/runpod_baked_runtime_entrypoint.sh"]
