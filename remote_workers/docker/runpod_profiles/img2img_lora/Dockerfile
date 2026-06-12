ARG BASE_IMAGE=yanwk/comfyui-boot:cu128-slim
FROM ${BASE_IMAGE}

ARG KJNODES_REPO=https://github.com/kijai/ComfyUI-KJNodes.git
ARG KJNODES_REF=7967a946c296a74901606e6a8d1195aa2b6f9215

LABEL org.opencontainers.image.title="AllBot RunPod img2img_lora ComfyUI profile"
LABEL org.opencontainers.image.description="ComfyUI runtime profile with img2img_lora custom nodes baked in; model files are synced from R2 at Pod startup."
LABEL allbot.runpod.profile="img2img_lora"
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
