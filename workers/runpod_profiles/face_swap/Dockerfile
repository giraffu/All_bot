ARG BASE_IMAGE=yanwk/comfyui-boot:cu128-slim
FROM ${BASE_IMAGE}

ARG COMFYUI_REPO=https://github.com/comfyanonymous/ComfyUI.git
ARG COMFYUI_REF=16cd8d8a8f5f16ce7e5f929fdba9f783990254ea
ARG COMFYUI_INSTALL_DIR=/opt/ComfyUI

LABEL org.opencontainers.image.title="AllBot face_swap ComfyUI profile"
LABEL org.opencontainers.image.description="Dedicated face_swap V2 runtime; models are synced from the external manifest."
LABEL allbot.runpod.profile="face_swap"
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
ENV PIP_NO_CACHE_DIR=1

RUN set -euo pipefail; \
    if command -v apt-get >/dev/null 2>&1; then \
      packages="ca-certificates curl ffmpeg findutils git openssh-server"; \
      if ! python3 -m pip --version >/dev/null 2>&1; then packages="${packages} python3-pip"; fi; \
      apt-get update; \
      DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ${packages}; \
      rm -rf /var/lib/apt/lists/*; \
    elif command -v zypper >/dev/null 2>&1; then \
      packages="ca-certificates curl ffmpeg findutils git openssh"; \
      if ! python3 -m pip --version >/dev/null 2>&1; then packages="${packages} python3-pip"; fi; \
      zypper --non-interactive --gpg-auto-import-keys install --no-recommends ${packages}; \
      zypper clean --all; \
    fi

RUN set -euo pipefail; \
    comfyui_dir="${COMFYUI_INSTALL_DIR}"; \
    rm -rf "${comfyui_dir}"; \
    git config --global http.version HTTP/1.1; \
    for attempt in 1 2 3 4 5; do \
      git clone --filter=blob:none "${COMFYUI_REPO}" "${comfyui_dir}" && break; \
      rm -rf "${comfyui_dir}"; \
      if [ "$attempt" = "5" ]; then exit 128; fi; \
      sleep $((attempt * 3)); \
    done; \
    git -C "${comfyui_dir}" checkout --force "${COMFYUI_REF}"; \
    if [ -f "${comfyui_dir}/requirements.txt" ]; then \
      python3 -m pip install --no-cache-dir -r "${comfyui_dir}/requirements.txt"; \
    fi; \
    rm -rf "${comfyui_dir}/.git" /root/.cache/pip /tmp/* /var/tmp/*; \
    echo "${comfyui_dir}" > /opt/allbot-comfyui-dir

RUN set -euo pipefail; \
    comfyui_dir="$(cat /opt/allbot-comfyui-dir)"; \
    test -f "${comfyui_dir}/main.py"; \
    python3 -c 'from pathlib import Path; import sys; root=Path("/opt/allbot-comfyui-dir").read_text().strip(); root=Path(root); checks={root/"nodes.py":("UNETLoader","CLIPLoader","VAELoader"),root/"comfy_extras"/"nodes_custom_sampler.py":("SamplerCustomAdvanced",),root/"comfy_extras"/"nodes_edit_model.py":("ReferenceLatent",),root/"comfy_extras"/"nodes_flux.py":("EmptyFlux2LatentImage","Flux2Scheduler")}; missing=[]; [missing.append(f"{path}:{name}") for path,names in checks.items() for name in names if name not in path.read_text(encoding="utf-8")]; sys.exit("missing face_swap V2 node sources: "+",".join(missing)) if missing else None'

RUN set -euo pipefail; \
    comfyui_dir="$(cat /opt/allbot-comfyui-dir)"; \
    if [ -d "${comfyui_dir}/models" ]; then \
      find "${comfyui_dir}/models" -type f \( \
        -name 'qwen_3_8b_fp8mixed.safetensors' -o \
        -name 'DarkBeast-Klein9b-V2-BFS-FP8-ComfyUI.safetensors' -o \
        -name 'flux2-vae.safetensors' \
      \) -print -quit | \
      awk 'NF { print "Business model file unexpectedly present in image: " $0; exit 1 }'; \
    fi

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
    PYTHONPATH=/opt/allbot/runtime/runpod_worker python3 -c 'from comfy_agent.workflow_task_patchers import TASK_SPECIFIC_PATCHERS; from shared.character_reference_sheet import compose_ingredients_character_panel; assert callable(compose_ingredients_character_panel)'

ENV ALLBOT_RUNPOD_REPO_DIR=/opt/allbot/runtime \
    ALLBOT_RUNPOD_WORKER_DIR=/opt/allbot/runtime/runpod_worker
CMD ["bash", "/opt/allbot/runpod_baked_runtime_entrypoint.sh"]
