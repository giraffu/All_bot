ARG RUNTIME_BASE_IMAGE=192.168.1.115:5000/allbot/allbot-gpu-lan-all@sha256:c6756b3ab6981b37058f8e2fe2ef59c556f326872ab1ad75dd9d7a1398b21d33
FROM ${RUNTIME_BASE_IMAGE}

ARG ALLBOT_GIT_SHA
ARG ALLBOT_RUNTIME_PACKAGE_SHA256
ARG ALLBOT_WORKFLOW_MAPPING_SHA256
ENV ALLBOT_GIT_SHA=$ALLBOT_GIT_SHA \
    ALLBOT_RUNTIME_PACKAGE_SHA256=$ALLBOT_RUNTIME_PACKAGE_SHA256 \
    ALLBOT_WORKFLOW_MAPPING_SHA256=$ALLBOT_WORKFLOW_MAPPING_SHA256
ARG RUNTIME_REQUIREMENTS_SHA256=d81a4ee4dc26db0deb2d554bd59b277dfae0bf9071454a5d955f8fff4925ed13

LABEL org.opencontainers.image.title="AllBot LAN SCAIL-2 flex runtime"
LABEL org.opencontainers.image.description="Restricted SCAIL-2-first LAN runtime with img2img and img2img_lora fallback."
LABEL allbot.lan.profile="scail2_flex"
LABEL allbot.lan.models="external-lan-multi-manifest"
LABEL allbot.lan.scope="gpu002-gpu0"
LABEL org.opencontainers.image.revision=$ALLBOT_GIT_SHA \
      io.allbot.runpod.agent-revision=$ALLBOT_GIT_SHA \
      io.allbot.runpod.workflow-revision=$ALLBOT_GIT_SHA

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN set -euo pipefail; \
    echo "${RUNTIME_REQUIREMENTS_SHA256}  /opt/allbot/runtime/runpod_worker/requirements.txt" | sha256sum -c -; \
    rm -rf /opt/allbot/runtime/runpod_worker

COPY workers/runpod_runtime /opt/allbot/runtime/runpod_worker
COPY workers/comfy_agent /opt/allbot/runtime/runpod_worker/comfy_agent
COPY src /opt/allbot/runtime/runpod_worker/src
RUN test -n "$ALLBOT_GIT_SHA" && \
    test -n "$ALLBOT_RUNTIME_PACKAGE_SHA256" && \
    test -n "$ALLBOT_WORKFLOW_MAPPING_SHA256" && \
    PYTHONPATH=/opt/allbot/runtime/runpod_worker python3 -c 'from comfy_agent.runtime_manifest import load_runtime_manifest; load_runtime_manifest()'
COPY shared /opt/allbot/runtime/runpod_worker/shared

RUN set -euo pipefail; \
    echo "${RUNTIME_REQUIREMENTS_SHA256}  /opt/allbot/runtime/runpod_worker/requirements.txt" | sha256sum -c -; \
    chmod +x \
      /opt/allbot/runtime/runpod_worker/scripts/runpod_bootstrap_from_git.sh \
      /opt/allbot/runtime/runpod_worker/scripts/runpod_baked_runtime_entrypoint.sh; \
    PYTHONPATH=/opt/allbot/runtime/runpod_worker python3 -c 'from comfy_agent.workflow_task_patchers import TASK_SPECIFIC_PATCHERS; from shared.character_reference_sheet import compose_ingredients_character_panel; assert callable(compose_ingredients_character_panel); expected={"scail2_action_transfer","scail2_action_transfer_long","scail2_video_replacement","scail2_face_swap_v2","img2img","img2img_lora"}; assert expected <= set(TASK_SPECIFIC_PATCHERS), sorted(expected-set(TASK_SPECIFIC_PATCHERS))'; \
    PYTHONPATH=/opt/allbot/runtime/runpod_worker python3 -c 'from pathlib import Path; from src.workflow_mapping_validation import resolve_workflow_filename; root=Path("/opt/allbot/runtime/runpod_worker/comfy_agent/workflows"); expected={"scail2_action_transfer","scail2_action_transfer_long","scail2_video_replacement","scail2_face_swap_v2","img2img","img2img_lora"}; missing=[task_type for task_type in expected if not (root/resolve_workflow_filename(task_type)).is_file()]; assert not missing, missing'; \
    if find /opt/ComfyUI/models -type f \( -name "*.safetensors" -o -name "*.ckpt" -o -name "*.pth" \) -print -quit | grep -q .; then \
      echo "Business model files must stay out of the SCAIL-2 flex image" >&2; \
      exit 1; \
    fi; \
    find /opt/allbot/runtime/runpod_worker -type d -name __pycache__ -prune -exec rm -rf {} +

ENV ALLBOT_RUNPOD_REPO_DIR=/opt/allbot/runtime \
    ALLBOT_RUNPOD_WORKER_DIR=/opt/allbot/runtime/runpod_worker
CMD ["bash", "/opt/allbot/runtime/runpod_worker/scripts/runpod_baked_runtime_entrypoint.sh"]
