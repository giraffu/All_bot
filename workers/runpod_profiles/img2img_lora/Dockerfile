ARG BASE_IMAGE=yanwk/comfyui-boot:cu128-slim@sha256:4172d960fe57c630d33f6bd8891aa7ecf55e7768559565c6b74e8d57e44512a9
FROM ${BASE_IMAGE}

ARG KJNODES_REPO=https://github.com/kijai/ComfyUI-KJNodes.git
ARG KJNODES_REF=7967a946c296a74901606e6a8d1195aa2b6f9215

LABEL org.opencontainers.image.title="AllBot RunPod img2img_lora ComfyUI profile"
LABEL org.opencontainers.image.description="ComfyUI runtime profile with img2img_lora custom nodes baked in; model files are synced from R2 at Pod startup."
LABEL allbot.runpod.profile="img2img_lora"
LABEL allbot.runpod.models="external-r2-manifest"
ARG ALLBOT_GIT_SHA
ARG ALLBOT_RUNTIME_PACKAGE_SHA256
ARG ALLBOT_WORKFLOW_MAPPING_SHA256
ENV ALLBOT_GIT_SHA=$ALLBOT_GIT_SHA \
    ALLBOT_RUNTIME_PACKAGE_SHA256=$ALLBOT_RUNTIME_PACKAGE_SHA256 \
    ALLBOT_WORKFLOW_MAPPING_SHA256=$ALLBOT_WORKFLOW_MAPPING_SHA256
LABEL org.opencontainers.image.revision=$ALLBOT_GIT_SHA \
      io.allbot.runpod.agent-revision=$ALLBOT_GIT_SHA \
      io.allbot.runpod.workflow-revision=$ALLBOT_GIT_SHA

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
    for attempt in 1 2 3 4 5; do \
      git clone --filter=blob:none "${KJNODES_REPO}" "${comfyui_dir}/custom_nodes/ComfyUI-KJNodes" && break; \
      rm -rf "${comfyui_dir}/custom_nodes/ComfyUI-KJNodes"; \
      if [ "$attempt" = "5" ]; then \
        echo "Failed to clone ComfyUI-KJNodes after ${attempt} attempts" >&2; \
        exit 128; \
      fi; \
      sleep $((attempt * 3)); \
    done; \
    git -C "${comfyui_dir}/custom_nodes/ComfyUI-KJNodes" checkout --force "${KJNODES_REF}"; \
    if [ -f "${comfyui_dir}/custom_nodes/ComfyUI-KJNodes/requirements.txt" ]; then \
      python3 -m pip install --no-cache-dir -r "${comfyui_dir}/custom_nodes/ComfyUI-KJNodes/requirements.txt"; \
    fi; \
    find "${comfyui_dir}/models" -type f \( -name 'Qwen-Rapid-AIO-NSFW-v23.safetensors' -o -path '*/loras/qwen/*.safetensors' \) -print -quit | \
      awk 'NF { print "Business model file unexpectedly present in image: " $0; exit 1 }'; \
    echo "${comfyui_dir}" > /opt/allbot-comfyui-dir

COPY workers/runpod_runtime /opt/allbot/runtime/runpod_worker
COPY workers/comfy_agent /opt/allbot/runtime/runpod_worker/comfy_agent
COPY src /opt/allbot/runtime/runpod_worker/src
RUN test -n "$ALLBOT_GIT_SHA" && \
    test -n "$ALLBOT_RUNTIME_PACKAGE_SHA256" && \
    test -n "$ALLBOT_WORKFLOW_MAPPING_SHA256"
COPY shared /opt/allbot/runtime/runpod_worker/shared
COPY workers/runpod_runtime/scripts/runpod_bootstrap_from_git.sh /opt/allbot/runpod_bootstrap_from_git.sh
COPY workers/runpod_runtime/scripts/runpod_baked_runtime_entrypoint.sh /opt/allbot/runpod_baked_runtime_entrypoint.sh

RUN chmod +x /opt/allbot/runpod_bootstrap_from_git.sh /opt/allbot/runpod_baked_runtime_entrypoint.sh && \
    python3 -m pip install --no-cache-dir -r /opt/allbot/runtime/runpod_worker/requirements.txt && \
    PYTHONPATH=/opt/allbot/runtime/runpod_worker python3 -c 'from comfy_agent.workflow_task_patchers import TASK_SPECIFIC_PATCHERS; from shared.character_reference_sheet import compose_ingredients_character_panel; assert callable(compose_ingredients_character_panel)'

ENV ALLBOT_RUNPOD_REPO_DIR=/opt/allbot/runtime \
    ALLBOT_RUNPOD_WORKER_DIR=/opt/allbot/runtime/runpod_worker
CMD ["bash", "/opt/allbot/runpod_baked_runtime_entrypoint.sh"]
