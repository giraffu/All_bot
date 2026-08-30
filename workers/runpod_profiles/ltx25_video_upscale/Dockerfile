ARG BASE_IMAGE=yanwk/comfyui-boot:cu128-slim@sha256:4172d960fe57c630d33f6bd8891aa7ecf55e7768559565c6b74e8d57e44512a9
ARG NODE_SOURCE_IMAGE=ghcr.io/giraffu/allbot-comfy-runpod-wan22-aio-video@sha256:5f959c7936e6ce271cbbb0d595993b48c4e408d6aded9476de949493d76400b4

FROM ${NODE_SOURCE_IMAGE} AS node_source
FROM ${BASE_IMAGE}

ARG COMFYUI_REPO=https://github.com/comfyanonymous/ComfyUI.git
ARG COMFYUI_REF=8a33128f2f8c5585c57486c07de481241e70a39c
ARG LTXVIDEO_REPO=https://github.com/Lightricks/ComfyUI-LTXVideo.git
ARG LTXVIDEO_REF=15d09abb5a187a8dcaea2fc31fe51ee96e6c9d0d
ARG COMFYUI_INSTALL_DIR=/opt/ComfyUI
ARG ALLBOT_GIT_SHA
ARG ALLBOT_RUNTIME_PACKAGE_SHA256
ARG ALLBOT_WORKFLOW_MAPPING_SHA256

LABEL org.opencontainers.image.title="AllBot LTX-2.5 IC V2V 2x video upscaler"
LABEL org.opencontainers.image.description="Model-free LTX-2.5 pixel-spatial IC-LoRA runtime"
LABEL allbot.runpod.profile="ltx25_video_upscale"
LABEL allbot.runpod.models="external-content-addressed-manifest"
LABEL org.opencontainers.image.revision=$ALLBOT_GIT_SHA

ENV ALLBOT_GIT_SHA=$ALLBOT_GIT_SHA \
    ALLBOT_RUNTIME_PACKAGE_SHA256=$ALLBOT_RUNTIME_PACKAGE_SHA256 \
    ALLBOT_WORKFLOW_MAPPING_SHA256=$ALLBOT_WORKFLOW_MAPPING_SHA256 \
    PIP_NO_CACHE_DIR=1
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN set -euo pipefail; \
    command -v ffmpeg >/dev/null; \
    command -v ffprobe >/dev/null; \
    command -v git >/dev/null; \
    comfyui_dir="${COMFYUI_INSTALL_DIR}"; \
    rm -rf "${comfyui_dir}"; mkdir -p "${comfyui_dir}"; \
    git -C "${comfyui_dir}" init; \
    git -C "${comfyui_dir}" remote add origin "${COMFYUI_REPO}"; \
    git -C "${comfyui_dir}" fetch --depth 1 --filter=blob:none origin "${COMFYUI_REF}"; \
    git -C "${comfyui_dir}" checkout --force FETCH_HEAD; \
    test "$(git -C "${comfyui_dir}" rev-parse HEAD)" = "${COMFYUI_REF}"; \
    python3 -m pip install -r "${comfyui_dir}/requirements.txt"; \
    rm -rf "${comfyui_dir}/.git"; \
    mkdir -p "${comfyui_dir}/custom_nodes"; \
    echo "${comfyui_dir}" > /opt/allbot-comfyui-dir

COPY --from=node_source /default-comfyui-bundle/ComfyUI/custom_nodes/ComfyUI-VideoHelperSuite /opt/allbot/node_source/ComfyUI-VideoHelperSuite
COPY workers/runpod_profiles/ltx_t2v/allbot_ltx_min_nodes /opt/allbot/allbot_ltx_min_nodes
RUN rm -rf /opt/allbot/runtime/runpod_worker
COPY workers/runpod_runtime /opt/allbot/runtime/runpod_worker
COPY workers/comfy_agent /opt/allbot/runtime/runpod_worker/comfy_agent
COPY src /opt/allbot/runtime/runpod_worker/src
COPY shared /opt/allbot/runtime/runpod_worker/shared
COPY workers/runpod_runtime/scripts/runpod_bootstrap_from_git.sh /opt/allbot/runpod_bootstrap_from_git.sh
COPY workers/runpod_runtime/scripts/runpod_baked_runtime_entrypoint.sh /opt/allbot/runpod_baked_runtime_entrypoint.sh

RUN set -euo pipefail; \
    test -n "$ALLBOT_GIT_SHA"; \
    test -n "$ALLBOT_RUNTIME_PACKAGE_SHA256"; \
    test -n "$ALLBOT_WORKFLOW_MAPPING_SHA256"; \
    comfyui_dir="$(cat /opt/allbot-comfyui-dir)"; \
    cp -a /opt/allbot/node_source/ComfyUI-VideoHelperSuite "${comfyui_dir}/custom_nodes/ComfyUI-VideoHelperSuite"; \
    cp -a /opt/allbot/allbot_ltx_min_nodes "${comfyui_dir}/custom_nodes/allbot_ltx_min_nodes"; \
    ltxvideo_dir="${comfyui_dir}/custom_nodes/ComfyUI-LTXVideo"; \
    mkdir -p "${ltxvideo_dir}"; git -C "${ltxvideo_dir}" init; \
    git -C "${ltxvideo_dir}" remote add origin "${LTXVIDEO_REPO}"; \
    git -C "${ltxvideo_dir}" fetch --depth 1 --filter=blob:none origin "${LTXVIDEO_REF}"; \
    git -C "${ltxvideo_dir}" checkout --force FETCH_HEAD; \
    test "$(git -C "${ltxvideo_dir}" rev-parse HEAD)" = "${LTXVIDEO_REF}"; \
    python3 -m pip install -r "${ltxvideo_dir}/requirements.txt"; \
    python3 -m pip install --no-cache-dir -r /opt/allbot/runtime/runpod_worker/requirements.txt minio packaging; \
    PYTHONPATH=/opt/allbot/runtime/runpod_worker python3 -c 'from comfy_agent.runtime_manifest import load_runtime_manifest; load_runtime_manifest()'; \
    PYTHONPATH=/opt/allbot/runtime/runpod_worker python3 -c 'from comfy_agent.workflow_task_patchers import TASK_SPECIFIC_PATCHERS as p; from shared.character_reference_sheet import compose_ingredients_character_panel; assert callable(compose_ingredients_character_panel); assert "ltx25_video_upscale" in p'; \
    COMFYUI_DIR="${comfyui_dir}" LTXVIDEO_NODE_DIR="${ltxvideo_dir}" PYTHONPATH="${comfyui_dir}:${PYTHONPATH:-}" python3 -c 'import importlib.util,os,sys; from pathlib import Path; import comfy.cli_args; comfy.cli_args.args.cpu=True; d=Path(os.environ["LTXVIDEO_NODE_DIR"]); s=importlib.util.spec_from_file_location("allbot_ltxvideo",d/"__init__.py",submodule_search_locations=[str(d)]); m=importlib.util.module_from_spec(s); sys.modules[s.name]=m; s.loader.exec_module(m); expected={"LTXICLoRALoaderModelOnly","LTXAddVideoICLoRAGuide"}; assert expected <= set(m.NODE_CLASS_MAPPINGS)'; \
    python3 -c 'import json; from pathlib import Path; p=Path("/opt/allbot/runtime/runpod_worker/comfy_agent/workflows/LTX 2.5 IC V2V Upscale.api.json"); data=json.loads(p.read_text()); assert data["5004:5606"]["inputs"]["strength_model"] == 1'; \
    if find "${comfyui_dir}/models" -type f -name '*.safetensors' -print -quit | grep -q .; then echo "models must not be baked into image" >&2; exit 1; fi; \
    chmod +x /opt/allbot/runpod_bootstrap_from_git.sh /opt/allbot/runpod_baked_runtime_entrypoint.sh; \
    test -x /opt/allbot/runpod_bootstrap_from_git.sh; \
    rm -rf /root/.cache/pip /tmp/* /var/tmp/*

ENV ALLBOT_RUNPOD_REPO_DIR=/opt/allbot/runtime \
    ALLBOT_RUNPOD_WORKER_DIR=/opt/allbot/runtime/runpod_worker
CMD ["bash", "/opt/allbot/runpod_baked_runtime_entrypoint.sh"]
