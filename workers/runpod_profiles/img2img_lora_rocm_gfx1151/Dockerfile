ARG BASE_IMAGE=rocm/pytorch:rocm7.2.1_ubuntu24.04_py3.12_pytorch_release_2.9.1@sha256:96a2fb24dec9896e2f8238178f0c49d0dcc4c7dcc597be09e4564316bd86d191
FROM ${BASE_IMAGE}

ARG COMFYUI_REPO=https://github.com/Comfy-Org/ComfyUI.git
ARG COMFYUI_REF=7bf8bfcd078c7f4ae50ca5149c9ff7d8613e1fb1
ARG KJNODES_REPO=https://github.com/kijai/ComfyUI-KJNodes.git
ARG KJNODES_REF=7967a946c296a74901606e6a8d1195aa2b6f9215
ARG COMFYUI_INSTALL_DIR=/opt/ComfyUI
ARG ALLBOT_GIT_SHA
ARG ALLBOT_RUNTIME_PACKAGE_SHA256
ARG ALLBOT_WORKFLOW_MAPPING_SHA256
ENV ALLBOT_GIT_SHA=$ALLBOT_GIT_SHA \
    ALLBOT_RUNTIME_PACKAGE_SHA256=$ALLBOT_RUNTIME_PACKAGE_SHA256 \
    ALLBOT_WORKFLOW_MAPPING_SHA256=$ALLBOT_WORKFLOW_MAPPING_SHA256

LABEL org.opencontainers.image.title="AllBot img2img ROCm gfx1151 ComfyUI profile"
LABEL org.opencontainers.image.description="Ryzen AI Max+ 395 gfx1151 production img2img runtime using AMD-validated ROCm 7.2.1 and PyTorch 2.9.1."
LABEL allbot.lan.profile="img2img_lora_rocm_gfx1151"
LABEL allbot.lan.accelerator="rocm"
LABEL allbot.lan.llvm_target="gfx1151"
LABEL org.opencontainers.image.revision=$ALLBOT_GIT_SHA \
      io.allbot.runpod.agent-revision=$ALLBOT_GIT_SHA \
      io.allbot.runpod.workflow-revision=$ALLBOT_GIT_SHA

SHELL ["/bin/bash", "-o", "pipefail", "-c"]
ENV PIP_NO_CACHE_DIR=1 \
    TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL=1 \
    COMFYUI_DIR=/opt/ComfyUI

RUN set -euo pipefail; \
    apt-get update; \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      ca-certificates curl ffmpeg git libgl1 libglib2.0-0 openssh-server; \
    rm -rf /var/lib/apt/lists/*

RUN set -euo pipefail; \
    rm -rf "${COMFYUI_INSTALL_DIR}"; \
    mkdir -p "${COMFYUI_INSTALL_DIR}"; \
    git -C "${COMFYUI_INSTALL_DIR}" init; \
    git -C "${COMFYUI_INSTALL_DIR}" remote add origin "${COMFYUI_REPO}"; \
    for attempt in 1 2 3 4 5; do \
      git -C "${COMFYUI_INSTALL_DIR}" fetch --depth 1 --filter=blob:none origin "${COMFYUI_REF}" && break; \
      if [ "$attempt" = "5" ]; then exit 128; fi; \
      sleep $((attempt * 3)); \
    done; \
    git -C "${COMFYUI_INSTALL_DIR}" checkout --force FETCH_HEAD; \
    test "$(git -C "${COMFYUI_INSTALL_DIR}" rev-parse HEAD)" = "${COMFYUI_REF}"; \
    python3 -m pip install --no-cache-dir -r "${COMFYUI_INSTALL_DIR}/requirements.txt"; \
    rm -rf "${COMFYUI_INSTALL_DIR}/.git"; \
    mkdir -p "${COMFYUI_INSTALL_DIR}/custom_nodes"; \
    echo "${COMFYUI_INSTALL_DIR}" > /opt/allbot-comfyui-dir

RUN set -euo pipefail; \
    node_dir="${COMFYUI_INSTALL_DIR}/custom_nodes/ComfyUI-KJNodes"; \
    git clone --filter=blob:none "${KJNODES_REPO}" "${node_dir}"; \
    git -C "${node_dir}" checkout --detach "${KJNODES_REF}"; \
    test "$(git -C "${node_dir}" rev-parse HEAD)" = "${KJNODES_REF}"; \
    python3 -m pip install --no-cache-dir -r "${node_dir}/requirements.txt"; \
    rm -rf "${node_dir}/.git"

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
    PYTHONPATH=/opt/allbot/runtime/runpod_worker python3 - <<'PY'
import torch
assert torch.__version__.startswith("2.9.1+rocm7.2.1"), torch.__version__
assert str(torch.version.hip).startswith("7.2."), torch.version.hip
from comfy_agent.workflow_task_patchers import TASK_SPECIFIC_PATCHERS
from shared.character_reference_sheet import compose_ingredients_character_panel
assert TASK_SPECIFIC_PATCHERS
assert callable(compose_ingredients_character_panel)
PY

ENV ALLBOT_RUNPOD_REPO_DIR=/opt/allbot/runtime \
    ALLBOT_RUNPOD_WORKER_DIR=/opt/allbot/runtime/runpod_worker
CMD ["bash", "/opt/allbot/runpod_baked_runtime_entrypoint.sh"]
