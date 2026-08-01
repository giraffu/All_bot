ARG BASE_IMAGE=yanwk/comfyui-boot:cu128-slim
ARG NODE_SOURCE_IMAGE=ghcr.io/giraffu/allbot-comfy-runpod-wan22-aio-video:20260619-wan22aio-rife-bcf3ebd

FROM ${NODE_SOURCE_IMAGE} AS node_source
FROM ${BASE_IMAGE}

ARG COMFYUI_REPO=https://github.com/comfyanonymous/ComfyUI.git
ARG COMFYUI_REF=7bf8bfcd078c7f4ae50ca5149c9ff7d8613e1fb1
ARG LTXVIDEO_REPO=https://github.com/Lightricks/ComfyUI-LTXVideo.git
ARG LTXVIDEO_REF=aceeae9635f6d493f2893ba3c411a1c36031788a
ARG COMFYUI_INSTALL_DIR=/opt/ComfyUI
ARG SAGEATTENTION_VERSION=1.0.6

LABEL org.opencontainers.image.title="AllBot LTX 2.3 Sulphur T2V + Ingredients profile"
LABEL org.opencontainers.image.description="LTX 2.3 T2V/IC runtime; all model files stay in the external LAN manifest."
LABEL allbot.runpod.profile="ltx_t2v"
LABEL allbot.runpod.models="external-lan-manifest"
LABEL allbot.runpod.scope="ltx-t2v-and-ingredients-only"
ARG ALLBOT_GIT_SHA
LABEL org.opencontainers.image.revision=$ALLBOT_GIT_SHA \
      io.allbot.runpod.agent-revision=$ALLBOT_GIT_SHA \
      io.allbot.runpod.workflow-revision=$ALLBOT_GIT_SHA

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ENV PIP_NO_CACHE_DIR=1

RUN set -euo pipefail; \
    command -v curl >/dev/null; \
    command -v ffmpeg >/dev/null; \
    command -v ffprobe >/dev/null; \
    command -v git >/dev/null; \
    command -v python3 >/dev/null; \
    python3 -m pip --version >/dev/null

RUN set -euo pipefail; \
    comfyui_dir="${COMFYUI_INSTALL_DIR}"; \
    rm -rf "${comfyui_dir}"; \
    mkdir -p "${comfyui_dir}"; \
    git -C "${comfyui_dir}" init; \
    git -C "${comfyui_dir}" remote add origin "${COMFYUI_REPO}"; \
    for attempt in 1 2 3 4 5; do \
      git -C "${comfyui_dir}" fetch --depth 1 --filter=blob:none origin "${COMFYUI_REF}" && break; \
      if [ "$attempt" = "5" ]; then \
        echo "Failed to fetch pinned ComfyUI after ${attempt} attempts" >&2; \
        exit 128; \
      fi; \
      sleep $((attempt * 3)); \
    done; \
    git -C "${comfyui_dir}" checkout --force FETCH_HEAD; \
    test "$(git -C "${comfyui_dir}" rev-parse HEAD)" = "${COMFYUI_REF}"; \
    python3 -m pip install --no-cache-dir -r "${comfyui_dir}/requirements.txt"; \
    rm -rf "${comfyui_dir}/.git"; \
    mkdir -p "${comfyui_dir}/custom_nodes"; \
    echo "${comfyui_dir}" > /opt/allbot-comfyui-dir

COPY --from=node_source /default-comfyui-bundle/ComfyUI/custom_nodes/ComfyUI-KJNodes /opt/allbot/node_source/ComfyUI-KJNodes
COPY --from=node_source /default-comfyui-bundle/ComfyUI/custom_nodes/ComfyUI-VideoHelperSuite /opt/allbot/node_source/ComfyUI-VideoHelperSuite
COPY --from=node_source /default-comfyui-bundle/ComfyUI/custom_nodes/rgthree-comfy /opt/allbot/node_source/rgthree-comfy
COPY workers/runpod_profiles/ltx_t2v/allbot_ltx_min_nodes /opt/allbot/allbot_ltx_min_nodes
COPY workers/runpod_runtime /opt/allbot/runtime/runpod_worker
COPY workers/runpod_runtime/scripts/runpod_bootstrap_from_git.sh /opt/allbot/runpod_bootstrap_from_git.sh
COPY workers/runpod_runtime/scripts/runpod_baked_runtime_entrypoint.sh /opt/allbot/runpod_baked_runtime_entrypoint.sh
COPY workers/runpod_runtime/requirements.txt /opt/allbot/runpod_worker/requirements.txt

RUN set -euo pipefail; \
    comfyui_dir="$(cat /opt/allbot-comfyui-dir)"; \
    test -f "${comfyui_dir}/main.py"; \
    for node_name in \
      ComfyUI-KJNodes \
      ComfyUI-VideoHelperSuite \
      rgthree-comfy; do \
      test -d "/opt/allbot/node_source/${node_name}"; \
      rm -rf "${comfyui_dir}/custom_nodes/${node_name}"; \
      cp -a "/opt/allbot/node_source/${node_name}" "${comfyui_dir}/custom_nodes/${node_name}"; \
      if [ -f "${comfyui_dir}/custom_nodes/${node_name}/requirements.txt" ]; then \
        python3 -m pip install --no-cache-dir -r "${comfyui_dir}/custom_nodes/${node_name}/requirements.txt"; \
      fi; \
    done; \
    rm -rf "${comfyui_dir}/custom_nodes/allbot_ltx_min_nodes"; \
    cp -a /opt/allbot/allbot_ltx_min_nodes "${comfyui_dir}/custom_nodes/allbot_ltx_min_nodes"; \
    ltxvideo_dir="${comfyui_dir}/custom_nodes/ComfyUI-LTXVideo"; \
    rm -rf "${ltxvideo_dir}"; \
    mkdir -p "${ltxvideo_dir}"; \
    git -C "${ltxvideo_dir}" init; \
    git -C "${ltxvideo_dir}" remote add origin "${LTXVIDEO_REPO}"; \
    git -C "${ltxvideo_dir}" fetch --depth 1 --filter=blob:none origin "${LTXVIDEO_REF}"; \
    git -C "${ltxvideo_dir}" checkout --force FETCH_HEAD; \
    test "$(git -C "${ltxvideo_dir}" rev-parse HEAD)" = "${LTXVIDEO_REF}"; \
    python3 -m pip install --no-cache-dir -r "${ltxvideo_dir}/requirements.txt"; \
    rm -rf "${ltxvideo_dir}/.git"; \
    COMFYUI_DIR="${comfyui_dir}" LTXVIDEO_NODE_DIR="${ltxvideo_dir}" PYTHONPATH="${comfyui_dir}:${PYTHONPATH:-}" python3 -c 'import importlib.util, os, sys; from pathlib import Path; import comfy.cli_args; comfy.cli_args.args.cpu=True; root = Path(os.environ["COMFYUI_DIR"]); node_dir = Path(os.environ["LTXVIDEO_NODE_DIR"]); spec = importlib.util.spec_from_file_location("allbot_ltxvideo_smoke", node_dir / "__init__.py", submodule_search_locations=[str(node_dir)]); module = importlib.util.module_from_spec(spec); assert spec.loader is not None; sys.modules[spec.name] = module; spec.loader.exec_module(module); expected={"LTXICLoRALoaderModelOnly","LTXAddVideoICLoRAGuide"}; assert expected <= set(module.NODE_CLASS_MAPPINGS), expected-set(module.NODE_CLASS_MAPPINGS); core_text = (root / "comfy_extras" / "nodes_lt.py").read_text(encoding="utf-8"); audio_text = (root / "comfy_extras" / "nodes_lt_audio.py").read_text(encoding="utf-8"); assert "LTXVScheduler" in core_text and "LTXVConditioning" in core_text and "LTXVEmptyLatentAudio" in audio_text; kj_text = (root / "custom_nodes" / "ComfyUI-KJNodes" / "__init__.py").read_text(encoding="utf-8"); assert "DiffusionModelLoaderKJ" in kj_text and "VAELoaderKJ" in kj_text'; \
    LTX_MIN_NODE_DIR="${comfyui_dir}/custom_nodes/allbot_ltx_min_nodes" python3 -c 'import importlib.util, os; from pathlib import Path; spec = importlib.util.spec_from_file_location("allbot_ltx_min_nodes_smoke", Path(os.environ["LTX_MIN_NODE_DIR"]) / "__init__.py"); module = importlib.util.module_from_spec(spec); assert spec.loader is not None; spec.loader.exec_module(module); expected = {"ImpactDummyInput", "TwoWaySwitch", "easy int", "mxSlider", "RAMCleanup", "VRAMCleanup", "Float", "IntToFloat", "Sigmas Sigmoid", "MathExpression|pysssss", "AllBotLTXCropGuideLatentsExact"}; assert expected <= set(module.NODE_CLASS_MAPPINGS)'; \
    chmod +x /opt/allbot/runpod_bootstrap_from_git.sh /opt/allbot/runpod_baked_runtime_entrypoint.sh; \
    python3 -m pip install --no-cache-dir -r /opt/allbot/runpod_worker/requirements.txt; \
    python3 -m pip install --no-cache-dir minio packaging "sageattention==${SAGEATTENTION_VERSION}"; \
    python3 -c 'import fastapi, minio, uvicorn, websockets; from sageattention import sageattn; assert callable(sageattn)'; \
    PYTHONPATH=/opt/allbot/runtime/runpod_worker python3 -c 'from comfy_agent.workflow_task_patchers import TASK_SPECIFIC_PATCHERS as p; assert {"ltx_t2v","ltx_t2v_ic"} <= set(p)'; \
    python3 -c 'import json; from pathlib import Path; root=Path("/opt/allbot/runtime/runpod_worker/comfy_agent/workflows"); expected={"LTX 2.3 Sulphur T2V.json","LTX 2.3 Sulphur Ingredients T2V.json"}; assert all((root/name).is_file() and isinstance(json.loads((root/name).read_text()),dict) for name in expected)'; \
    if find "${comfyui_dir}/models" -type f -name "*.safetensors" -print -quit | grep -q .; then \
      echo "LTX model files must stay out of the profile image" >&2; \
      exit 1; \
    fi; \
    find "${comfyui_dir}" -type d -name __pycache__ -prune -exec rm -rf {} +; \
    python3 -m pip cache purge >/dev/null 2>&1 || true; \
    rm -rf /root/.cache/pip /tmp/* /var/tmp/*

ENV ALLBOT_RUNPOD_REPO_DIR=/opt/allbot/runtime \
    ALLBOT_RUNPOD_WORKER_DIR=/opt/allbot/runtime/runpod_worker
CMD ["bash", "/opt/allbot/runpod_baked_runtime_entrypoint.sh"]
