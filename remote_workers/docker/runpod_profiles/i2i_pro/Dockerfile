ARG BASE_IMAGE=yanwk/comfyui-boot:cu128-slim
FROM ${BASE_IMAGE}

ARG COMFYUI_REPO=https://github.com/comfyanonymous/ComfyUI.git
ARG COMFYUI_REF=16cd8d8a8f5f16ce7e5f929fdba9f783990254ea
ARG COMFYUI_INSTALL_DIR=/opt/ComfyUI

LABEL org.opencontainers.image.title="AllBot RunPod i2i_pro ComfyUI profile"
LABEL org.opencontainers.image.description="ComfyUI runtime profile for i2i_pro; model files are synced from R2 at Pod startup."
LABEL allbot.runpod.profile="i2i_pro"
LABEL allbot.runpod.models="external-r2-manifest"

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ENV PIP_NO_CACHE_DIR=1

RUN set -euo pipefail; \
    if command -v apt-get >/dev/null 2>&1; then \
      packages="ca-certificates curl ffmpeg findutils git openssh-server"; \
      if ! python3 -m pip --version >/dev/null 2>&1; then \
        packages="${packages} python3-pip"; \
      fi; \
      apt-get update; \
      DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ${packages}; \
      rm -rf /var/lib/apt/lists/*; \
    fi

RUN set -euo pipefail; \
    comfyui_dir="${COMFYUI_INSTALL_DIR}"; \
    rm -rf "${comfyui_dir}"; \
    git config --global http.version HTTP/1.1; \
    for attempt in 1 2 3 4 5; do \
      git clone --filter=blob:none "${COMFYUI_REPO}" "${comfyui_dir}" && break; \
      rm -rf "${comfyui_dir}"; \
      if [ "$attempt" = "5" ]; then \
        echo "Failed to clone ComfyUI after ${attempt} attempts" >&2; \
        exit 128; \
      fi; \
      sleep $((attempt * 3)); \
    done; \
    git -C "${comfyui_dir}" checkout --force "${COMFYUI_REF}"; \
    if [ -f "${comfyui_dir}/requirements.txt" ]; then \
      python3 -m pip install --no-cache-dir -r "${comfyui_dir}/requirements.txt"; \
    fi; \
    rm -rf "${comfyui_dir}/.git"; \
    python3 -m pip cache purge >/dev/null 2>&1 || true; \
    rm -rf /root/.cache/pip /tmp/* /var/tmp/*; \
    echo "${comfyui_dir}" > /opt/allbot-comfyui-dir

RUN set -euo pipefail; \
    comfyui_dir="$(cat /opt/allbot-comfyui-dir)"; \
    test -f "${comfyui_dir}/main.py"; \
    python3 -c 'from pathlib import Path; import sys; root=Path("/opt/allbot-comfyui-dir").read_text().strip(); root=Path(root); checks={root/"nodes.py":("UNETLoader","CLIPLoader","VAELoader"),root/"comfy_extras"/"nodes_custom_sampler.py":("SamplerCustomAdvanced",),root/"comfy_extras"/"nodes_edit_model.py":("ReferenceLatent",),root/"comfy_extras"/"nodes_flux.py":("EmptyFlux2LatentImage","Flux2Scheduler")}; missing=[]; [missing.append(f"{path}:{name}") for path,names in checks.items() for name in names if name not in path.read_text(encoding="utf-8")]; sys.exit("missing ComfyUI i2i_pro node sources: "+",".join(missing)) if missing else None'

RUN set -euo pipefail; \
    comfyui_dir="$(cat /opt/allbot-comfyui-dir)"; \
    if [ -d "${comfyui_dir}/models" ]; then \
      find "${comfyui_dir}/models" -type f \( \
        -name 'qwen_3_8b_fp8mixed.safetensors' -o \
        -name 'flux2-vae.safetensors' -o \
        -name 'DarkBeast-Klein9b-V2-BFS-FP8-ComfyUI.safetensors' -o \
        -name 'qwen_3_4b.safetensors' -o \
        -name 'ae.safetensors' -o \
        -name 'DarkBeastZ6-BlitZ-BF16-ComfyUI.safetensors' \
        \) -print -quit | \
        awk 'NF { print "Business model file unexpectedly present in image: " $0; exit 1 }'; \
    fi

COPY remote_workers/scripts/runpod_bootstrap_from_git.sh /opt/allbot/runpod_bootstrap_from_git.sh

RUN set -euo pipefail; \
    chmod +x /opt/allbot/runpod_bootstrap_from_git.sh

CMD ["bash", "/opt/allbot/runpod_bootstrap_from_git.sh"]
