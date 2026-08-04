ARG BASE_IMAGE=yanwk/comfyui-boot:cu128-slim
FROM ${BASE_IMAGE}

ARG COMFYUI_REPO=https://github.com/comfyanonymous/ComfyUI.git
ARG COMFYUI_REF=0764232429b8cfb10b79b6f186c8cb23e0b22897
ARG KJNODES_REPO=https://github.com/kijai/ComfyUI-KJNodes.git
ARG KJNODES_REF=1289b52fbb6d64a339a4047b9ea74cf7758ccf1e
ARG VHS_REPO=https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git
ARG VHS_REF=2984ec4c4b93292421888f38db74a5e8802a8ff8
ARG DASIWA_REPO=https://github.com/darksidewalker/ComfyUI-DaSiWa-Nodes.git
ARG DASIWA_REF=f6c759658513b120678bd5f96c2ec0b046a46a46
ARG COMFYUI_INSTALL_DIR=/opt/ComfyUI
ARG SAGEATTENTION_VERSION=1.0.6
ARG ALLBOT_GIT_SHA

LABEL org.opencontainers.image.title="AllBot MiniMax H3 DaSiWa profile" \
      org.opencontainers.image.description="MiniMax H3 T2V/I2V/FLF2V/REF2V runtime with external model manifest" \
      org.opencontainers.image.revision=$ALLBOT_GIT_SHA \
      io.allbot.runpod.agent-revision=$ALLBOT_GIT_SHA \
      io.allbot.runpod.workflow-revision=$ALLBOT_GIT_SHA \
      allbot.runpod.profile="minimax_h3" \
      allbot.runpod.models="external-model-manifest"

SHELL ["/bin/bash", "-o", "pipefail", "-c"]
ENV PIP_NO_CACHE_DIR=1

RUN set -euo pipefail; \
    command -v ffmpeg >/dev/null; command -v git >/dev/null; command -v python3 >/dev/null; \
    rm -rf "${COMFYUI_INSTALL_DIR}"; mkdir -p "${COMFYUI_INSTALL_DIR}"; \
    git -C "${COMFYUI_INSTALL_DIR}" init; \
    git -C "${COMFYUI_INSTALL_DIR}" remote add origin "${COMFYUI_REPO}"; \
    git -C "${COMFYUI_INSTALL_DIR}" fetch --depth 1 --filter=blob:none origin "${COMFYUI_REF}"; \
    git -C "${COMFYUI_INSTALL_DIR}" checkout --force FETCH_HEAD; \
    test "$(git -C "${COMFYUI_INSTALL_DIR}" rev-parse HEAD)" = "${COMFYUI_REF}"; \
    python3 -m pip install --no-cache-dir -r "${COMFYUI_INSTALL_DIR}/requirements.txt"; \
    rm -rf "${COMFYUI_INSTALL_DIR}/.git"; \
    mkdir -p "${COMFYUI_INSTALL_DIR}/custom_nodes"; \
    echo "${COMFYUI_INSTALL_DIR}" > /opt/allbot-comfyui-dir

RUN set -euo pipefail; \
    clone_node() { repo="$1"; ref="$2"; name="$3"; target="${COMFYUI_INSTALL_DIR}/custom_nodes/${name}"; \
      git clone --filter=blob:none "$repo" "$target"; git -C "$target" checkout --detach "$ref"; \
      test "$(git -C "$target" rev-parse HEAD)" = "$ref"; \
      if [ -f "$target/requirements.txt" ]; then python3 -m pip install --no-cache-dir -r "$target/requirements.txt"; fi; \
      rm -rf "$target/.git"; }; \
    clone_node "${KJNODES_REPO}" "${KJNODES_REF}" ComfyUI-KJNodes; \
    clone_node "${VHS_REPO}" "${VHS_REF}" ComfyUI-VideoHelperSuite; \
    clone_node "${DASIWA_REPO}" "${DASIWA_REF}" ComfyUI-DaSiWa-Nodes; \
    python3 -m pip install --no-cache-dir "sageattention==${SAGEATTENTION_VERSION}"

COPY workers/runpod_runtime /opt/allbot/runtime/runpod_worker
COPY shared /opt/allbot/runtime/runpod_worker/shared
COPY workers/runpod_runtime/scripts/runpod_bootstrap_from_git.sh /opt/allbot/runpod_bootstrap_from_git.sh
COPY workers/runpod_runtime/scripts/runpod_baked_runtime_entrypoint.sh /opt/allbot/runpod_baked_runtime_entrypoint.sh

RUN set -euo pipefail; \
    chmod +x /opt/allbot/runpod_bootstrap_from_git.sh /opt/allbot/runpod_baked_runtime_entrypoint.sh; \
    python3 -m pip install --no-cache-dir -r /opt/allbot/runtime/runpod_worker/requirements.txt; \
    grep -q 'MiniMaxH3ImageToVideo' "${COMFYUI_INSTALL_DIR}/comfy_extras/nodes_minimax_h3.py"; \
    grep -q 'MiniMaxH3ReferenceToVideo' "${COMFYUI_INSTALL_DIR}/comfy_extras/nodes_minimax_h3.py"; \
    grep -q 'MiniMaxH3MemoryEfficientSageAttentionPatch' "${COMFYUI_INSTALL_DIR}/custom_nodes/ComfyUI-KJNodes/nodes/ltxv_nodes.py"; \
    PYTHONPATH=/opt/allbot/runtime/runpod_worker python3 -c 'from comfy_agent.workflow_task_patchers import TASK_SPECIFIC_PATCHERS as p; expected={"minimax_h3_t2v","minimax_h3_i2v","minimax_h3_flf2v","minimax_h3_ref2v"}; assert expected <= set(p)'; \
    python3 -c 'import json; from pathlib import Path; root=Path("/opt/allbot/runtime/runpod_worker/comfy_agent/workflows"); names=["MiniMax H3 T2V.api.json","MiniMax H3 I2V.api.json","MiniMax H3 FLF2V.api.json","MiniMax H3 REF2V.api.json"]; assert all(isinstance(json.loads((root/n).read_text()),dict) for n in names)'; \
    if find "${COMFYUI_INSTALL_DIR}/models" -type f -name '*.safetensors' -print -quit | grep -q .; then \
      echo "MiniMax H3 model files must stay out of the image" >&2; exit 1; \
    fi; \
    find "${COMFYUI_INSTALL_DIR}" -type d -name __pycache__ -prune -exec rm -rf {} +; \
    rm -rf /root/.cache/pip /tmp/* /var/tmp/*

ENV ALLBOT_RUNPOD_REPO_DIR=/opt/allbot/runtime \
    ALLBOT_RUNPOD_WORKER_DIR=/opt/allbot/runtime/runpod_worker
CMD ["bash", "/opt/allbot/runpod_baked_runtime_entrypoint.sh"]
