ARG BASE_IMAGE=192.168.1.115:5000/allbot/comfy-runpod-i2i-pro:20260614-i2ipro-b75c6a9-cu128-min5-ssh
FROM ${BASE_IMAGE}

LABEL org.opencontainers.image.title="AllBot RunPod PornMaster Flux2 edit ComfyUI profile"
LABEL org.opencontainers.image.description="ComfyUI runtime profile for PornMaster Flux2 single/multiple image editing; model files are synced from the LAN model cache at startup."
LABEL allbot.runpod.profile="pornmaster_flux2_edit"
LABEL allbot.runpod.models="external-lan-manifest"

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

COPY patch_flux2_small_decoder.py /opt/allbot/patch_flux2_small_decoder.py

RUN set -euo pipefail; \
    comfyui_dir="$(cat /opt/allbot-comfyui-dir)"; \
    test -f "${comfyui_dir}/main.py"; \
    COMFYUI_DIR="${comfyui_dir}" python3 /opt/allbot/patch_flux2_small_decoder.py; \
    python3 -c 'from pathlib import Path; import sys; root=Path("/opt/allbot-comfyui-dir").read_text().strip(); root=Path(root); checks={root/"nodes.py":("UNETLoader","CLIPLoader","VAELoader"),root/"comfy_extras"/"nodes_custom_sampler.py":("SamplerCustomAdvanced",),root/"comfy_extras"/"nodes_edit_model.py":("ReferenceLatent",),root/"comfy_extras"/"nodes_flux.py":("EmptyFlux2LatentImage","Flux2Scheduler")}; missing=[]; [missing.append(f"{path}:{name}") for path,names in checks.items() for name in names if name not in path.read_text(encoding="utf-8")]; sys.exit("missing PornMaster Flux2 edit node sources: "+",".join(missing)) if missing else None'; \
    find "${comfyui_dir}/models" -type f \( \
      -name 'PornMaster_flux2_klein_9b_turbo_fp8_V4.safetensors' -o \
      -name 'qwen_3_8b_fp8mixed.safetensors' -o \
      -name 'full_encoder_small_decoder.safetensors' \
      \) -print -quit | \
      awk 'NF { print "Business model file unexpectedly present in image: " $0; exit 1 }'
