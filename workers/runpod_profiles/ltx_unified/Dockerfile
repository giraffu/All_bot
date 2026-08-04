ARG BASE_IMAGE=192.168.1.115:5000/allbot/comfy-runpod-ltx-t2v@sha256:9ed3de73923fc8f021716f7fc19d8d3e5f6ed552a8ee11cb849b3dfb293db043
FROM ${BASE_IMAGE}

LABEL org.opencontainers.image.title="AllBot unified LTX 2.3 profile"
LABEL org.opencontainers.image.description="LTX 2.3 I2V/FLF2V/V2V Audio/T2V/IC runtime; all model files stay in the external LAN manifest."
LABEL allbot.runpod.profile="ltx_unified"
LABEL allbot.runpod.models="external-lan-manifest"
LABEL allbot.runpod.scope="ltx-video-and-t2v"
ARG ALLBOT_GIT_SHA
ARG LICON_MSR_REVISION=94a52bfec735ff6f802c480f7fe8fdac1d279a7f
ARG KJNODES_REVISION=5fc6db6b39638a692f114c4bb5b6949f801b4efa
LABEL org.opencontainers.image.revision=$ALLBOT_GIT_SHA \
      io.allbot.runpod.agent-revision=$ALLBOT_GIT_SHA \
      io.allbot.runpod.workflow-revision=$ALLBOT_GIT_SHA

SHELL ["/bin/bash", "-o", "pipefail", "-c"]
ENV PIP_NO_CACHE_DIR=1

COPY workers/runpod_profiles/ltx_unified/allbot_ltx_min_nodes /opt/allbot/allbot_ltx_min_nodes
COPY workers/runpod_runtime /opt/allbot/runtime/runpod_worker
COPY shared /opt/allbot/runtime/runpod_worker/shared
COPY workers/runpod_runtime/scripts/runpod_bootstrap_from_git.sh /opt/allbot/runpod_bootstrap_from_git.sh
COPY workers/runpod_runtime/scripts/runpod_baked_runtime_entrypoint.sh /opt/allbot/runpod_baked_runtime_entrypoint.sh
COPY workers/runpod_runtime/requirements.txt /opt/allbot/runpod_worker/requirements.txt

RUN set -euo pipefail; \
    comfyui_dir="$(cat /opt/allbot-comfyui-dir)"; \
    test -f "${comfyui_dir}/main.py"; \
    test -d "${comfyui_dir}/custom_nodes/ComfyUI-LTXVideo"; \
    test -d "${comfyui_dir}/custom_nodes/ComfyUI-KJNodes"; \
    test -d "${comfyui_dir}/custom_nodes/ComfyUI-VideoHelperSuite"; \
    test -d "${comfyui_dir}/custom_nodes/rgthree-comfy"; \
    rm -rf "${comfyui_dir}/custom_nodes/ComfyUI-KJNodes"; \
    git clone https://github.com/kijai/ComfyUI-KJNodes.git \
      "${comfyui_dir}/custom_nodes/ComfyUI-KJNodes"; \
    git -C "${comfyui_dir}/custom_nodes/ComfyUI-KJNodes" checkout --detach \
      "${KJNODES_REVISION}"; \
    test "$(git -C "${comfyui_dir}/custom_nodes/ComfyUI-KJNodes" rev-parse HEAD)" = \
      "${KJNODES_REVISION}"; \
    python3 -m pip install --no-cache-dir -r \
      "${comfyui_dir}/custom_nodes/ComfyUI-KJNodes/requirements.txt"; \
    rm -rf "${comfyui_dir}/custom_nodes/ComfyUI-KJNodes/.git"; \
    git clone https://github.com/liconstudio/ComfyUI-Licon-MSR.git \
      "${comfyui_dir}/custom_nodes/ComfyUI-Licon-MSR"; \
    git -C "${comfyui_dir}/custom_nodes/ComfyUI-Licon-MSR" checkout --detach \
      "${LICON_MSR_REVISION}"; \
    test "$(git -C "${comfyui_dir}/custom_nodes/ComfyUI-Licon-MSR" rev-parse HEAD)" = \
      "${LICON_MSR_REVISION}"; \
    rm -rf "${comfyui_dir}/custom_nodes/ComfyUI-Licon-MSR/.git"; \
    rm -rf "${comfyui_dir}/custom_nodes/allbot_ltx_min_nodes"; \
    cp -a /opt/allbot/allbot_ltx_min_nodes "${comfyui_dir}/custom_nodes/allbot_ltx_min_nodes"; \
    chmod +x /opt/allbot/runpod_bootstrap_from_git.sh /opt/allbot/runpod_baked_runtime_entrypoint.sh; \
    python3 -m pip install --no-cache-dir -r /opt/allbot/runpod_worker/requirements.txt; \
    python3 -c 'import fastapi, minio, uvicorn, websockets; from sageattention import sageattn; assert callable(sageattn)'; \
    COMFYUI_DIR="${comfyui_dir}" PYTHONPATH="${comfyui_dir}:${PYTHONPATH:-}" python3 -c 'import importlib.util, os, sys; from pathlib import Path; import comfy.cli_args; comfy.cli_args.args.cpu=True; p=Path(os.environ["COMFYUI_DIR"])/"custom_nodes/ComfyUI-Licon-MSR"; s=importlib.util.spec_from_file_location("allbot_licon_msr",p/"__init__.py",submodule_search_locations=[str(p)]); m=importlib.util.module_from_spec(s); sys.modules[s.name]=m; s.loader.exec_module(m); assert "LiconMSR" in m.NODE_CLASS_MAPPINGS; ltx=Path(os.environ["COMFYUI_DIR"])/"custom_nodes/ComfyUI-LTXVideo"; q=importlib.util.spec_from_file_location("allbot_ltxvideo",ltx/"__init__.py",submodule_search_locations=[str(ltx)]); n=importlib.util.module_from_spec(q); sys.modules[q.name]=n; q.loader.exec_module(n); expected={"LTXICLoRALoaderModelOnly","LTXAddVideoICLoRAGuide"}; assert expected <= set(n.NODE_CLASS_MAPPINGS), expected-set(n.NODE_CLASS_MAPPINGS)'; \
    PYTHONPATH=/opt/allbot/runtime/runpod_worker python3 -c 'from comfy_agent.workflow_task_patchers import TASK_SPECIFIC_PATCHERS as p; from shared.character_reference_sheet import compose_ingredients_character_panel; assert {"ltx_video","ltx_video_flf2v","ltx_video_v2v_audio","ltx_t2v","ltx_t2v_ic"} <= set(p); assert callable(compose_ingredients_character_panel)'; \
    python3 -c 'import json; from pathlib import Path; root=Path("/opt/allbot/runtime/runpod_worker/comfy_agent/workflows"); expected={"LTX 2.3 I2V 10Eros LoRA.json","LTX 2.3 FLF2V 10Eros LoRA.json","LTX 2.3 V2V Audio 10Eros LoRA.json","LTX 2.3 Sulphur T2V.json","LTX 2.3 Sulphur Ingredients T2V.json"}; assert all((root/name).is_file() and isinstance(json.loads((root/name).read_text()),dict) for name in expected)'; \
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
