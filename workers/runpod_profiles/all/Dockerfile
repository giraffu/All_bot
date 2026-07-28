ARG BASE_IMAGE=yanwk/comfyui-boot:cu128-slim
ARG NODE_SOURCE_IMAGE=ghcr.io/giraffu/allbot-comfy-runpod-wan22-aio-video@sha256:c004db27771a8709b660732e4be4334a7fa6cfce7e3b6782b12301135d9ba57f

FROM ${NODE_SOURCE_IMAGE} AS node_source
FROM ${BASE_IMAGE}

ARG COMFYUI_REPO=https://github.com/comfyanonymous/ComfyUI.git
ARG COMFYUI_REF=7bf8bfcd078c7f4ae50ca5149c9ff7d8613e1fb1
ARG LTXVIDEO_REPO=https://github.com/Lightricks/ComfyUI-LTXVideo.git
ARG LTXVIDEO_REF=aceeae9635f6d493f2893ba3c411a1c36031788a
ARG COMFYUI_INSTALL_DIR=/opt/ComfyUI
ARG SAGEATTENTION_VERSION=1.0.6
ARG REUSE_BASE_CUSTOM_NODES=false
ARG ALLBOT_GIT_SHA

LABEL org.opencontainers.image.title="AllBot LAN all-task ComfyUI profile"
LABEL org.opencontainers.image.description="LAN-only union runtime for all supported AllBot image and video workflows; model files stay in external LAN manifests."
LABEL allbot.lan.profile="all"
LABEL allbot.lan.models="external-lan-manifests"
LABEL allbot.lan.scope="gpu226-production-validation"
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
    python3 -m pip --version >/dev/null

RUN set -euo pipefail; \
    comfyui_dir="${COMFYUI_INSTALL_DIR}"; \
    if [ "${REUSE_BASE_CUSTOM_NODES}" = "true" ]; then \
      echo "Reusing pinned ComfyUI and LTX sources from base image"; \
      test -f "${comfyui_dir}/main.py"; \
      test -d "${comfyui_dir}/custom_nodes/ComfyUI-LTXVideo"; \
    else \
      rm -rf "${comfyui_dir}"; \
      mkdir -p "${comfyui_dir}"; \
      git -C "${comfyui_dir}" init; \
      git -C "${comfyui_dir}" remote add origin "${COMFYUI_REPO}"; \
      for attempt in 1 2 3 4 5; do \
        git -C "${comfyui_dir}" fetch --depth 1 --filter=blob:none origin "${COMFYUI_REF}" && break; \
        if [ "$attempt" = "5" ]; then exit 128; fi; \
        sleep $((attempt * 3)); \
      done; \
      git -C "${comfyui_dir}" checkout --force FETCH_HEAD; \
      test "$(git -C "${comfyui_dir}" rev-parse HEAD)" = "${COMFYUI_REF}"; \
      python3 -m pip install --no-cache-dir -r "${comfyui_dir}/requirements.txt"; \
      rm -rf "${comfyui_dir}/.git"; \
      mkdir -p "${comfyui_dir}/custom_nodes"; \
    fi; \
    echo "${comfyui_dir}" > /opt/allbot-comfyui-dir

COPY --from=node_source /default-comfyui-bundle/ComfyUI/custom_nodes/ComfyUI-KJNodes /opt/allbot/node_source/ComfyUI-KJNodes
COPY --from=node_source /default-comfyui-bundle/ComfyUI/custom_nodes/ComfyUI-VideoHelperSuite /opt/allbot/node_source/ComfyUI-VideoHelperSuite
COPY --from=node_source /default-comfyui-bundle/ComfyUI/custom_nodes/rgthree-comfy /opt/allbot/node_source/rgthree-comfy
COPY --from=node_source /default-comfyui-bundle/ComfyUI/custom_nodes/ComfyUI-Frame-Interpolation /opt/allbot/node_source/ComfyUI-Frame-Interpolation
COPY --from=node_source /default-comfyui-bundle/ComfyUI/custom_nodes/ComfyUI_Fill-Nodes /opt/allbot/node_source/ComfyUI_Fill-Nodes
COPY --from=node_source /default-comfyui-bundle/ComfyUI/custom_nodes/ComfyUI-GGUF /opt/allbot/node_source/ComfyUI-GGUF
COPY --from=node_source /default-comfyui-bundle/ComfyUI/custom_nodes/ComfyUI-DaSiWa-Nodes /opt/allbot/node_source/ComfyUI-DaSiWa-Nodes
COPY --from=node_source /default-comfyui-bundle/ComfyUI/custom_nodes/comfyui-WhiteRabbit /opt/allbot/node_source/comfyui-WhiteRabbit
COPY workers/runpod_profiles/ltx_t2v/allbot_ltx_min_nodes /opt/allbot/allbot_ltx_min_nodes
COPY workers/runpod_profiles/pornmaster_flux2_edit/patch_flux2_small_decoder.py /opt/allbot/patch_flux2_small_decoder.py
COPY workers/runpod_runtime /opt/allbot/runtime/runpod_worker
COPY workers/runpod_profiles/all/runpod_sync_models_multi_manifest.patch /opt/allbot/runpod_sync_models_multi_manifest.patch
COPY workers/runpod_runtime/scripts/runpod_bootstrap_from_git.sh /opt/allbot/runpod_bootstrap_from_git.sh
COPY workers/runpod_runtime/scripts/runpod_baked_runtime_entrypoint.sh /opt/allbot/runpod_baked_runtime_entrypoint.sh

RUN set -euo pipefail; \
    comfyui_dir="$(cat /opt/allbot-comfyui-dir)"; \
    for node_name in \
      ComfyUI-KJNodes \
      ComfyUI-VideoHelperSuite \
      rgthree-comfy \
      ComfyUI-Frame-Interpolation \
      ComfyUI_Fill-Nodes \
      ComfyUI-GGUF \
      ComfyUI-DaSiWa-Nodes \
      comfyui-WhiteRabbit; do \
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
    if [ "${REUSE_BASE_CUSTOM_NODES}" = "true" ]; then \
      test -f "${ltxvideo_dir}/__init__.py"; \
    else \
      mkdir -p "${ltxvideo_dir}"; \
      git -C "${ltxvideo_dir}" init; \
      git -C "${ltxvideo_dir}" remote add origin "${LTXVIDEO_REPO}"; \
      git -C "${ltxvideo_dir}" fetch --depth 1 --filter=blob:none origin "${LTXVIDEO_REF}"; \
      git -C "${ltxvideo_dir}" checkout --force FETCH_HEAD; \
      test "$(git -C "${ltxvideo_dir}" rev-parse HEAD)" = "${LTXVIDEO_REF}"; \
      python3 -m pip install --no-cache-dir -r "${ltxvideo_dir}/requirements.txt"; \
      rm -rf "${ltxvideo_dir}/.git"; \
    fi; \
    COMFYUI_DIR="${comfyui_dir}" python3 /opt/allbot/patch_flux2_small_decoder.py; \
    (cd /opt/allbot/runtime/runpod_worker && git apply /opt/allbot/runpod_sync_models_multi_manifest.patch); \
    python3 -m pip install --no-cache-dir -r /opt/allbot/runtime/runpod_worker/requirements.txt; \
    python3 -m pip install --no-cache-dir minio packaging "sageattention==${SAGEATTENTION_VERSION}"; \
    chmod +x /opt/allbot/runpod_bootstrap_from_git.sh /opt/allbot/runpod_baked_runtime_entrypoint.sh; \
    PYTHONPATH=/opt/allbot/runtime/runpod_worker python3 -c 'from comfy_agent.workflow_task_patchers import TASK_SPECIFIC_PATCHERS'; \
    COMFYUI_DIR="${comfyui_dir}" LTXVIDEO_NODE_DIR="${ltxvideo_dir}" PYTHONPATH="${comfyui_dir}:${PYTHONPATH:-}" python3 -c 'import importlib.util, os, sys; from pathlib import Path; import comfy.cli_args; comfy.cli_args.args.cpu=True; root=Path(os.environ["COMFYUI_DIR"]); node_dir=Path(os.environ["LTXVIDEO_NODE_DIR"]); spec=importlib.util.spec_from_file_location("allbot_ltxvideo_smoke", node_dir/"__init__.py", submodule_search_locations=[str(node_dir)]); module=importlib.util.module_from_spec(spec); assert spec.loader is not None; sys.modules[spec.name]=module; spec.loader.exec_module(module); expected={"LTXVSpatioTemporalTiledVAEDecode","LTXICLoRALoaderModelOnly","LTXAddVideoICLoRAGuide"}; assert expected <= set(module.NODE_CLASS_MAPPINGS), expected-set(module.NODE_CLASS_MAPPINGS); scail=(root/"comfy_extras"/"nodes_scail.py").read_text(encoding="utf-8"); assert "WanSCAILToVideo" in scail and "SCAIL2ColoredMask" in scail; kj=(root/"custom_nodes"/"ComfyUI-KJNodes"/"__init__.py").read_text(encoding="utf-8"); assert "DiffusionModelLoaderKJ" in kj and "VAELoaderKJ" in kj'; \
    LTX_MIN_NODE_DIR="${comfyui_dir}/custom_nodes/allbot_ltx_min_nodes" python3 -c 'import importlib.util, os; from pathlib import Path; spec=importlib.util.spec_from_file_location("allbot_ltx_min_nodes_smoke", Path(os.environ["LTX_MIN_NODE_DIR"])/"__init__.py"); module=importlib.util.module_from_spec(spec); assert spec.loader is not None; spec.loader.exec_module(module); expected={"ImpactDummyInput","TwoWaySwitch","easy int","mxSlider","RAMCleanup","VRAMCleanup","Float","IntToFloat","Sigmas Sigmoid","MathExpression|pysssss"}; assert expected <= set(module.NODE_CLASS_MAPPINGS)'; \
    COMFYUI_DIR="${comfyui_dir}" python3 -c 'from pathlib import Path; import os, sys; root=Path(os.environ["COMFYUI_DIR"]); checks={root/"nodes.py":("UNETLoader","CLIPLoader","VAELoader"),root/"comfy_extras"/"nodes_custom_sampler.py":("SamplerCustomAdvanced",),root/"comfy_extras"/"nodes_edit_model.py":("ReferenceLatent",),root/"comfy_extras"/"nodes_flux.py":("EmptyFlux2LatentImage","Flux2Scheduler")}; missing=[]; [missing.append(f"{path}:{name}") for path,names in checks.items() for name in names if name not in path.read_text(encoding="utf-8")]; sys.exit("missing all-profile core node sources: "+",".join(missing)) if missing else None'; \
    python3 "${comfyui_dir}/main.py" --cpu --quick-test-for-ci --disable-auto-launch; \
    python3 -c 'import json; from pathlib import Path; root=Path("/opt/allbot/runtime/runpod_worker/comfy_agent/workflows"); mappings=json.loads((root/"mappings.json").read_text()); expected={"img2img","img2img_lora","image_to_video","wan22_video_v2","pornmaster_flux2_edit_bf16","pornmaster_flux2_multi_edit_bf16","scail2_action_transfer","scail2_action_transfer_long","scail2_video_replacement","scail2_face_swap_v2","ltx_video","ltx_video_flf2v","ltx_video_v2v_audio","i2i_pro","t2i-pornmaster-turbo","face_swap_v2","face_swap","ltx_t2v","ltx_t2v_ic"}; assert expected <= set(mappings), sorted(expected-set(mappings))'; \
    if find "${comfyui_dir}/models" -type f \( -name "*.safetensors" -o -name "*.ckpt" -o -name "*.pth" \) -print -quit | grep -q .; then \
      echo "Business model files must stay out of the LAN all image" >&2; \
      exit 1; \
    fi; \
    find "${comfyui_dir}" -type d -name __pycache__ -prune -exec rm -rf {} +; \
    python3 -m pip cache purge >/dev/null 2>&1 || true; \
    rm -rf /root/.cache/pip /tmp/* /var/tmp/*

ENV ALLBOT_RUNPOD_REPO_DIR=/opt/allbot/runtime \
    ALLBOT_RUNPOD_WORKER_DIR=/opt/allbot/runtime/runpod_worker
CMD ["bash", "/opt/allbot/runpod_baked_runtime_entrypoint.sh"]
