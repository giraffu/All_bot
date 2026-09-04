from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any


GPU_PHASE_TELEMETRY_VERSION = "gpu_phase_v1"
GPU_PHASE_MARKER_PREFIX = f"dashboard_{GPU_PHASE_TELEMETRY_VERSION}|"
GPU_PHASE_KEY_PREFIX = f"dashboard:worker_gpu_phase:{GPU_PHASE_TELEMETRY_VERSION}:"
GPU_PHASE_TTL_SECONDS = 7 * 24 * 60 * 60


@dataclass(frozen=True)
class GpuEquivalence:
    gpu: str
    factor: float


# Physical GPU seconds multiplied by this factor yield RTX 5090-equivalent
# seconds. Only stable production worker identities with a known GPU are listed;
# mixed RunPod profiles intentionally require an explicit runtime override.
_DEFAULT_WORKER_GPU_RULES: tuple[tuple[str, GpuEquivalence], ...] = (
    ("lan_aio_prod_gpu177_", GpuEquivalence("rtx_5090", 1.0)),
    ("lan_aio_prod_gpu226_", GpuEquivalence("rtx_5090", 1.0)),
    ("lan_aio_prod_gpu252_", GpuEquivalence("rtx_4090", 0.69)),
    ("runpod_prod_img2img_", GpuEquivalence("rtx_4090", 0.69)),
    ("runpod_prod_image_to_video_", GpuEquivalence("rtx_4090", 0.69)),
    ("runpod_prod_i2i_pro_", GpuEquivalence("rtx_4090", 0.69)),
    (
        "runpod_prod_pornmaster_flux2_edit_bf16_",
        GpuEquivalence("rtx_4090", 0.69),
    ),
    ("runpod_prod_minimax_h3_", GpuEquivalence("rtx_5090", 1.0)),
    ("runpod_prod_ltx_t2v_", GpuEquivalence("rtx_5090", 1.0)),
    ("runpod_prod_ltx25_video_upscale_", GpuEquivalence("rtx_5090", 1.0)),
)


def gpu_phase_key(task_id: str) -> str:
    return f"{GPU_PHASE_KEY_PREFIX}{task_id}"


def _configured_worker_gpu_rules() -> tuple[tuple[str, GpuEquivalence], ...]:
    raw = os.getenv("DASHBOARD_WORKER_GPU_EQUIVALENCE_JSON", "").strip()
    if not raw:
        return ()
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return ()
    if not isinstance(payload, dict):
        return ()

    rules: list[tuple[str, GpuEquivalence]] = []
    for worker_prefix, value in payload.items():
        if not isinstance(worker_prefix, str) or not worker_prefix:
            continue
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            gpu = "configured"
            factor = float(value)
        elif isinstance(value, dict):
            gpu = str(value.get("gpu") or "configured").strip() or "configured"
            try:
                factor = float(value.get("factor"))
            except (TypeError, ValueError):
                continue
        else:
            continue
        if 0 < factor <= 10:
            rules.append((worker_prefix, GpuEquivalence(gpu, factor)))
    return tuple(sorted(rules, key=lambda item: len(item[0]), reverse=True))


def resolve_worker_gpu_equivalence(worker_id: Any) -> GpuEquivalence | None:
    normalized = str(worker_id or "").strip()
    if not normalized:
        return None
    rules = (*_configured_worker_gpu_rules(), *_DEFAULT_WORKER_GPU_RULES)
    for prefix, equivalence in rules:
        if normalized.startswith(prefix):
            return equivalence
    return None


def build_gpu_phase_marker(equivalence: GpuEquivalence) -> str:
    return (
        f"{GPU_PHASE_MARKER_PREFIX}gpu={equivalence.gpu}|factor={equivalence.factor:g}"
    )


def parse_gpu_phase_factor(value: Any) -> float | None:
    marker = str(value or "")
    if not marker.startswith(GPU_PHASE_MARKER_PREFIX):
        return None
    fields: dict[str, str] = {}
    for part in marker[len(GPU_PHASE_MARKER_PREFIX) :].split("|"):
        key, separator, field_value = part.partition("=")
        if separator:
            fields[key] = field_value
    try:
        factor = float(fields["factor"])
    except (KeyError, TypeError, ValueError):
        return None
    return factor if 0 < factor <= 10 else None


def visible_worker_error(value: Any) -> str | None:
    normalized = str(value or "").strip()
    if not normalized or normalized.startswith(GPU_PHASE_MARKER_PREFIX):
        return None
    return normalized
