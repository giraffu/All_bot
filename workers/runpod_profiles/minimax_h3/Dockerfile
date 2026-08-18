ARG BASE_IMAGE=192.168.1.115:5000/allbot/comfyui-boot@sha256:09c810dd10ee5185cd7ee6e7d5d1b108118d85965838ad8c5ee1be425de1d5c1

FROM ${BASE_IMAGE}

ARG COMFYUI_REPO=https://github.com/comfyanonymous/ComfyUI.git
ARG COMFYUI_REF=7fe8a6138504f90ff7be82f3babf416da32876b1
ARG COMFYUI_ARCHIVE_SHA256=9b2ecedfe742e5b182ab2aa6e6b210a66b3f920e8a97ead8624daed5a2ccffc3
ARG KJNODES_REPO=https://github.com/kijai/ComfyUI-KJNodes.git
ARG KJNODES_REF=1289b52fbb6d64a339a4047b9ea74cf7758ccf1e
ARG VHS_REPO=https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git
ARG VHS_REF=2984ec4c4b93292421888f38db74a5e8802a8ff8
ARG DASIWA_REPO=https://github.com/darksidewalker/ComfyUI-DaSiWa-Nodes.git
ARG DASIWA_REF=f6c759658513b120678bd5f96c2ec0b046a46a46
ARG RESERVED_VRAM_REPO=https://github.com/Windecay/ComfyUI-ReservedVRAM.git
ARG RESERVED_VRAM_REF=be93b9375ebe8b24fa431609f56fa8f441b4b37f
ARG COMFYUI_INSTALL_DIR=/opt/ComfyUI

SHELL ["/bin/bash", "-o", "pipefail", "-c"]
ENV PIP_NO_CACHE_DIR=1

RUN set -euo pipefail; \
    command -v ffmpeg >/dev/null; command -v git >/dev/null; command -v python3 >/dev/null; \
    rm -rf "${COMFYUI_INSTALL_DIR}"; mkdir -p "${COMFYUI_INSTALL_DIR}"; \
    archive=/tmp/ComfyUI.tar.gz; repo_path="${COMFYUI_REPO#https://github.com/}"; repo_path="${repo_path%.git}"; \
    for attempt in 1 2 3; do \
      rm -f "$archive"; \
      if python3 -c 'import sys, urllib.request; urllib.request.urlretrieve(sys.argv[1], sys.argv[2])' \
        "https://codeload.github.com/${repo_path}/tar.gz/${COMFYUI_REF}" "$archive"; then break; fi; \
      test "$attempt" -lt 3; sleep "$((attempt * 2))"; \
    done; \
    echo "${COMFYUI_ARCHIVE_SHA256}  $archive" | sha256sum -c -; \
    tar -xzf "$archive" --strip-components=1 -C "${COMFYUI_INSTALL_DIR}"; \
    python3 -m pip install --no-cache-dir -r "${COMFYUI_INSTALL_DIR}/requirements.txt"; \
    rm -f "$archive"; \
    mkdir -p "${COMFYUI_INSTALL_DIR}/custom_nodes"; \
    echo "${COMFYUI_INSTALL_DIR}" > /opt/allbot-comfyui-dir

RUN set -euo pipefail; \
    install_node() { repo="$1"; ref="$2"; sha="$3"; name="$4"; target="${COMFYUI_INSTALL_DIR}/custom_nodes/${name}"; archive="/tmp/${name}.tar.gz"; repo_path="${repo#https://github.com/}"; repo_path="${repo_path%.git}"; \
      for attempt in 1 2 3; do \
        rm -f "$archive"; \
        if python3 -c 'import sys, urllib.request; urllib.request.urlretrieve(sys.argv[1], sys.argv[2])' \
          "https://codeload.github.com/${repo_path}/tar.gz/${ref}" "$archive"; then break; fi; \
        test "$attempt" -lt 3; sleep "$((attempt * 2))"; \
      done; \
      echo "$sha  $archive" | sha256sum -c -; \
      rm -rf "$target"; mkdir -p "$target"; tar -xzf "$archive" --strip-components=1 -C "$target"; \
      if [ -f "$target/requirements.txt" ]; then python3 -m pip install --no-cache-dir -r "$target/requirements.txt"; fi; \
      rm -f "$archive"; }; \
    install_node "${KJNODES_REPO}" "${KJNODES_REF}" d4dc73109ae070afd899a9844cd8b913b602a75cf10d901e2cba100e6dcc89f7 ComfyUI-KJNodes; \
    install_node "${VHS_REPO}" "${VHS_REF}" 69042eba3e2193a8f428d14bb9ebe97a03b64c0c4de4665c9c6c5f746e60c195 ComfyUI-VideoHelperSuite; \
    install_node "${DASIWA_REPO}" "${DASIWA_REF}" bfe493454a24eaf8732d163a3f2061169b319fbc9b5933013aa6da37e1674e18 ComfyUI-DaSiWa-Nodes; \
    install_node "${RESERVED_VRAM_REPO}" "${RESERVED_VRAM_REF}" 22124250c3da2f3b6cab6ebda7158d281144f6cfa9423c65f20b50112f29465c ComfyUI-ReservedVRAM

ARG ALLBOT_GIT_SHA
ARG ALLBOT_RUNTIME_PACKAGE_SHA256
ARG ALLBOT_WORKFLOW_MAPPING_SHA256
ENV ALLBOT_GIT_SHA=$ALLBOT_GIT_SHA \
    ALLBOT_RUNTIME_PACKAGE_SHA256=$ALLBOT_RUNTIME_PACKAGE_SHA256 \
    ALLBOT_WORKFLOW_MAPPING_SHA256=$ALLBOT_WORKFLOW_MAPPING_SHA256

COPY workers/runpod_runtime /opt/allbot/runtime/runpod_worker
COPY workers/comfy_agent /opt/allbot/runtime/runpod_worker/comfy_agent
COPY src /opt/allbot/runtime/runpod_worker/src
RUN test -n "$ALLBOT_GIT_SHA" && \
    test -n "$ALLBOT_RUNTIME_PACKAGE_SHA256" && \
    test -n "$ALLBOT_WORKFLOW_MAPPING_SHA256"
COPY shared /opt/allbot/runtime/runpod_worker/shared
COPY workers/runpod_runtime/scripts/runpod_bootstrap_from_git.sh /opt/allbot/runpod_bootstrap_from_git.sh
COPY workers/runpod_runtime/scripts/runpod_baked_runtime_entrypoint.sh /opt/allbot/runpod_baked_runtime_entrypoint.sh

RUN set -euo pipefail; \
    chmod +x /opt/allbot/runpod_bootstrap_from_git.sh /opt/allbot/runpod_baked_runtime_entrypoint.sh; \
    python3 -m pip install --no-cache-dir -r /opt/allbot/runtime/runpod_worker/requirements.txt; \
    grep -q 'MiniMaxH3ImageToVideo' "${COMFYUI_INSTALL_DIR}/comfy_extras/nodes_minimax_h3.py"; \
    grep -q 'MiniMaxH3SigmaShift' "${COMFYUI_INSTALL_DIR}/comfy_extras/nodes_minimax_h3.py"; \
    grep -q 'LoraLoaderModelOnly' "${COMFYUI_INSTALL_DIR}/nodes.py"; \
    grep -q 'ModelAttentionBackend' "${COMFYUI_INSTALL_DIR}/comfy_extras/nodes_model_advanced.py"; \
    grep -q 'ReservedVRAMSetter' "${COMFYUI_INSTALL_DIR}/custom_nodes/ComfyUI-ReservedVRAM/nodes.py"; \
    grep -R -q 'DaSiWa_ResolutionScaleCalculator' "${COMFYUI_INSTALL_DIR}/custom_nodes/ComfyUI-DaSiWa-Nodes"; \
    PYTHONPATH=/opt/allbot/runtime/runpod_worker python3 -c 'from comfy_agent.workflow_task_patchers import TASK_SPECIFIC_PATCHERS as p; from shared.character_reference_sheet import compose_ingredients_character_panel; expected={"minimax_h3_t2v","minimax_h3_i2v","minimax_h3_flf2v"}; assert expected <= set(p); assert callable(compose_ingredients_character_panel)'; \
    python3 -c 'import json; from pathlib import Path; root=Path("/opt/allbot/runtime/runpod_worker/comfy_agent/workflows"); names=["MiniMax H3 T2V.api.json","MiniMax H3 I2V.api.json","MiniMax H3 FLF2V.api.json"]; assert all(isinstance(json.loads((root/n).read_text()),dict) for n in names)'; \
    if find "${COMFYUI_INSTALL_DIR}/models" -type f -name '*.safetensors' -print -quit | grep -q .; then \
      echo "MiniMax H3 model files must stay out of the image" >&2; exit 1; \
    fi; \
    find "${COMFYUI_INSTALL_DIR}" -type d -name __pycache__ -prune -exec rm -rf {} +; \
    rm -rf /root/.cache/pip /tmp/* /var/tmp/*

LABEL org.opencontainers.image.title="AllBot MiniMax H3 author stack profile" \
      org.opencontainers.image.description="Pinned 10Eros Beta2, LightX2V 8-step and NaughtyTimes v2 T2V/I2V/FLF2V runtime with external model manifest" \
      org.opencontainers.image.revision=$ALLBOT_GIT_SHA \
      io.allbot.runpod.agent-revision=$ALLBOT_GIT_SHA \
      io.allbot.runpod.workflow-revision=$ALLBOT_GIT_SHA \
      allbot.runpod.profile="minimax_h3" \
      allbot.runpod.models="external-model-manifest"

ENV ALLBOT_RUNPOD_REPO_DIR=/opt/allbot/runtime \
    ALLBOT_RUNPOD_WORKER_DIR=/opt/allbot/runtime/runpod_worker
CMD ["bash", "/opt/allbot/runpod_baked_runtime_entrypoint.sh"]
