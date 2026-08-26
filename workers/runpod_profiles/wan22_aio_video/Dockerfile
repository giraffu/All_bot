ARG BASE_IMAGE=yanwk/comfyui-boot:cu128-slim@sha256:4172d960fe57c630d33f6bd8891aa7ecf55e7768559565c6b74e8d57e44512a9
FROM ${BASE_IMAGE}

ARG COMFYUI_REPO=https://github.com/comfyanonymous/ComfyUI.git
ARG COMFYUI_REF=master
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
ARG RIFE49_URL=https://huggingface.co/lividtm/RIFE/resolve/main/rife49.pth
ARG RIFE49_SHA256=e55fd00f3cc184e3c65961f4bb827a9da022e78eed36b055242c0ac30000d533
ARG GGUF_REPO=https://github.com/city96/ComfyUI-GGUF.git
ARG GGUF_REF=main
ARG DASIWA_REPO=https://github.com/darksidewalker/ComfyUI-DaSiWa-Nodes.git
ARG DASIWA_REF=main
ARG WHITERABBIT_REPO=https://github.com/Artificial-Sweetener/comfyui-WhiteRabbit.git
ARG WHITERABBIT_REF=4815da41473c99400da6ca4127f0e324dbfd865a
ARG REUSE_BASE_CUSTOM_NODES=false

LABEL org.opencontainers.image.title="AllBot RunPod wan22_aio_video ComfyUI profile"
LABEL org.opencontainers.image.description="ComfyUI runtime profile with Wan22 AIO custom nodes baked in; model files are synced from R2 at Pod startup."
LABEL allbot.runpod.profile="wan22_aio_video"
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
      packages="ca-certificates curl ffmpeg git openssh-server"; \
      if ! python3 -m pip --version >/dev/null 2>&1; then \
        packages="${packages} python3-pip"; \
      fi; \
      apt-get update; \
      DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ${packages}; \
      rm -rf /var/lib/apt/lists/*; \
    fi

RUN set -euo pipefail; \
    find_comfyui_dir() { \
      for candidate in \
        /default-comfyui-bundle/ComfyUI \
        /workspace/ComfyUI \
        /root/ComfyUI \
        "${COMFYUI_INSTALL_DIR}"; do \
        if [ -f "${candidate}/main.py" ]; then \
          printf '%s\n' "${candidate}"; \
          return 0; \
        fi; \
      done; \
      return 1; \
    }; \
    if comfyui_dir="$(find_comfyui_dir)"; then \
      echo "Using existing ComfyUI at ${comfyui_dir}"; \
    else \
      comfyui_dir="${COMFYUI_INSTALL_DIR}"; \
      rm -rf "${comfyui_dir}"; \
      git clone --filter=blob:none "${COMFYUI_REPO}" "${comfyui_dir}"; \
      git -C "${comfyui_dir}" checkout --force "${COMFYUI_REF}"; \
      if [ -f "${comfyui_dir}/requirements.txt" ]; then \
        python3 -m pip install --no-cache-dir -r "${comfyui_dir}/requirements.txt"; \
      fi; \
      rm -rf "${comfyui_dir}/.git"; \
    fi; \
    mkdir -p "${comfyui_dir}/custom_nodes"; \
    git config --global http.version HTTP/1.1; \
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
    require_existing_node() { \
      local node_name="$1"; \
      if [ ! -d "${comfyui_dir}/custom_nodes/${node_name}" ]; then \
        echo "REUSE_BASE_CUSTOM_NODES=true but ${node_name} is missing from ${comfyui_dir}/custom_nodes" >&2; \
        exit 75; \
      fi; \
    }; \
    if [ "${REUSE_BASE_CUSTOM_NODES}" = "true" ]; then \
      echo "Reusing baked custom nodes from base image"; \
      require_existing_node "ComfyUI-KJNodes"; \
      require_existing_node "ComfyUI-VideoHelperSuite"; \
      require_existing_node "rgthree-comfy"; \
      require_existing_node "ComfyUI-Frame-Interpolation"; \
      require_existing_node "ComfyUI_Fill-Nodes"; \
      require_existing_node "ComfyUI-GGUF"; \
      require_existing_node "ComfyUI-DaSiWa-Nodes"; \
      require_existing_node "comfyui-WhiteRabbit"; \
      require_existing_node "ComfyUI-LTXVideo"; \
      python3 -c 'import importlib.util, sys; missing = [name for name in ("packaging", "torchlanc") if importlib.util.find_spec(name) is None]; sys.exit("REUSE_BASE_CUSTOM_NODES=true but missing Python package(s): " + ",".join(missing) if missing else 0)'; \
    else \
      clone_node "${KJNODES_REPO}" "${KJNODES_REF}" "${comfyui_dir}/custom_nodes/ComfyUI-KJNodes"; \
      clone_node "${VIDEOHELPERSUITE_REPO}" "${VIDEOHELPERSUITE_REF}" "${comfyui_dir}/custom_nodes/ComfyUI-VideoHelperSuite"; \
      clone_node "${RGTHREE_REPO}" "${RGTHREE_REF}" "${comfyui_dir}/custom_nodes/rgthree-comfy"; \
      clone_node "${FRAME_INTERPOLATION_REPO}" "${FRAME_INTERPOLATION_REF}" "${comfyui_dir}/custom_nodes/ComfyUI-Frame-Interpolation"; \
      clone_node "${GGUF_REPO}" "${GGUF_REF}" "${comfyui_dir}/custom_nodes/ComfyUI-GGUF"; \
      clone_node "${DASIWA_REPO}" "${DASIWA_REF}" "${comfyui_dir}/custom_nodes/ComfyUI-DaSiWa-Nodes"; \
      clone_node "${WHITERABBIT_REPO}" "${WHITERABBIT_REF}" "${comfyui_dir}/custom_nodes/comfyui-WhiteRabbit"; \
      python3 -m pip install --no-cache-dir packaging torchlanc; \
    fi; \
    if [ -d "${comfyui_dir}/models" ]; then \
      find "${comfyui_dir}/models" -type f \( \
        -name 'wan22EnhancedNSFWSVICamera_nsfwFASTMOVEV2FP8H.safetensors' -o \
        -name 'wan22EnhancedNSFWSVICamera_nsfwFASTMOVEV2FP8L.safetensors' -o \
        -name 'DasiwaWAN22I2V14BLightspeed_snatchkissHighV11.safetensors' -o \
        -name 'DasiwaWAN22I2V14BLightspeed_snatchkissLowV11.safetensors' -o \
        -path '*/loras/*_high_noise.safetensors' -o \
        -path '*/loras/*_low_noise.safetensors' \
        \) -print -quit | \
        awk 'NF { print "Business model file unexpectedly present in image: " $0; exit 1 }'; \
    fi; \
    find "${comfyui_dir}" -type d -name __pycache__ -prune -exec rm -rf {} +; \
    python3 -m pip cache purge >/dev/null 2>&1 || true; \
    rm -rf /root/.cache/pip /tmp/* /var/tmp/*; \
    echo "${comfyui_dir}" > /opt/allbot-comfyui-dir

# Keep the FL_RIFE provider in a final small layer so Wan22 node fixes do not
# invalidate the heavier baked custom-node layer.
RUN set -euo pipefail; \
    if [ -s /opt/allbot-comfyui-dir ]; then \
      comfyui_dir="$(cat /opt/allbot-comfyui-dir)"; \
    elif [ -f /default-comfyui-bundle/ComfyUI/main.py ]; then \
      comfyui_dir=/default-comfyui-bundle/ComfyUI; \
    elif [ -f /workspace/ComfyUI/main.py ]; then \
      comfyui_dir=/workspace/ComfyUI; \
    elif [ -f /root/ComfyUI/main.py ]; then \
      comfyui_dir=/root/ComfyUI; \
    else \
      comfyui_dir="${COMFYUI_INSTALL_DIR}"; \
    fi; \
    test -f "${comfyui_dir}/main.py"; \
    mkdir -p "${comfyui_dir}/custom_nodes"; \
    target="${comfyui_dir}/custom_nodes/ComfyUI_Fill-Nodes"; \
    if [ "${REUSE_BASE_CUSTOM_NODES}" = "true" ]; then \
      test -d "${target}" || { echo "REUSE_BASE_CUSTOM_NODES=true but ComfyUI_Fill-Nodes is missing" >&2; exit 75; }; \
      echo "Reusing baked ComfyUI_Fill-Nodes from base image"; \
    else \
      rm -rf "${target}"; \
      git config --global http.version HTTP/1.1; \
      for attempt in 1 2 3 4 5; do \
        git clone --filter=blob:none "${FILL_NODES_REPO}" "${target}" && break; \
        rm -rf "${target}"; \
        if [ "$attempt" = "5" ]; then \
          echo "Failed to clone ${FILL_NODES_REPO} after ${attempt} attempts" >&2; \
          exit 128; \
        fi; \
        sleep $((attempt * 3)); \
      done; \
      git -C "${target}" checkout --force "${FILL_NODES_REF}"; \
    fi; \
    if [ "${REUSE_BASE_CUSTOM_NODES}" != "true" ] && [ -f "${target}/requirements.txt" ]; then \
      python3 -m pip install --no-cache-dir -r "${target}/requirements.txt"; \
    fi; \
    if [ "${REUSE_BASE_CUSTOM_NODES}" != "true" ]; then rm -rf "${target}/.git"; fi; \
    find "${target}" -type d -name __pycache__ -prune -exec rm -rf {} +; \
    python3 -m pip cache purge >/dev/null 2>&1 || true; \
    rm -rf /root/.cache/pip /tmp/* /var/tmp/*

RUN set -euo pipefail; \
    if [ -s /opt/allbot-comfyui-dir ]; then \
      comfyui_dir="$(cat /opt/allbot-comfyui-dir)"; \
    elif [ -f /default-comfyui-bundle/ComfyUI/main.py ]; then \
      comfyui_dir=/default-comfyui-bundle/ComfyUI; \
    elif [ -f /workspace/ComfyUI/main.py ]; then \
      comfyui_dir=/workspace/ComfyUI; \
    elif [ -f /root/ComfyUI/main.py ]; then \
      comfyui_dir=/root/ComfyUI; \
    else \
      comfyui_dir="${COMFYUI_INSTALL_DIR}"; \
    fi; \
    test -f "${comfyui_dir}/main.py"; \
    tmp="/tmp/allbot-rife49.pth"; \
    curl -fsSL --retry 5 --retry-delay 3 "${RIFE49_URL}" -o "${tmp}"; \
    printf '%s  %s\n' "${RIFE49_SHA256}" "${tmp}" | sha256sum -c -; \
    for dst in \
      "${comfyui_dir}/custom_nodes/ComfyUI_Fill-Nodes/nodes/cache/rife_models/rife49.pth" \
      "${comfyui_dir}/custom_nodes/ComfyUI-Frame-Interpolation/ckpts/rife/rife49.pth"; do \
      mkdir -p "$(dirname "${dst}")"; \
      cp "${tmp}" "${dst}"; \
      chmod 0644 "${dst}"; \
    done; \
    rm -f "${tmp}"

ARG LTXVIDEO_REPO=https://github.com/Lightricks/ComfyUI-LTXVideo.git
ARG LTXVIDEO_REF=229437c6b65796d6a7a63ae34be2bd5ba31fa543

# Wan22AioV82 uses LTXVSpatioTemporalTiledVAEDecode for video VAE decode.
RUN set -euo pipefail; \
    if [ -s /opt/allbot-comfyui-dir ]; then \
      comfyui_dir="$(cat /opt/allbot-comfyui-dir)"; \
    elif [ -f /default-comfyui-bundle/ComfyUI/main.py ]; then \
      comfyui_dir=/default-comfyui-bundle/ComfyUI; \
    elif [ -f /workspace/ComfyUI/main.py ]; then \
      comfyui_dir=/workspace/ComfyUI; \
    elif [ -f /root/ComfyUI/main.py ]; then \
      comfyui_dir=/root/ComfyUI; \
    else \
      comfyui_dir="${COMFYUI_INSTALL_DIR}"; \
    fi; \
    test -f "${comfyui_dir}/main.py"; \
    mkdir -p "${comfyui_dir}/custom_nodes"; \
    target="${comfyui_dir}/custom_nodes/ComfyUI-LTXVideo"; \
    if [ "${REUSE_BASE_CUSTOM_NODES}" = "true" ]; then \
      test -d "${target}" || { echo "REUSE_BASE_CUSTOM_NODES=true but ComfyUI-LTXVideo is missing" >&2; exit 75; }; \
      echo "Reusing baked ComfyUI-LTXVideo from base image"; \
    else \
      rm -rf "${target}"; \
      git config --global http.version HTTP/1.1; \
      for attempt in 1 2 3 4 5; do \
        git clone --filter=blob:none "${LTXVIDEO_REPO}" "${target}" && break; \
        rm -rf "${target}"; \
        if [ "$attempt" = "5" ]; then \
          echo "Failed to clone ${LTXVIDEO_REPO} after ${attempt} attempts" >&2; \
          exit 128; \
        fi; \
        sleep $((attempt * 3)); \
      done; \
      git -C "${target}" checkout --force "${LTXVIDEO_REF}"; \
    fi; \
    printf '%s\n' \
      'from .tiled_vae_decode import LTXVTiledVAEDecode, LTXVSpatioTemporalTiledVAEDecode  # noqa: F401' \
      'from .nodes_registry import NODE_CLASS_MAPPINGS as RUNTIME_NODE_CLASS_MAPPINGS' \
      'from .nodes_registry import NODE_DISPLAY_NAME_MAPPINGS as RUNTIME_NODE_DISPLAY_NAME_MAPPINGS' \
      '' \
      'NODE_CLASS_MAPPINGS = dict(RUNTIME_NODE_CLASS_MAPPINGS)' \
      'NODE_DISPLAY_NAME_MAPPINGS = dict(RUNTIME_NODE_DISPLAY_NAME_MAPPINGS)' \
      'WEB_DIRECTORY = "./web"' \
      '' \
      '__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]' \
      > "${target}/__init__.py"; \
    grep -R "LTXVSpatioTemporalTiledVAEDecode" "${target}" >/dev/null; \
    LTXVIDEO_NODE_DIR="${target}" PYTHONPATH="${comfyui_dir}:${PYTHONPATH:-}" python3 -c 'import importlib.util, os, sys; from pathlib import Path; node_dir = Path(os.environ["LTXVIDEO_NODE_DIR"]); spec = importlib.util.spec_from_file_location("allbot_ltxvideo_smoke", node_dir / "__init__.py", submodule_search_locations=[str(node_dir)]); module = importlib.util.module_from_spec(spec); assert spec.loader is not None; sys.modules[spec.name] = module; spec.loader.exec_module(module); assert "LTXVSpatioTemporalTiledVAEDecode" in module.NODE_CLASS_MAPPINGS'; \
    if [ "${REUSE_BASE_CUSTOM_NODES}" != "true" ]; then rm -rf "${target}/.git"; fi; \
    find "${target}" -type d -name __pycache__ -prune -exec rm -rf {} +; \
    python3 -m pip cache purge >/dev/null 2>&1 || true; \
    rm -rf /root/.cache/pip /tmp/* /var/tmp/*

RUN rm -rf /opt/allbot/runtime/runpod_worker
COPY workers/runpod_runtime /opt/allbot/runtime/runpod_worker
COPY workers/comfy_agent /opt/allbot/runtime/runpod_worker/comfy_agent
COPY src /opt/allbot/runtime/runpod_worker/src
RUN test -n "$ALLBOT_GIT_SHA" && \
    test -n "$ALLBOT_RUNTIME_PACKAGE_SHA256" && \
    test -n "$ALLBOT_WORKFLOW_MAPPING_SHA256" && \
    PYTHONPATH=/opt/allbot/runtime/runpod_worker python3 -c 'from comfy_agent.runtime_manifest import load_runtime_manifest; load_runtime_manifest()'
COPY shared /opt/allbot/runtime/runpod_worker/shared
RUN python3 -m pip install --no-cache-dir -r /opt/allbot/runtime/runpod_worker/requirements.txt
COPY workers/runpod_runtime/scripts/runpod_bootstrap_from_git.sh /opt/allbot/runpod_bootstrap_from_git.sh
COPY workers/runpod_runtime/scripts/runpod_baked_runtime_entrypoint.sh /opt/allbot/runpod_baked_runtime_entrypoint.sh

RUN set -euo pipefail; \
    chmod +x /opt/allbot/runpod_bootstrap_from_git.sh /opt/allbot/runpod_baked_runtime_entrypoint.sh; \
    PYTHONPATH=/opt/allbot/runtime/runpod_worker python3 -c 'from comfy_agent.workflow_task_patchers import TASK_SPECIFIC_PATCHERS; from shared.character_reference_sheet import compose_ingredients_character_panel; assert callable(compose_ingredients_character_panel)'

ENV ALLBOT_RUNPOD_REPO_DIR=/opt/allbot/runtime \
    ALLBOT_RUNPOD_WORKER_DIR=/opt/allbot/runtime/runpod_worker
CMD ["bash", "/opt/allbot/runpod_baked_runtime_entrypoint.sh"]
