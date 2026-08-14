ARG BASE_IMAGE=192.168.1.115:5000/allbot/comfyui-boot@sha256:09c810dd10ee5185cd7ee6e7d5d1b108118d85965838ad8c5ee1be425de1d5c1
ARG CUDA_DEVEL_IMAGE=192.168.1.115:5000/nvidia/cuda@sha256:45d0ca2dc7251cb51c9aa472760607cf4dfd354b5ec684422a6f49af82ea0603
ARG PYTHON_BUILDER_IMAGE=192.168.1.115:5000/library/python@sha256:9bde3c3a1ebcc25e36add077b92e8f1a7408f4e21efd6551bc02994f9ece70ee

FROM ${CUDA_DEVEL_IMAGE} AS cuda_devel

FROM ${BASE_IMAGE} AS python_runtime

FROM ${PYTHON_BUILDER_IMAGE} AS python_builder

FROM cuda_devel AS sage_builder

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ARG SAGEATTENTION_REPO=https://github.com/thu-ml/SageAttention.git
ARG SAGEATTENTION_REF=d1a57a546c3d395b1ffcbeecc66d81db76f3b4b5
ARG SAGEATTENTION_ARCHIVE_SHA256=74b6667164f9e368e3799bc2ab59b9b08c4591630f1c6029560208b6fcf354c4
ARG CUDA_INSTALL_DIR=/usr/local/cuda-12.8

COPY --from=python_builder /usr/local /usr/local

COPY --from=python_runtime /usr/local/lib64/python3.12/site-packages/torch /opt/python-lib64/torch
COPY --from=python_runtime /usr/local/lib64/python3.12/site-packages/torchgen /opt/python-lib64/torchgen
COPY --from=python_runtime /usr/local/lib64/python3.12/site-packages/torch-2.11.0+cu128.dist-info /opt/python-lib64/torch-2.11.0+cu128.dist-info
COPY --from=python_runtime /usr/local/lib64/python3.12/site-packages/triton /opt/python-lib64/triton
COPY --from=python_runtime /usr/local/lib64/python3.12/site-packages/triton-3.6.0.dist-info /opt/python-lib64/triton-3.6.0.dist-info
COPY --from=python_runtime /usr/local/lib64/python3.12/site-packages/cuda /opt/python-lib64/cuda
COPY --from=python_runtime /usr/local/lib/python3.12/site-packages/nvidia /opt/python-lib/nvidia

ENV CUDA_HOME=${CUDA_INSTALL_DIR} \
    PATH=${CUDA_INSTALL_DIR}/bin:${PATH} \
    PYTHONPATH=/opt/python-lib64:/opt/python-lib \
    TORCH_CUDA_ARCH_LIST=12.0 \
    EXT_PARALLEL=4 \
    MAX_JOBS=4 \
    NVCC_APPEND_FLAGS="--threads 4"

RUN set -euo pipefail; \
    command -v nvcc >/dev/null; \
    test "$(gcc -dumpfullversion)" = "13.3.0"; \
    python3 -m pip install --no-cache-dir \
      filelock fsspec jinja2 networkx ninja packaging 'setuptools<82' sympy typing-extensions wheel; \
    python3 -c 'import torch; assert torch.__version__ == "2.11.0+cu128"'; \
    archive_url="${SAGEATTENTION_REPO%.git}/archive/${SAGEATTENTION_REF}.tar.gz"; \
    python3 -c 'import sys, urllib.request; urllib.request.urlretrieve(sys.argv[1], sys.argv[2])' \
      "${archive_url}" /tmp/SageAttention.tar.gz; \
    echo "${SAGEATTENTION_ARCHIVE_SHA256}  /tmp/SageAttention.tar.gz" | sha256sum -c -; \
    mkdir -p /tmp/SageAttention; \
    tar -xzf /tmp/SageAttention.tar.gz --strip-components=1 -C /tmp/SageAttention; \
    python3 -m pip wheel --no-deps --no-build-isolation \
      --wheel-dir /opt/allbot-wheels /tmp/SageAttention; \
    test "$(find /opt/allbot-wheels -maxdepth 1 -type f -name 'sageattention-*.whl' | wc -l)" = 1

FROM ${BASE_IMAGE}

ARG COMFYUI_REPO=https://github.com/comfyanonymous/ComfyUI.git
ARG COMFYUI_REF=0764232429b8cfb10b79b6f186c8cb23e0b22897
ARG COMFYUI_ARCHIVE_SHA256=ba491752490e5b06ee3b918eb9ed20b637c6d60e0cc0fb68ac0e1d44fc033f81
ARG KJNODES_REPO=https://github.com/kijai/ComfyUI-KJNodes.git
ARG KJNODES_REF=1289b52fbb6d64a339a4047b9ea74cf7758ccf1e
ARG VHS_REPO=https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git
ARG VHS_REF=2984ec4c4b93292421888f38db74a5e8802a8ff8
ARG DASIWA_REPO=https://github.com/darksidewalker/ComfyUI-DaSiWa-Nodes.git
ARG DASIWA_REF=f6c759658513b120678bd5f96c2ec0b046a46a46
ARG COMFYUI_INSTALL_DIR=/opt/ComfyUI
ARG ALLBOT_GIT_SHA

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
    install_node "${DASIWA_REPO}" "${DASIWA_REF}" bfe493454a24eaf8732d163a3f2061169b319fbc9b5933013aa6da37e1674e18 ComfyUI-DaSiWa-Nodes

COPY --from=sage_builder /opt/allbot-wheels /opt/allbot-wheels

RUN set -euo pipefail; \
    python3 -m pip install --no-cache-dir /opt/allbot-wheels/sageattention-*.whl; \
    python3 -c 'from sageattention.core import get_cuda_arch_versions; assert callable(get_cuda_arch_versions)'; \
    rm -rf /opt/allbot-wheels

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
    grep -R -q 'DaSiWa_ResolutionScaleCalculator' "${COMFYUI_INSTALL_DIR}/custom_nodes/ComfyUI-DaSiWa-Nodes"; \
    PYTHONPATH=/opt/allbot/runtime/runpod_worker python3 -c 'from comfy_agent.workflow_task_patchers import TASK_SPECIFIC_PATCHERS as p; from shared.character_reference_sheet import compose_ingredients_character_panel; expected={"minimax_h3_t2v","minimax_h3_i2v","minimax_h3_flf2v"}; assert expected <= set(p); assert callable(compose_ingredients_character_panel)'; \
    python3 -c 'import json; from pathlib import Path; root=Path("/opt/allbot/runtime/runpod_worker/comfy_agent/workflows"); names=["MiniMax H3 T2V.api.json","MiniMax H3 I2V.api.json","MiniMax H3 FLF2V.api.json","MiniMax H3 REF2V.api.json"]; assert all(isinstance(json.loads((root/n).read_text()),dict) for n in names)'; \
    if find "${COMFYUI_INSTALL_DIR}/models" -type f -name '*.safetensors' -print -quit | grep -q .; then \
      echo "MiniMax H3 model files must stay out of the image" >&2; exit 1; \
    fi; \
    find "${COMFYUI_INSTALL_DIR}" -type d -name __pycache__ -prune -exec rm -rf {} +; \
    rm -rf /root/.cache/pip /tmp/* /var/tmp/*

LABEL org.opencontainers.image.title="AllBot MiniMax H3 RedMix profile" \
      org.opencontainers.image.description="Fixed RedMix MiniMax H3 T2V/I2V/FLF2V 8-step runtime with external model manifest" \
      org.opencontainers.image.revision=$ALLBOT_GIT_SHA \
      io.allbot.runpod.agent-revision=$ALLBOT_GIT_SHA \
      io.allbot.runpod.workflow-revision=$ALLBOT_GIT_SHA \
      allbot.runpod.profile="minimax_h3" \
      allbot.runpod.models="external-model-manifest"

ENV ALLBOT_RUNPOD_REPO_DIR=/opt/allbot/runtime \
    ALLBOT_RUNPOD_WORKER_DIR=/opt/allbot/runtime/runpod_worker
CMD ["bash", "-lc", "python3 -c 'from sageattention.core import get_cuda_arch_versions; archs=get_cuda_arch_versions(); assert \"sm120\" in archs, f\"MiniMax H3 requires compiled RTX 5090 SageAttention, detected {archs}\"'; exec bash /opt/allbot/runpod_baked_runtime_entrypoint.sh"]
