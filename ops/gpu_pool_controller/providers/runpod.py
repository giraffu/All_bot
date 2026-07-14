from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable

from ..runpod_profile_catalog import (
    RUNPOD_I2I_PRO_CONTAINER_DISK_GB,
    RUNPOD_I2I_PRO_GPU_TYPE_IDS,
    RUNPOD_I2I_PRO_MODEL_MANIFEST_KEY,
    RUNPOD_I2I_PRO_MODEL_PREFIX,
    RUNPOD_I2I_PRO_SUPPORTED_TASK_TYPES,
    RUNPOD_I2I_PRO_WORKFLOW_OVERRIDES,
    RUNPOD_IMG2IMG_LORA_DOCKER_START_CMD,
    RUNPOD_IMAGE_TO_VIDEO_MODEL_MANIFEST_KEY,
    RUNPOD_IMAGE_TO_VIDEO_MODEL_PREFIX,
    RUNPOD_LTX_VIDEO_CONTAINER_DISK_GB,
    RUNPOD_LTX_VIDEO_DOCKER_START_CMD,
    RUNPOD_LTX_VIDEO_GPU_TYPE_IDS,
    RUNPOD_LTX_VIDEO_MODEL_MANIFEST_KEY,
    RUNPOD_LTX_VIDEO_MODEL_PREFIX,
    RUNPOD_LTX_VIDEO_SUPPORTED_TASK_TYPES,
    RUNPOD_LTX_VIDEO_WORKFLOW_OVERRIDES,
    RUNPOD_PORNMASTER_FLUX2_EDIT_CONTAINER_DISK_GB,
    RUNPOD_PORNMASTER_FLUX2_EDIT_DOCKER_START_CMD,
    RUNPOD_PORNMASTER_FLUX2_EDIT_GPU_TYPE_IDS,
    RUNPOD_PORNMASTER_FLUX2_EDIT_MODEL_MANIFEST_KEY,
    RUNPOD_PORNMASTER_FLUX2_EDIT_MODEL_PREFIX,
    RUNPOD_PORNMASTER_FLUX2_EDIT_SUPPORTED_TASK_TYPES,
    RUNPOD_PORNMASTER_FLUX2_EDIT_BF16_CONTAINER_DISK_GB,
    RUNPOD_PORNMASTER_FLUX2_EDIT_BF16_COMFY_EXTRA_ARGS,
    RUNPOD_PORNMASTER_FLUX2_EDIT_BF16_DOCKER_START_CMD,
    RUNPOD_PORNMASTER_FLUX2_EDIT_BF16_GPU_TYPE_IDS,
    RUNPOD_PORNMASTER_FLUX2_EDIT_BF16_MODEL_MANIFEST_KEY,
    RUNPOD_PORNMASTER_FLUX2_EDIT_BF16_MODEL_PREFIX,
    RUNPOD_PORNMASTER_FLUX2_EDIT_BF16_SUPPORTED_TASK_TYPES,
    RUNPOD_PROD_AGENT_ID,
    RUNPOD_PROD_AGENT_ID_PREFIX,
    RUNPOD_PROD_BUCKET,
    RUNPOD_PROD_DEFAULT_MAX_MANUAL_SLOTS,
    RUNPOD_PROD_GPU_TYPE_IDS,
    RUNPOD_PROD_IMAGE_TO_VIDEO_AGENT_ID_PREFIX,
    RUNPOD_PROD_IMAGE_TO_VIDEO_POD_NAME_PREFIX,
    RUNPOD_PROD_I2I_PRO_AGENT_ID_PREFIX,
    RUNPOD_PROD_I2I_PRO_POD_NAME_PREFIX,
    RUNPOD_PROD_LTX_VIDEO_AGENT_ID_PREFIX,
    RUNPOD_PROD_LTX_VIDEO_POD_NAME_PREFIX,
    RUNPOD_PROD_PORNMASTER_FLUX2_EDIT_AGENT_ID_PREFIX,
    RUNPOD_PROD_PORNMASTER_FLUX2_EDIT_POD_NAME_PREFIX,
    RUNPOD_PROD_MAX_MANUAL_SLOTS,
    RUNPOD_PROD_NODE_ID,
    RUNPOD_PROD_POD_NAME_PREFIX,
    RUNPOD_PROD_SCAIL2_AGENT_ID_PREFIX,
    RUNPOD_PROD_SCAIL2_POD_NAME_PREFIX,
    RUNPOD_PROD_SUPPORTED_TASK_TYPES,
    RUNPOD_PROD_WAN22_VIDEO_V2_AGENT_ID_PREFIX,
    RUNPOD_PROD_WAN22_VIDEO_V2_POD_NAME_PREFIX,
    RUNPOD_PUBLIC_IMG2IMG_LORA_IMAGE,
    RUNPOD_PUBLIC_LTX_VIDEO_IMAGE_PREFIX,
    RUNPOD_PUBLIC_PORNMASTER_FLUX2_EDIT_IMAGE_PREFIX,
    RUNPOD_PUBLIC_SCAIL2_IMAGE_PREFIX,
    RUNPOD_PUBLIC_WAN22_AIO_VIDEO_RIFE_IMAGE,
    RUNPOD_PUBLIC_WAN22_VIDEO_V2_IMAGE_PREFIX,
    RUNPOD_SCAIL2_CONTAINER_DISK_GB,
    RUNPOD_SCAIL2_DOCKER_START_CMD,
    RUNPOD_SCAIL2_GPU_TYPE_IDS,
    RUNPOD_SCAIL2_MODEL_MANIFEST_KEY,
    RUNPOD_SCAIL2_MODEL_PREFIX,
    RUNPOD_SCAIL2_SUPPORTED_TASK_TYPES,
    RUNPOD_TASK_PROFILES,
    RUNPOD_WAN22_AIO_VIDEO_GPU_TYPE_IDS,
    RUNPOD_WAN22_AIO_VIDEO_MODEL_MANIFEST_KEY,
    RUNPOD_WAN22_AIO_VIDEO_MODEL_PREFIX,
    RUNPOD_WAN22_VIDEO_V2_COMPLETION_TIMEOUT_SECONDS,
    RUNPOD_WAN22_VIDEO_V2_COMFY_EXTRA_ARGS,
    RUNPOD_WAN22_VIDEO_V2_MODEL_MANIFEST_KEY,
    RUNPOD_WAN22_VIDEO_V2_MODEL_PREFIX,
    RunPodTaskProfile,
    _normalize_prod_worker_slot,
    _prod_agent_id_prefix_for,
    _prod_max_manual_slots_from_env,
    _prod_pod_name_prefix_for,
    _prod_profile_from_agent_id,
    normalize_prod_worker_profile,
    prod_agent_id_from_slot,
    prod_pod_name_from_agent_id,
    prod_slot_from_agent_id,
    prod_worker_profile_for_task_type,
    prod_worker_profile_from_agent_id,
)
from ..runpod_pod_request import (
    RunPodPodRequestBuilder,
    is_managed_pod as _is_managed_pod,
    normalized_ports,
    pod_cost,
    pod_readiness_from_payload,
)


__all__ = (
    "RUNPOD_API_BASE_URL",
    "RUNPOD_ACTIVE_STATUSES",
    "RUNPOD_AGENT_SECRET_TOKEN_REF",
    "RUNPOD_R2_ACCESS_KEY_REF",
    "RUNPOD_R2_SECRET_KEY_REF",
    "RUNPOD_PROD_AGENT_SECRET_TOKEN_REF",
    "RUNPOD_PROD_R2_ACCESS_KEY_REF",
    "RUNPOD_PROD_R2_SECRET_KEY_REF",
    "RUNPOD_MODEL_CACHE_R2_ACCESS_KEY_REF",
    "RUNPOD_MODEL_CACHE_R2_SECRET_KEY_REF",
    "RUNPOD_PROD_WORKER_CENTRAL_URL",
    "RUNPOD_I2I_PRO_CONTAINER_DISK_GB",
    "RUNPOD_I2I_PRO_GPU_TYPE_IDS",
    "RUNPOD_I2I_PRO_MODEL_MANIFEST_KEY",
    "RUNPOD_I2I_PRO_MODEL_PREFIX",
    "RUNPOD_I2I_PRO_SUPPORTED_TASK_TYPES",
    "RUNPOD_I2I_PRO_WORKFLOW_OVERRIDES",
    "RUNPOD_IMAGE_TO_VIDEO_MODEL_MANIFEST_KEY",
    "RUNPOD_IMAGE_TO_VIDEO_MODEL_PREFIX",
    "RUNPOD_LTX_VIDEO_CONTAINER_DISK_GB",
    "RUNPOD_LTX_VIDEO_DOCKER_START_CMD",
    "RUNPOD_LTX_VIDEO_GPU_TYPE_IDS",
    "RUNPOD_LTX_VIDEO_MODEL_MANIFEST_KEY",
    "RUNPOD_LTX_VIDEO_MODEL_PREFIX",
    "RUNPOD_LTX_VIDEO_SUPPORTED_TASK_TYPES",
    "RUNPOD_LTX_VIDEO_WORKFLOW_OVERRIDES",
    "RUNPOD_PORNMASTER_FLUX2_EDIT_CONTAINER_DISK_GB",
    "RUNPOD_PORNMASTER_FLUX2_EDIT_DOCKER_START_CMD",
    "RUNPOD_PORNMASTER_FLUX2_EDIT_GPU_TYPE_IDS",
    "RUNPOD_PORNMASTER_FLUX2_EDIT_MODEL_MANIFEST_KEY",
    "RUNPOD_PORNMASTER_FLUX2_EDIT_MODEL_PREFIX",
    "RUNPOD_PORNMASTER_FLUX2_EDIT_SUPPORTED_TASK_TYPES",
    "RUNPOD_PORNMASTER_FLUX2_EDIT_BF16_CONTAINER_DISK_GB",
    "RUNPOD_PORNMASTER_FLUX2_EDIT_BF16_COMFY_EXTRA_ARGS",
    "RUNPOD_PORNMASTER_FLUX2_EDIT_BF16_DOCKER_START_CMD",
    "RUNPOD_PORNMASTER_FLUX2_EDIT_BF16_GPU_TYPE_IDS",
    "RUNPOD_PORNMASTER_FLUX2_EDIT_BF16_MODEL_MANIFEST_KEY",
    "RUNPOD_PORNMASTER_FLUX2_EDIT_BF16_MODEL_PREFIX",
    "RUNPOD_PORNMASTER_FLUX2_EDIT_BF16_SUPPORTED_TASK_TYPES",
    "RUNPOD_PROD_AGENT_ID",
    "RUNPOD_PROD_AGENT_ID_PREFIX",
    "RUNPOD_PROD_BUCKET",
    "RUNPOD_PROD_DEFAULT_MAX_MANUAL_SLOTS",
    "RUNPOD_PROD_GPU_TYPE_IDS",
    "RUNPOD_PROD_IMAGE_TO_VIDEO_AGENT_ID_PREFIX",
    "RUNPOD_PROD_IMAGE_TO_VIDEO_POD_NAME_PREFIX",
    "RUNPOD_PROD_I2I_PRO_AGENT_ID_PREFIX",
    "RUNPOD_PROD_I2I_PRO_POD_NAME_PREFIX",
    "RUNPOD_PROD_LTX_VIDEO_AGENT_ID_PREFIX",
    "RUNPOD_PROD_LTX_VIDEO_POD_NAME_PREFIX",
    "RUNPOD_PROD_PORNMASTER_FLUX2_EDIT_AGENT_ID_PREFIX",
    "RUNPOD_PROD_PORNMASTER_FLUX2_EDIT_POD_NAME_PREFIX",
    "RUNPOD_PROD_MAX_MANUAL_SLOTS",
    "RUNPOD_PROD_NODE_ID",
    "RUNPOD_PROD_POD_NAME_PREFIX",
    "RUNPOD_PROD_SCAIL2_AGENT_ID_PREFIX",
    "RUNPOD_PROD_SCAIL2_POD_NAME_PREFIX",
    "RUNPOD_PROD_SUPPORTED_TASK_TYPES",
    "RUNPOD_PROD_WAN22_VIDEO_V2_AGENT_ID_PREFIX",
    "RUNPOD_PROD_WAN22_VIDEO_V2_POD_NAME_PREFIX",
    "RUNPOD_PUBLIC_IMG2IMG_LORA_IMAGE",
    "RUNPOD_PUBLIC_LTX_VIDEO_IMAGE_PREFIX",
    "RUNPOD_PUBLIC_PORNMASTER_FLUX2_EDIT_IMAGE_PREFIX",
    "RUNPOD_PUBLIC_SCAIL2_IMAGE_PREFIX",
    "RUNPOD_PUBLIC_WAN22_AIO_VIDEO_RIFE_IMAGE",
    "RUNPOD_PUBLIC_WAN22_VIDEO_V2_IMAGE_PREFIX",
    "RUNPOD_SCAIL2_CONTAINER_DISK_GB",
    "RUNPOD_SCAIL2_DOCKER_START_CMD",
    "RUNPOD_SCAIL2_GPU_TYPE_IDS",
    "RUNPOD_SCAIL2_MODEL_MANIFEST_KEY",
    "RUNPOD_SCAIL2_MODEL_PREFIX",
    "RUNPOD_SCAIL2_SUPPORTED_TASK_TYPES",
    "RUNPOD_TASK_PROFILES",
    "RUNPOD_WAN22_AIO_VIDEO_GPU_TYPE_IDS",
    "RUNPOD_WAN22_AIO_VIDEO_MODEL_MANIFEST_KEY",
    "RUNPOD_WAN22_AIO_VIDEO_MODEL_PREFIX",
    "RUNPOD_WAN22_VIDEO_V2_COMPLETION_TIMEOUT_SECONDS",
    "RUNPOD_WAN22_VIDEO_V2_COMFY_EXTRA_ARGS",
    "RUNPOD_WAN22_VIDEO_V2_MODEL_MANIFEST_KEY",
    "RUNPOD_WAN22_VIDEO_V2_MODEL_PREFIX",
    "RunPodProvider",
    "RunPodProviderError",
    "RunPodSettings",
    "RunPodTaskProfile",
    "_normalize_prod_worker_slot",
    "_prod_agent_id_prefix_for",
    "_prod_max_manual_slots_from_env",
    "_prod_pod_name_prefix_for",
    "_prod_profile_from_agent_id",
    "normalize_prod_worker_profile",
    "prod_agent_id_from_slot",
    "prod_pod_name_from_agent_id",
    "prod_slot_from_agent_id",
    "prod_worker_profile_for_task_type",
    "prod_worker_profile_from_agent_id",
    "redact_payload",
    "redact_text",
)


RUNPOD_API_BASE_URL = "https://rest.runpod.io/v1"
RUNPOD_ACTIVE_STATUSES = {"RUNNING"}
RUNPOD_AGENT_SECRET_TOKEN_REF = (
    "{{ RUNPOD_SECRET_allbot_cloud_test_agent_secret_token }}"
)
RUNPOD_R2_ACCESS_KEY_REF = "{{ RUNPOD_SECRET_allbot_cloud_test_r2_access_key }}"
RUNPOD_R2_SECRET_KEY_REF = "{{ RUNPOD_SECRET_allbot_cloud_test_r2_secret_key }}"
RUNPOD_PROD_AGENT_SECRET_TOKEN_REF = (
    "{{ RUNPOD_SECRET_allbot_cloud_prod_agent_secret_token }}"
)
RUNPOD_PROD_R2_ACCESS_KEY_REF = "{{ RUNPOD_SECRET_allbot_cloud_prod_r2_access_key }}"
RUNPOD_PROD_R2_SECRET_KEY_REF = "{{ RUNPOD_SECRET_allbot_cloud_prod_r2_secret_key }}"
RUNPOD_MODEL_CACHE_R2_ACCESS_KEY_REF = (
    "{{ RUNPOD_SECRET_allbot_model_cache_r2_access_key }}"
)
RUNPOD_MODEL_CACHE_R2_SECRET_KEY_REF = (
    "{{ RUNPOD_SECRET_allbot_model_cache_r2_secret_key }}"
)
RUNPOD_PROD_WORKER_CENTRAL_URL = "https://worker-central.aivison.it.com"
SENSITIVE_KEY_MARKERS = (
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "CREDENTIAL",
    "SIGNATURE",
    "ACCESS_KEY",
    "AUTHORIZATION",
)
SENSITIVE_TEXT_PATTERNS = (
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(
        r"(?i)\b("
        r"authorization|api[_-]?key|token|secret|password|credential|"
        r"signature|access[_-]?key|x-amz-signature"
        r")\b\s*[:=]\s*[^,\s&'\"}]+"
    ),
)

HttpRequestFunc = Callable[
    [str, str],
    Any,
]


class RunPodProviderError(RuntimeError):
    pass


def _bool_env(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _csv(value: str | None, *, default: tuple[str, ...] = ()) -> tuple[str, ...]:
    if value is None:
        return default
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _int_env(value: str | None, *, default: int) -> int:
    if value is None or not value.strip():
        return default
    return int(value)


def _float_env(value: str | None, *, default: float) -> float:
    if value is None or not value.strip():
        return default
    return float(value)


def _format_seconds_env(value: float) -> str:
    return f"{value:g}"


def _docker_start_cmd_env(
    json_value: str | None,
    script_value: str | None,
    script_file: str | None,
    *,
    json_env_name: str,
) -> tuple[str, ...]:
    if json_value and json_value.strip():
        parsed = json.loads(json_value)
        if not isinstance(parsed, list) or not all(
            isinstance(item, str) for item in parsed
        ):
            raise ValueError(f"{json_env_name} must be a JSON string array")
        return tuple(parsed)
    if script_file and script_file.strip():
        script = Path(script_file).expanduser().read_text(encoding="utf-8")
        return ("bash", "-lc", script)
    if script_value and script_value.strip():
        return ("bash", "-lc", script_value)
    return ()


def _runpod_extra_env_from_env() -> dict[str, str]:
    extra_env: dict[str, str] = {}
    public_key = _public_key_from_env(
        os.getenv("RUNPOD_PUBLIC_KEY"),
        os.getenv("RUNPOD_PUBLIC_KEY_FILE"),
    )
    if public_key:
        extra_env["PUBLIC_KEY"] = public_key
    return extra_env


def _public_key_from_env(value: str | None, file_value: str | None) -> str:
    raw = (value or "").strip()
    if not raw and file_value and file_value.strip():
        raw = Path(file_value).expanduser().read_text(encoding="utf-8").strip()
    if not raw:
        return ""
    for line in raw.splitlines():
        candidate = line.strip()
        if candidate.startswith("ssh-"):
            return candidate
    raise ValueError("RUNPOD_PUBLIC_KEY must contain an ssh public key")


def _is_sensitive_key(key: str) -> bool:
    normalized = key.upper()
    return any(marker in normalized for marker in SENSITIVE_KEY_MARKERS)


def redact_payload(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if _is_sensitive_key(str(key)):
                redacted[str(key)] = "<redacted>"
            else:
                redacted[str(key)] = redact_payload(item)
        return redacted
    if isinstance(value, list):
        return [redact_payload(item) for item in value]
    if isinstance(value, tuple):
        return [redact_payload(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def redact_text(value: str) -> str:
    redacted = value
    for pattern in SENSITIVE_TEXT_PATTERNS:
        redacted = pattern.sub(
            lambda match: _redact_text_match(match.group(0)), redacted
        )
    return redacted


def _redact_text_match(value: str) -> str:
    if value.lower().startswith("bearer "):
        return "Bearer <redacted>"
    separator = ":" if ":" in value else "="
    key = value.split(separator, 1)[0]
    return f"{key}{separator}<redacted>"


@dataclass(frozen=True)
class RunPodSettings:
    api_key: str = ""
    base_url: str = RUNPOD_API_BASE_URL
    autoscaler_enabled: bool = False
    dry_run: bool = True
    max_pods_total: int = 1
    max_pods_per_type: int = 1
    max_hourly_cost_usd: float = 5.0
    projected_cost_per_hr_img2img_lora: float = 0.0
    projected_cost_per_hr_wan22_aio_video: float = 0.0
    projected_cost_per_hr_image_to_video: float = 0.0
    projected_cost_per_hr_wan22_video_v2: float = 0.0
    projected_cost_per_hr_i2i_pro: float = 0.0
    projected_cost_per_hr_scail2: float = 0.0
    projected_cost_per_hr_ltx_video: float = 0.0
    projected_cost_per_hr_pornmaster_flux2_edit: float = 0.0
    cloud_type: str = "SECURE"
    interruptible: bool = False
    gpu_type_ids_img2img_lora: tuple[str, ...] = (
        "NVIDIA GeForce RTX 4090",
        "NVIDIA GeForce RTX 5090",
        "NVIDIA L40S",
    )
    gpu_type_ids_wan22_aio_video: tuple[str, ...] = RUNPOD_WAN22_AIO_VIDEO_GPU_TYPE_IDS
    gpu_type_ids_image_to_video: tuple[str, ...] = RUNPOD_WAN22_AIO_VIDEO_GPU_TYPE_IDS
    gpu_type_ids_wan22_video_v2: tuple[str, ...] = RUNPOD_WAN22_AIO_VIDEO_GPU_TYPE_IDS
    gpu_type_ids_i2i_pro: tuple[str, ...] = RUNPOD_I2I_PRO_GPU_TYPE_IDS
    gpu_type_ids_scail2: tuple[str, ...] = RUNPOD_SCAIL2_GPU_TYPE_IDS
    gpu_type_ids_ltx_video: tuple[str, ...] = RUNPOD_LTX_VIDEO_GPU_TYPE_IDS
    gpu_type_ids_pornmaster_flux2_edit: tuple[
        str, ...
    ] = RUNPOD_PORNMASTER_FLUX2_EDIT_GPU_TYPE_IDS
    data_center_ids: tuple[str, ...] = ()
    container_disk_gb: int = 80
    container_disk_gb_ltx_video: int = RUNPOD_LTX_VIDEO_CONTAINER_DISK_GB
    container_disk_gb_pornmaster_flux2_edit: int = (
        RUNPOD_PORNMASTER_FLUX2_EDIT_CONTAINER_DISK_GB
    )
    volume_gb: int = 0
    volume_mount_path: str = "/workspace"
    network_volume_id: str = ""
    pod_ports: tuple[str, ...] = ()
    use_template_img2img_lora: bool = True
    use_template_wan22_aio_video: bool = False
    use_template_image_to_video: bool = False
    use_template_wan22_video_v2: bool = False
    use_template_i2i_pro: bool = False
    use_template_scail2: bool = False
    use_template_ltx_video: bool = False
    use_template_pornmaster_flux2_edit: bool = False
    docker_start_cmd_img2img_lora: tuple[
        str, ...
    ] = RUNPOD_IMG2IMG_LORA_DOCKER_START_CMD
    docker_start_cmd_wan22_aio_video: tuple[str, ...] = ()
    docker_start_cmd_image_to_video: tuple[str, ...] = ()
    docker_start_cmd_wan22_video_v2: tuple[str, ...] = ()
    docker_start_cmd_i2i_pro: tuple[str, ...] = ()
    docker_start_cmd_scail2: tuple[str, ...] = RUNPOD_SCAIL2_DOCKER_START_CMD
    docker_start_cmd_ltx_video: tuple[str, ...] = RUNPOD_LTX_VIDEO_DOCKER_START_CMD
    docker_start_cmd_pornmaster_flux2_edit: tuple[
        str, ...
    ] = RUNPOD_PORNMASTER_FLUX2_EDIT_DOCKER_START_CMD
    template_id_img2img_lora: str = ""
    template_id_wan22_aio_video: str = ""
    template_id_image_to_video: str = ""
    template_id_wan22_video_v2: str = ""
    template_id_i2i_pro: str = ""
    template_id_scail2: str = ""
    template_id_ltx_video: str = ""
    template_id_pornmaster_flux2_edit: str = ""
    image_name_img2img_lora: str = ""
    image_name_wan22_aio_video: str = ""
    image_name_image_to_video: str = RUNPOD_PUBLIC_WAN22_AIO_VIDEO_RIFE_IMAGE
    image_name_wan22_video_v2: str = RUNPOD_PUBLIC_WAN22_AIO_VIDEO_RIFE_IMAGE
    image_name_i2i_pro: str = ""
    image_name_scail2: str = ""
    image_name_ltx_video: str = ""
    image_name_pornmaster_flux2_edit: str = ""
    worker_central_url_cloud_test: str = "https://worker-central-test.example.com"
    worker_central_url_cloud_prod: str = RUNPOD_PROD_WORKER_CENTRAL_URL
    prod_agent_id: str = RUNPOD_PROD_AGENT_ID
    prod_supported_task_types: tuple[str, ...] = RUNPOD_PROD_SUPPORTED_TASK_TYPES
    prod_gpu_type_ids: tuple[str, ...] = RUNPOD_PROD_GPU_TYPE_IDS
    prod_max_manual_slots: int = RUNPOD_PROD_DEFAULT_MAX_MANUAL_SLOTS
    prod_node_id: str = RUNPOD_PROD_NODE_ID
    prod_bucket: str = RUNPOD_PROD_BUCKET
    prod_agent_secret_token_ref: str = RUNPOD_PROD_AGENT_SECRET_TOKEN_REF
    prod_minio_access_key_ref: str = RUNPOD_PROD_R2_ACCESS_KEY_REF
    prod_minio_secret_key_ref: str = RUNPOD_PROD_R2_SECRET_KEY_REF
    keepalive_on_bootstrap_failure: bool = False
    agent_secret_token: str = ""
    minio_endpoint: str = ""
    minio_access_key: str = ""
    minio_secret_key: str = ""
    agent_secret_token_ref: str = RUNPOD_AGENT_SECRET_TOKEN_REF
    minio_access_key_ref: str = RUNPOD_R2_ACCESS_KEY_REF
    minio_secret_key_ref: str = RUNPOD_R2_SECRET_KEY_REF
    model_sync_enabled: bool = False
    model_bucket: str = ""
    model_prefix: str = "img2img_lora/2026-06-10"
    model_manifest_key: str = ""
    model_prefix_wan22_aio_video: str = RUNPOD_WAN22_AIO_VIDEO_MODEL_PREFIX
    model_manifest_key_wan22_aio_video: str = RUNPOD_WAN22_AIO_VIDEO_MODEL_MANIFEST_KEY
    model_prefix_image_to_video: str = RUNPOD_IMAGE_TO_VIDEO_MODEL_PREFIX
    model_manifest_key_image_to_video: str = RUNPOD_IMAGE_TO_VIDEO_MODEL_MANIFEST_KEY
    model_prefix_wan22_video_v2: str = RUNPOD_WAN22_VIDEO_V2_MODEL_PREFIX
    model_manifest_key_wan22_video_v2: str = RUNPOD_WAN22_VIDEO_V2_MODEL_MANIFEST_KEY
    wan22_video_v2_completion_timeout_seconds: float = (
        RUNPOD_WAN22_VIDEO_V2_COMPLETION_TIMEOUT_SECONDS
    )
    wan22_video_v2_exit_on_timeout: bool = True
    wan22_video_v2_comfy_extra_args: str = RUNPOD_WAN22_VIDEO_V2_COMFY_EXTRA_ARGS
    model_prefix_i2i_pro: str = RUNPOD_I2I_PRO_MODEL_PREFIX
    model_manifest_key_i2i_pro: str = RUNPOD_I2I_PRO_MODEL_MANIFEST_KEY
    task_type_workflow_overrides_i2i_pro: str = RUNPOD_I2I_PRO_WORKFLOW_OVERRIDES
    model_prefix_scail2: str = RUNPOD_SCAIL2_MODEL_PREFIX
    model_manifest_key_scail2: str = RUNPOD_SCAIL2_MODEL_MANIFEST_KEY
    model_prefix_ltx_video: str = RUNPOD_LTX_VIDEO_MODEL_PREFIX
    model_manifest_key_ltx_video: str = RUNPOD_LTX_VIDEO_MODEL_MANIFEST_KEY
    task_type_workflow_overrides_ltx_video: str = RUNPOD_LTX_VIDEO_WORKFLOW_OVERRIDES
    model_prefix_pornmaster_flux2_edit: str = (
        RUNPOD_PORNMASTER_FLUX2_EDIT_MODEL_PREFIX
    )
    model_manifest_key_pornmaster_flux2_edit: str = (
        RUNPOD_PORNMASTER_FLUX2_EDIT_MODEL_MANIFEST_KEY
    )
    model_endpoint: str = ""
    model_secure: bool = True
    model_access_key_ref: str = RUNPOD_MODEL_CACHE_R2_ACCESS_KEY_REF
    model_secret_key_ref: str = RUNPOD_MODEL_CACHE_R2_SECRET_KEY_REF
    comfy_custom_nodes_enabled: bool = True
    comfy_kjnodes_enabled: bool = True
    extra_env: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "RunPodSettings":
        model_bucket = os.getenv("RUNPOD_MODEL_BUCKET", "")
        global_model_prefix = os.getenv(
            "RUNPOD_MODEL_PREFIX", "img2img_lora/2026-06-10"
        )
        global_model_manifest_key = os.getenv("RUNPOD_MODEL_MANIFEST_KEY", "")
        wan22_aio_image = os.getenv("RUNPOD_IMAGE_NAME_WAN22_AIO_VIDEO", "")
        wan22_aio_gpu_type_ids = (
            _csv(
                os.getenv("RUNPOD_GPU_TYPE_IDS_WAN22_AIO_VIDEO"),
                default=cls.gpu_type_ids_wan22_aio_video,
            )
            or RUNPOD_WAN22_AIO_VIDEO_GPU_TYPE_IDS
        )
        wan22_aio_cost = _float_env(
            os.getenv("RUNPOD_PROJECTED_COST_PER_HR_WAN22_AIO_VIDEO"),
            default=0.0,
        )
        image_to_video_use_template_raw = os.getenv(
            "RUNPOD_USE_TEMPLATE_IMAGE_TO_VIDEO"
        )
        wan22_video_v2_use_template_raw = os.getenv(
            "RUNPOD_USE_TEMPLATE_WAN22_VIDEO_V2"
        )
        image_to_video_image = os.getenv(
            "RUNPOD_IMAGE_NAME_IMAGE_TO_VIDEO"
        ) or RUNPOD_PUBLIC_WAN22_AIO_VIDEO_RIFE_IMAGE
        wan22_video_v2_image = os.getenv(
            "RUNPOD_IMAGE_NAME_WAN22_VIDEO_V2"
        ) or RUNPOD_PUBLIC_WAN22_AIO_VIDEO_RIFE_IMAGE
        image_to_video_template = os.getenv("RUNPOD_TEMPLATE_ID_IMAGE_TO_VIDEO", "")
        wan22_video_v2_template = os.getenv("RUNPOD_TEMPLATE_ID_WAN22_VIDEO_V2", "")
        wan22_aio_model_prefix = os.getenv(
            "RUNPOD_MODEL_PREFIX_WAN22_AIO_VIDEO",
            global_model_prefix
            if global_model_prefix.startswith("wan22_aio_video/")
            else RUNPOD_WAN22_AIO_VIDEO_MODEL_PREFIX,
        )
        wan22_aio_model_manifest_key = os.getenv(
            "RUNPOD_MODEL_MANIFEST_KEY_WAN22_AIO_VIDEO",
            global_model_manifest_key
            if global_model_manifest_key.startswith("wan22_aio_video/")
            else RUNPOD_WAN22_AIO_VIDEO_MODEL_MANIFEST_KEY,
        )
        return cls(
            api_key=os.getenv("RUNPOD_API_KEY", ""),
            base_url=os.getenv("RUNPOD_API_BASE_URL", RUNPOD_API_BASE_URL).rstrip("/"),
            autoscaler_enabled=_bool_env(
                os.getenv("RUNPOD_AUTOSCALER_ENABLED"),
                default=False,
            ),
            dry_run=_bool_env(os.getenv("RUNPOD_DRY_RUN"), default=True),
            max_pods_total=_int_env(os.getenv("RUNPOD_MAX_PODS_TOTAL"), default=1),
            max_pods_per_type=_int_env(
                os.getenv("RUNPOD_MAX_PODS_PER_TYPE"),
                default=1,
            ),
            max_hourly_cost_usd=_float_env(
                os.getenv("RUNPOD_MAX_HOURLY_COST_USD"),
                default=5.0,
            ),
            projected_cost_per_hr_img2img_lora=_float_env(
                os.getenv("RUNPOD_PROJECTED_COST_PER_HR_IMG2IMG_LORA"),
                default=0.0,
            ),
            projected_cost_per_hr_wan22_aio_video=_float_env(
                os.getenv("RUNPOD_PROJECTED_COST_PER_HR_WAN22_AIO_VIDEO"),
                default=wan22_aio_cost,
            ),
            projected_cost_per_hr_image_to_video=_float_env(
                os.getenv("RUNPOD_PROJECTED_COST_PER_HR_IMAGE_TO_VIDEO"),
                default=wan22_aio_cost,
            ),
            projected_cost_per_hr_wan22_video_v2=_float_env(
                os.getenv("RUNPOD_PROJECTED_COST_PER_HR_WAN22_VIDEO_V2"),
                default=wan22_aio_cost,
            ),
            projected_cost_per_hr_i2i_pro=_float_env(
                os.getenv("RUNPOD_PROJECTED_COST_PER_HR_I2I_PRO"),
                default=0.0,
            ),
            projected_cost_per_hr_scail2=_float_env(
                os.getenv("RUNPOD_PROJECTED_COST_PER_HR_SCAIL2"),
                default=0.0,
            ),
            projected_cost_per_hr_ltx_video=_float_env(
                os.getenv("RUNPOD_PROJECTED_COST_PER_HR_LTX_VIDEO"),
                default=0.0,
            ),
            projected_cost_per_hr_pornmaster_flux2_edit=_float_env(
                os.getenv("RUNPOD_PROJECTED_COST_PER_HR_PORNMASTER_FLUX2_EDIT"),
                default=0.0,
            ),
            cloud_type=os.getenv("RUNPOD_CLOUD_TYPE", "SECURE"),
            interruptible=_bool_env(os.getenv("RUNPOD_INTERRUPTIBLE"), default=False),
            gpu_type_ids_img2img_lora=_csv(
                os.getenv("RUNPOD_GPU_TYPE_IDS_IMG2IMG_LORA"),
                default=cls.gpu_type_ids_img2img_lora,
            ),
            gpu_type_ids_wan22_aio_video=_csv(
                os.getenv("RUNPOD_GPU_TYPE_IDS_WAN22_AIO_VIDEO"),
                default=cls.gpu_type_ids_wan22_aio_video,
            )
            or RUNPOD_WAN22_AIO_VIDEO_GPU_TYPE_IDS,
            gpu_type_ids_image_to_video=_csv(
                os.getenv("RUNPOD_GPU_TYPE_IDS_IMAGE_TO_VIDEO"),
                default=wan22_aio_gpu_type_ids,
            )
            or RUNPOD_WAN22_AIO_VIDEO_GPU_TYPE_IDS,
            gpu_type_ids_wan22_video_v2=_csv(
                os.getenv("RUNPOD_GPU_TYPE_IDS_WAN22_VIDEO_V2"),
                default=wan22_aio_gpu_type_ids,
            )
            or RUNPOD_WAN22_AIO_VIDEO_GPU_TYPE_IDS,
            gpu_type_ids_i2i_pro=_csv(
                os.getenv("RUNPOD_GPU_TYPE_IDS_I2I_PRO"),
                default=cls.gpu_type_ids_i2i_pro,
            )
            or RUNPOD_I2I_PRO_GPU_TYPE_IDS,
            gpu_type_ids_scail2=_csv(
                os.getenv("RUNPOD_GPU_TYPE_IDS_SCAIL2"),
                default=cls.gpu_type_ids_scail2,
            )
            or RUNPOD_SCAIL2_GPU_TYPE_IDS,
            gpu_type_ids_ltx_video=_csv(
                os.getenv("RUNPOD_GPU_TYPE_IDS_LTX_VIDEO"),
                default=cls.gpu_type_ids_ltx_video,
            )
            or RUNPOD_LTX_VIDEO_GPU_TYPE_IDS,
            gpu_type_ids_pornmaster_flux2_edit=_csv(
                os.getenv("RUNPOD_GPU_TYPE_IDS_PORNMASTER_FLUX2_EDIT"),
                default=cls.gpu_type_ids_pornmaster_flux2_edit,
            )
            or RUNPOD_PORNMASTER_FLUX2_EDIT_GPU_TYPE_IDS,
            data_center_ids=_csv(os.getenv("RUNPOD_ALLOWED_DATACENTERS")),
            container_disk_gb=_int_env(
                os.getenv("RUNPOD_CONTAINER_DISK_GB"),
                default=80,
            ),
            container_disk_gb_ltx_video=_int_env(
                os.getenv("RUNPOD_CONTAINER_DISK_GB_LTX_VIDEO"),
                default=RUNPOD_LTX_VIDEO_CONTAINER_DISK_GB,
            ),
            container_disk_gb_pornmaster_flux2_edit=_int_env(
                os.getenv("RUNPOD_CONTAINER_DISK_GB_PORNMASTER_FLUX2_EDIT"),
                default=RUNPOD_PORNMASTER_FLUX2_EDIT_CONTAINER_DISK_GB,
            ),
            volume_gb=_int_env(os.getenv("RUNPOD_VOLUME_GB"), default=0),
            volume_mount_path=os.getenv("RUNPOD_VOLUME_MOUNT_PATH", "/workspace"),
            network_volume_id=os.getenv("RUNPOD_NETWORK_VOLUME_ID", ""),
            pod_ports=_csv(os.getenv("RUNPOD_PORTS")),
            use_template_img2img_lora=_bool_env(
                os.getenv("RUNPOD_USE_TEMPLATE_IMG2IMG_LORA"),
                default=True,
            ),
            use_template_wan22_aio_video=_bool_env(
                os.getenv("RUNPOD_USE_TEMPLATE_WAN22_AIO_VIDEO"),
                default=False,
            ),
            use_template_image_to_video=_bool_env(
                image_to_video_use_template_raw,
                default=False,
            ),
            use_template_wan22_video_v2=_bool_env(
                wan22_video_v2_use_template_raw,
                default=False,
            ),
            use_template_i2i_pro=_bool_env(
                os.getenv("RUNPOD_USE_TEMPLATE_I2I_PRO"),
                default=False,
            ),
            use_template_scail2=_bool_env(
                os.getenv("RUNPOD_USE_TEMPLATE_SCAIL2"),
                default=False,
            ),
            use_template_ltx_video=_bool_env(
                os.getenv("RUNPOD_USE_TEMPLATE_LTX_VIDEO"),
                default=False,
            ),
            use_template_pornmaster_flux2_edit=_bool_env(
                os.getenv("RUNPOD_USE_TEMPLATE_PORNMASTER_FLUX2_EDIT"),
                default=False,
            ),
            docker_start_cmd_img2img_lora=_docker_start_cmd_env(
                os.getenv("RUNPOD_DOCKER_START_CMD_JSON_IMG2IMG_LORA"),
                os.getenv("RUNPOD_DOCKER_START_SCRIPT_IMG2IMG_LORA"),
                os.getenv("RUNPOD_DOCKER_START_SCRIPT_FILE_IMG2IMG_LORA"),
                json_env_name="RUNPOD_DOCKER_START_CMD_JSON_IMG2IMG_LORA",
            )
            or RUNPOD_IMG2IMG_LORA_DOCKER_START_CMD,
            docker_start_cmd_wan22_aio_video=_docker_start_cmd_env(
                os.getenv("RUNPOD_DOCKER_START_CMD_JSON_WAN22_AIO_VIDEO"),
                os.getenv("RUNPOD_DOCKER_START_SCRIPT_WAN22_AIO_VIDEO"),
                os.getenv("RUNPOD_DOCKER_START_SCRIPT_FILE_WAN22_AIO_VIDEO"),
                json_env_name="RUNPOD_DOCKER_START_CMD_JSON_WAN22_AIO_VIDEO",
            ),
            docker_start_cmd_image_to_video=_docker_start_cmd_env(
                os.getenv("RUNPOD_DOCKER_START_CMD_JSON_IMAGE_TO_VIDEO")
                or os.getenv("RUNPOD_DOCKER_START_CMD_JSON_WAN22_AIO_VIDEO"),
                os.getenv("RUNPOD_DOCKER_START_SCRIPT_IMAGE_TO_VIDEO")
                or os.getenv("RUNPOD_DOCKER_START_SCRIPT_WAN22_AIO_VIDEO"),
                os.getenv("RUNPOD_DOCKER_START_SCRIPT_FILE_IMAGE_TO_VIDEO")
                or os.getenv("RUNPOD_DOCKER_START_SCRIPT_FILE_WAN22_AIO_VIDEO"),
                json_env_name="RUNPOD_DOCKER_START_CMD_JSON_IMAGE_TO_VIDEO",
            ),
            docker_start_cmd_wan22_video_v2=_docker_start_cmd_env(
                os.getenv("RUNPOD_DOCKER_START_CMD_JSON_WAN22_VIDEO_V2")
                or os.getenv("RUNPOD_DOCKER_START_CMD_JSON_WAN22_AIO_VIDEO"),
                os.getenv("RUNPOD_DOCKER_START_SCRIPT_WAN22_VIDEO_V2")
                or os.getenv("RUNPOD_DOCKER_START_SCRIPT_WAN22_AIO_VIDEO"),
                os.getenv("RUNPOD_DOCKER_START_SCRIPT_FILE_WAN22_VIDEO_V2")
                or os.getenv("RUNPOD_DOCKER_START_SCRIPT_FILE_WAN22_AIO_VIDEO"),
                json_env_name="RUNPOD_DOCKER_START_CMD_JSON_WAN22_VIDEO_V2",
            ),
            docker_start_cmd_i2i_pro=_docker_start_cmd_env(
                os.getenv("RUNPOD_DOCKER_START_CMD_JSON_I2I_PRO"),
                os.getenv("RUNPOD_DOCKER_START_SCRIPT_I2I_PRO"),
                os.getenv("RUNPOD_DOCKER_START_SCRIPT_FILE_I2I_PRO"),
                json_env_name="RUNPOD_DOCKER_START_CMD_JSON_I2I_PRO",
            ),
            docker_start_cmd_scail2=_docker_start_cmd_env(
                os.getenv("RUNPOD_DOCKER_START_CMD_JSON_SCAIL2"),
                os.getenv("RUNPOD_DOCKER_START_SCRIPT_SCAIL2"),
                os.getenv("RUNPOD_DOCKER_START_SCRIPT_FILE_SCAIL2"),
                json_env_name="RUNPOD_DOCKER_START_CMD_JSON_SCAIL2",
            )
            or RUNPOD_SCAIL2_DOCKER_START_CMD,
            docker_start_cmd_ltx_video=_docker_start_cmd_env(
                os.getenv("RUNPOD_DOCKER_START_CMD_JSON_LTX_VIDEO"),
                os.getenv("RUNPOD_DOCKER_START_SCRIPT_LTX_VIDEO"),
                os.getenv("RUNPOD_DOCKER_START_SCRIPT_FILE_LTX_VIDEO"),
                json_env_name="RUNPOD_DOCKER_START_CMD_JSON_LTX_VIDEO",
            )
            or RUNPOD_LTX_VIDEO_DOCKER_START_CMD,
            docker_start_cmd_pornmaster_flux2_edit=_docker_start_cmd_env(
                os.getenv("RUNPOD_DOCKER_START_CMD_JSON_PORNMASTER_FLUX2_EDIT"),
                os.getenv("RUNPOD_DOCKER_START_SCRIPT_PORNMASTER_FLUX2_EDIT"),
                os.getenv("RUNPOD_DOCKER_START_SCRIPT_FILE_PORNMASTER_FLUX2_EDIT"),
                json_env_name="RUNPOD_DOCKER_START_CMD_JSON_PORNMASTER_FLUX2_EDIT",
            )
            or RUNPOD_PORNMASTER_FLUX2_EDIT_DOCKER_START_CMD,
            template_id_img2img_lora=os.getenv("RUNPOD_TEMPLATE_ID_IMG2IMG_LORA", ""),
            template_id_wan22_aio_video=os.getenv(
                "RUNPOD_TEMPLATE_ID_WAN22_AIO_VIDEO",
                "",
            ),
            template_id_image_to_video=image_to_video_template,
            template_id_wan22_video_v2=wan22_video_v2_template,
            template_id_i2i_pro=os.getenv("RUNPOD_TEMPLATE_ID_I2I_PRO", ""),
            template_id_scail2=os.getenv("RUNPOD_TEMPLATE_ID_SCAIL2", ""),
            template_id_ltx_video=os.getenv("RUNPOD_TEMPLATE_ID_LTX_VIDEO", ""),
            template_id_pornmaster_flux2_edit=os.getenv(
                "RUNPOD_TEMPLATE_ID_PORNMASTER_FLUX2_EDIT",
                "",
            ),
            image_name_img2img_lora=os.getenv("RUNPOD_IMAGE_NAME_IMG2IMG_LORA", ""),
            image_name_wan22_aio_video=wan22_aio_image,
            image_name_image_to_video=image_to_video_image,
            image_name_wan22_video_v2=wan22_video_v2_image,
            image_name_i2i_pro=os.getenv("RUNPOD_IMAGE_NAME_I2I_PRO", ""),
            image_name_scail2=os.getenv("RUNPOD_IMAGE_NAME_SCAIL2", ""),
            image_name_ltx_video=os.getenv("RUNPOD_IMAGE_NAME_LTX_VIDEO", ""),
            image_name_pornmaster_flux2_edit=os.getenv(
                "RUNPOD_IMAGE_NAME_PORNMASTER_FLUX2_EDIT",
                "",
            ),
            worker_central_url_cloud_test=os.getenv(
                "RUNPOD_CLOUD_TEST_CENTRAL_API_URL",
                os.getenv(
                    "RUNPOD_WORKER_CENTRAL_URL_TEST",
                    "https://worker-central-test.example.com",
                ),
            ).rstrip("/"),
            worker_central_url_cloud_prod=os.getenv(
                "RUNPOD_CLOUD_PROD_CENTRAL_API_URL",
                os.getenv(
                    "RUNPOD_WORKER_CENTRAL_URL_PROD",
                    RUNPOD_PROD_WORKER_CENTRAL_URL,
                ),
            ).rstrip("/"),
            prod_agent_id=os.getenv("RUNPOD_PROD_AGENT_ID", RUNPOD_PROD_AGENT_ID),
            prod_supported_task_types=_csv(
                os.getenv("RUNPOD_PROD_SUPPORTED_TASK_TYPES"),
                default=cls.prod_supported_task_types,
            ),
            prod_gpu_type_ids=_csv(
                os.getenv("RUNPOD_PROD_GPU_TYPE_IDS"),
                default=cls.prod_gpu_type_ids,
            )
            or RUNPOD_PROD_GPU_TYPE_IDS,
            prod_max_manual_slots=_prod_max_manual_slots_from_env(),
            prod_node_id=os.getenv("RUNPOD_PROD_NODE_ID", RUNPOD_PROD_NODE_ID),
            prod_bucket=os.getenv("RUNPOD_PROD_BUCKET", RUNPOD_PROD_BUCKET),
            prod_agent_secret_token_ref=os.getenv(
                "RUNPOD_PROD_AGENT_SECRET_TOKEN_REF",
                RUNPOD_PROD_AGENT_SECRET_TOKEN_REF,
            ),
            prod_minio_access_key_ref=os.getenv(
                "RUNPOD_PROD_R2_ACCESS_KEY_REF",
                RUNPOD_PROD_R2_ACCESS_KEY_REF,
            ),
            prod_minio_secret_key_ref=os.getenv(
                "RUNPOD_PROD_R2_SECRET_KEY_REF",
                RUNPOD_PROD_R2_SECRET_KEY_REF,
            ),
            keepalive_on_bootstrap_failure=_bool_env(
                os.getenv("RUNPOD_KEEPALIVE_ON_BOOTSTRAP_FAILURE"),
                default=False,
            ),
            agent_secret_token=os.getenv("AGENT_SECRET_TOKEN", ""),
            minio_endpoint=os.getenv("MINIO_ENDPOINT", ""),
            minio_access_key=os.getenv("MINIO_ACCESS_KEY", ""),
            minio_secret_key=os.getenv("MINIO_SECRET_KEY", ""),
            agent_secret_token_ref=os.getenv(
                "RUNPOD_AGENT_SECRET_TOKEN_REF",
                RUNPOD_AGENT_SECRET_TOKEN_REF,
            ),
            minio_access_key_ref=os.getenv(
                "RUNPOD_R2_ACCESS_KEY_REF",
                RUNPOD_R2_ACCESS_KEY_REF,
            ),
            minio_secret_key_ref=os.getenv(
                "RUNPOD_R2_SECRET_KEY_REF",
                RUNPOD_R2_SECRET_KEY_REF,
            ),
            model_sync_enabled=_bool_env(
                os.getenv("RUNPOD_MODEL_SYNC_ENABLED"),
                default=bool(model_bucket.strip()),
            ),
            model_bucket=model_bucket,
            model_prefix=global_model_prefix,
            model_manifest_key=global_model_manifest_key,
            model_prefix_wan22_aio_video=wan22_aio_model_prefix,
            model_manifest_key_wan22_aio_video=wan22_aio_model_manifest_key,
            model_prefix_image_to_video=os.getenv(
                "RUNPOD_MODEL_PREFIX_IMAGE_TO_VIDEO",
                RUNPOD_IMAGE_TO_VIDEO_MODEL_PREFIX,
            ),
            model_manifest_key_image_to_video=os.getenv(
                "RUNPOD_MODEL_MANIFEST_KEY_IMAGE_TO_VIDEO",
                RUNPOD_IMAGE_TO_VIDEO_MODEL_MANIFEST_KEY,
            ),
            model_prefix_wan22_video_v2=os.getenv(
                "RUNPOD_MODEL_PREFIX_WAN22_VIDEO_V2",
                RUNPOD_WAN22_VIDEO_V2_MODEL_PREFIX,
            ),
            model_manifest_key_wan22_video_v2=os.getenv(
                "RUNPOD_MODEL_MANIFEST_KEY_WAN22_VIDEO_V2",
                RUNPOD_WAN22_VIDEO_V2_MODEL_MANIFEST_KEY,
            ),
            wan22_video_v2_completion_timeout_seconds=_float_env(
                os.getenv("RUNPOD_WAN22_VIDEO_V2_COMPLETION_TIMEOUT_SECONDS"),
                default=RUNPOD_WAN22_VIDEO_V2_COMPLETION_TIMEOUT_SECONDS,
            ),
            wan22_video_v2_exit_on_timeout=_bool_env(
                os.getenv("RUNPOD_WAN22_VIDEO_V2_EXIT_ON_TIMEOUT"),
                default=True,
            ),
            wan22_video_v2_comfy_extra_args=os.getenv(
                "RUNPOD_WAN22_VIDEO_V2_COMFY_EXTRA_ARGS",
                RUNPOD_WAN22_VIDEO_V2_COMFY_EXTRA_ARGS,
            ).strip(),
            model_prefix_i2i_pro=os.getenv(
                "RUNPOD_MODEL_PREFIX_I2I_PRO",
                RUNPOD_I2I_PRO_MODEL_PREFIX,
            ),
            model_manifest_key_i2i_pro=os.getenv(
                "RUNPOD_MODEL_MANIFEST_KEY_I2I_PRO",
                RUNPOD_I2I_PRO_MODEL_MANIFEST_KEY,
            ),
            task_type_workflow_overrides_i2i_pro=os.getenv(
                "RUNPOD_TASK_TYPE_WORKFLOW_OVERRIDES_I2I_PRO",
                RUNPOD_I2I_PRO_WORKFLOW_OVERRIDES,
            ),
            model_prefix_scail2=os.getenv(
                "RUNPOD_MODEL_PREFIX_SCAIL2",
                global_model_prefix
                if global_model_prefix.startswith("scail2/")
                else RUNPOD_SCAIL2_MODEL_PREFIX,
            ),
            model_manifest_key_scail2=os.getenv(
                "RUNPOD_MODEL_MANIFEST_KEY_SCAIL2",
                global_model_manifest_key
                if global_model_manifest_key.startswith("scail2/")
                else RUNPOD_SCAIL2_MODEL_MANIFEST_KEY,
            ),
            model_prefix_ltx_video=os.getenv(
                "RUNPOD_MODEL_PREFIX_LTX_VIDEO",
                global_model_prefix
                if global_model_prefix.startswith("ltx_video/")
                else RUNPOD_LTX_VIDEO_MODEL_PREFIX,
            ),
            model_manifest_key_ltx_video=os.getenv(
                "RUNPOD_MODEL_MANIFEST_KEY_LTX_VIDEO",
                global_model_manifest_key
                if global_model_manifest_key.startswith("ltx_video/")
                else RUNPOD_LTX_VIDEO_MODEL_MANIFEST_KEY,
            ),
            task_type_workflow_overrides_ltx_video=os.getenv(
                "RUNPOD_TASK_TYPE_WORKFLOW_OVERRIDES_LTX_VIDEO",
                RUNPOD_LTX_VIDEO_WORKFLOW_OVERRIDES,
            ),
            model_prefix_pornmaster_flux2_edit=os.getenv(
                "RUNPOD_MODEL_PREFIX_PORNMASTER_FLUX2_EDIT",
                global_model_prefix
                if global_model_prefix.startswith("pornmaster_flux2_edit/")
                else RUNPOD_PORNMASTER_FLUX2_EDIT_MODEL_PREFIX,
            ),
            model_manifest_key_pornmaster_flux2_edit=os.getenv(
                "RUNPOD_MODEL_MANIFEST_KEY_PORNMASTER_FLUX2_EDIT",
                global_model_manifest_key
                if global_model_manifest_key.startswith("pornmaster_flux2_edit/")
                else RUNPOD_PORNMASTER_FLUX2_EDIT_MODEL_MANIFEST_KEY,
            ),
            model_endpoint=os.getenv("RUNPOD_MODEL_ENDPOINT", ""),
            model_secure=_bool_env(os.getenv("RUNPOD_MODEL_SECURE"), default=True),
            model_access_key_ref=os.getenv(
                "RUNPOD_MODEL_ACCESS_KEY_REF",
                os.getenv(
                    "RUNPOD_R2_MODEL_ACCESS_KEY_REF",
                    RUNPOD_MODEL_CACHE_R2_ACCESS_KEY_REF,
                ),
            ),
            model_secret_key_ref=os.getenv(
                "RUNPOD_MODEL_SECRET_KEY_REF",
                os.getenv(
                    "RUNPOD_R2_MODEL_SECRET_KEY_REF",
                    RUNPOD_MODEL_CACHE_R2_SECRET_KEY_REF,
                ),
            ),
            comfy_custom_nodes_enabled=_bool_env(
                os.getenv("RUNPOD_COMFY_CUSTOM_NODES_ENABLED"),
                default=True,
            ),
            comfy_kjnodes_enabled=_bool_env(
                os.getenv("RUNPOD_COMFY_KJNODES_ENABLED"),
                default=True,
            ),
            extra_env=_runpod_extra_env_from_env(),
        )


class RunPodProvider:
    """RunPod Pods provider v0.

    The provider is safe by default: render/list/reconcile are allowed, while
    mutations stay dry-run unless the explicit RunPod gates are opened.
    """

    provider = "runpod"

    def __init__(
        self,
        settings: RunPodSettings | None = None,
        *,
        request_func: Callable[..., Any] | None = None,
    ) -> None:
        self.settings = settings or RunPodSettings.from_env()
        self._request_func = request_func
        self._pod_request_builder = RunPodPodRequestBuilder(self.settings)

    def validate_key(self) -> dict[str, Any]:
        if not self.settings.api_key:
            return {"ok": False, "error": "missing_RUNPOD_API_KEY"}
        try:
            self._request("GET", "/pods", params={"computeType": "GPU"})
        except Exception as exc:
            return {"ok": False, "error": self._safe_error(exc)}
        return {"ok": True, "message": "RunPod API key accepted"}

    def list_pods(
        self,
        *,
        managed_only: bool = True,
        desired_status: str | None = None,
    ) -> dict[str, Any]:
        if not self.settings.api_key:
            return {"ok": False, "error": "missing_RUNPOD_API_KEY", "pods": []}
        params: dict[str, str] = {"computeType": "GPU"}
        if desired_status:
            params["desiredStatus"] = desired_status
        try:
            payload = self._request("GET", "/pods", params=params)
        except Exception as exc:
            return {"ok": False, "error": self._safe_error(exc), "pods": []}
        pods = payload if isinstance(payload, list) else payload.get("pods", [])
        if managed_only:
            pods = [pod for pod in pods if self.is_managed_pod(pod)]
        return {"ok": True, "count": len(pods), "pods": redact_payload(pods)}

    def get_pod(self, *, pod_id: str, redact: bool = True) -> dict[str, Any]:
        if not self.settings.api_key:
            return {"ok": False, "error": "missing_RUNPOD_API_KEY"}
        try:
            payload = self._request(
                "GET",
                f"/pods/{pod_id}",
                params={
                    "includeMachine": "true",
                    "includeTemplate": "true",
                    "includeNetworkVolume": "true",
                },
            )
        except Exception as exc:
            return {"ok": False, "error": self._safe_error(exc)}
        result = {"ok": True, "pod": payload}
        return redact_payload(result) if redact else result

    def pod_readiness(self, *, pod_id: str) -> dict[str, Any]:
        fetched = self.get_pod(pod_id=pod_id, redact=False)
        if not fetched.get("ok"):
            return fetched
        pod = dict(fetched.get("pod") or {})
        readiness = self._pod_readiness_from_payload(
            pod,
            require_port_mappings=bool(self.settings.pod_ports),
        )
        return {
            "ok": True,
            "pod_id": pod.get("id") or pod_id,
            "name": pod.get("name"),
            "desired_status": pod.get("desiredStatus") or pod.get("status"),
            "readiness": readiness,
            "pod": redact_payload(pod),
        }

    def reconcile_managed_pods(
        self,
        pods: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if pods is None:
            listed = self.list_pods(managed_only=True)
            if not listed.get("ok"):
                return listed
            pods = list(listed.get("pods") or [])
        managed = [pod for pod in pods if self.is_managed_pod(pod)]
        by_task_type: dict[str, int] = {}
        by_status: dict[str, int] = {}
        orphans: list[str] = []
        for pod in managed:
            env = pod.get("env") or {}
            task_type = str(env.get("RUNPOD_TASK_TYPE") or "unknown")
            status = str(pod.get("desiredStatus") or pod.get("status") or "unknown")
            by_task_type[task_type] = by_task_type.get(task_type, 0) + 1
            by_status[status] = by_status.get(status, 0) + 1
            if not env.get("RUNPOD_TASK_TYPE") or not env.get("AGENT_ID"):
                pod_id = str(pod.get("id") or pod.get("name") or "unknown")
                orphans.append(pod_id)
        return {
            "ok": True,
            "managed_count": len(managed),
            "by_task_type": by_task_type,
            "by_status": by_status,
            "orphans": orphans,
        }

    def render_create_pod_request(
        self,
        *,
        task_type: str,
        environment: str = "cloud-test",
        redact: bool = True,
    ) -> dict[str, Any]:
        body = self._create_pod_body(task_type=task_type, environment=environment)
        payload = {
            "ok": True,
            "dry_run": True,
            "method": "POST",
            "url": f"{self.settings.base_url}/pods",
            "json": body,
        }
        return redact_payload(payload) if redact else payload

    def create_pod(
        self,
        *,
        task_type: str,
        environment: str = "cloud-test",
        existing_pods: list[dict[str, Any]] | None = None,
        execute: bool = False,
    ) -> dict[str, Any]:
        request = self.render_create_pod_request(
            task_type=task_type,
            environment=environment,
            redact=False,
        )
        if (
            self._should_reconcile_existing_pods(execute=execute)
            and existing_pods is None
        ):
            listed = self.list_pods(managed_only=True)
            if not listed.get("ok"):
                return {
                    "ok": False,
                    "dry_run": True,
                    "action": "create",
                    "execute": execute,
                    "guard": {
                        "allowed": False,
                        "reasons": [
                            str(listed.get("error") or "runpod list-pods failed")
                        ],
                    },
                    "request": redact_payload(request),
                }
            existing_pods = list(listed.get("pods") or [])
        profile = self._profile_for_task_type(task_type)
        projected_cost = self._projected_profile_cost(profile, existing_pods or [])
        guard = self._mutation_guard(
            action="create",
            task_type=profile.task_type,
            existing_pods=existing_pods or [],
            projected_new_cost_per_hr=projected_cost,
        )
        if not execute or not guard["allowed"]:
            return {
                "ok": False if execute and not guard["allowed"] else True,
                "dry_run": True,
                "action": "create",
                "execute": execute,
                "guard": guard,
                "request": redact_payload(request),
            }
        try:
            response = self._request("POST", "/pods", json_body=request["json"])
        except Exception as exc:
            return {
                "ok": False,
                "dry_run": False,
                "action": "create",
                "error": self._safe_error(exc),
            }
        return {"ok": True, "dry_run": False, "pod": redact_payload(response)}

    def start_pod(
        self,
        *,
        pod_id: str,
        task_type: str = "img2img_lora",
        existing_pods: list[dict[str, Any]] | None = None,
        execute: bool = False,
    ) -> dict[str, Any]:
        return self._pod_mutation(
            action="start",
            method="POST",
            path=f"/pods/{pod_id}/start",
            task_type=task_type,
            existing_pods=existing_pods or [],
            execute=execute,
        )

    def stop_pod(
        self,
        *,
        pod_id: str,
        task_type: str = "img2img_lora",
        existing_pods: list[dict[str, Any]] | None = None,
        execute: bool = False,
    ) -> dict[str, Any]:
        return self._pod_mutation(
            action="stop",
            method="POST",
            path=f"/pods/{pod_id}/stop",
            task_type=task_type,
            existing_pods=existing_pods or [],
            execute=execute,
        )

    def restart_pod(
        self,
        *,
        pod_id: str,
        task_type: str = "img2img_lora",
        existing_pods: list[dict[str, Any]] | None = None,
        execute: bool = False,
    ) -> dict[str, Any]:
        return self._pod_mutation(
            action="restart",
            method="POST",
            path=f"/pods/{pod_id}/restart",
            task_type=task_type,
            existing_pods=existing_pods or [],
            execute=execute,
        )

    def delete_pod(
        self,
        *,
        pod_id: str,
        task_type: str = "img2img_lora",
        existing_pods: list[dict[str, Any]] | None = None,
        execute: bool = False,
    ) -> dict[str, Any]:
        return self._pod_mutation(
            action="delete",
            method="DELETE",
            path=f"/pods/{pod_id}",
            task_type=task_type,
            existing_pods=existing_pods or [],
            execute=execute,
        )

    def for_prod_agent_id(self, agent_id: str) -> "RunPodProvider":
        prod_slot_from_agent_id(
            agent_id,
            max_manual_slots=self.settings.prod_max_manual_slots,
        )
        return RunPodProvider(
            replace(self.settings, prod_agent_id=agent_id),
            request_func=self._request_func,
        )

    @staticmethod
    def is_managed_pod(pod: dict[str, Any]) -> bool:
        return _is_managed_pod(pod)

    @classmethod
    def _pod_readiness_from_payload(
        cls,
        pod: dict[str, Any],
        *,
        require_port_mappings: bool = False,
    ) -> dict[str, Any]:
        del cls
        return pod_readiness_from_payload(
            pod,
            require_port_mappings=require_port_mappings,
        )

    @staticmethod
    def _normalized_ports(raw_ports: Any) -> list[str]:
        return normalized_ports(raw_ports)

    def _pod_mutation(
        self,
        *,
        action: str,
        method: str,
        path: str,
        task_type: str,
        existing_pods: list[dict[str, Any]],
        execute: bool,
    ) -> dict[str, Any]:
        if (
            action == "start"
            and self._should_reconcile_existing_pods(execute=execute)
            and not existing_pods
        ):
            listed = self.list_pods(managed_only=True)
            if not listed.get("ok"):
                return {
                    "ok": False,
                    "dry_run": True,
                    "action": action,
                    "execute": execute,
                    "guard": {
                        "allowed": False,
                        "reasons": [
                            str(listed.get("error") or "runpod list-pods failed")
                        ],
                    },
                    "request": {
                        "method": method,
                        "url": f"{self.settings.base_url}{path}",
                    },
                }
            existing_pods = list(listed.get("pods") or [])
        guard = self._mutation_guard(
            action=action,
            task_type=self._profile_for_task_type(task_type).task_type,
            existing_pods=existing_pods,
            projected_new_cost_per_hr=0.0,
        )
        request = {"method": method, "url": f"{self.settings.base_url}{path}"}
        if not execute or not guard["allowed"]:
            return {
                "ok": False if execute and not guard["allowed"] else True,
                "dry_run": True,
                "action": action,
                "execute": execute,
                "guard": guard,
                "request": request,
            }
        try:
            response = self._request(method, path)
        except Exception as exc:
            return {
                "ok": False,
                "dry_run": False,
                "action": action,
                "error": self._safe_error(exc),
            }
        return {
            "ok": True,
            "dry_run": False,
            "action": action,
            "response": redact_payload(response),
        }

    def _should_reconcile_existing_pods(self, *, execute: bool) -> bool:
        return (
            execute
            and not self.settings.dry_run
            and self.settings.autoscaler_enabled
        )

    def _create_pod_body(self, *, task_type: str, environment: str) -> dict[str, Any]:
        return self._pod_request_builder.create_pod_body(
            task_type=task_type,
            environment=environment,
        )

    def _container_disk_gb_for(
        self,
        *,
        profile: RunPodTaskProfile,
        environment: str,
    ) -> int:
        return self._pod_request_builder.container_disk_gb_for(
            profile=profile,
            environment=environment,
        )

    def _pod_env(
        self,
        *,
        profile: RunPodTaskProfile,
        environment: str,
    ) -> dict[str, str]:
        return self._pod_request_builder.pod_env(
            profile=profile,
            environment=environment,
        )

    def _pod_name(self, *, profile: RunPodTaskProfile, environment: str) -> str:
        return self._pod_request_builder.pod_name(
            profile=profile,
            environment=environment,
        )

    def _environment_config(
        self,
        *,
        profile: RunPodTaskProfile,
        environment: str,
    ) -> dict[str, Any]:
        return self._pod_request_builder.environment_config(
            profile=profile,
            environment=environment,
        )

    def _mutation_guard(
        self,
        *,
        action: str,
        task_type: str,
        existing_pods: list[dict[str, Any]],
        projected_new_cost_per_hr: float,
    ) -> dict[str, Any]:
        return self._pod_request_builder.mutation_guard(
            action=action,
            task_type=task_type,
            existing_pods=existing_pods,
            projected_new_cost_per_hr=projected_new_cost_per_hr,
        )

    def _projected_profile_cost(
        self,
        profile: RunPodTaskProfile,
        pods: list[dict[str, Any]],
    ) -> float:
        return self._pod_request_builder.projected_profile_cost(profile, pods)

    def _configured_projected_cost(self, profile: RunPodTaskProfile) -> float:
        return self._pod_request_builder.configured_projected_cost(profile)

    @staticmethod
    def _is_active(pod: dict[str, Any]) -> bool:
        return (
            str(pod.get("desiredStatus") or pod.get("status") or "")
            in RUNPOD_ACTIVE_STATUSES
        )

    @staticmethod
    def _pod_cost(pod: dict[str, Any]) -> float:
        return pod_cost(pod)

    @staticmethod
    def _profile_for_task_type(task_type: str) -> RunPodTaskProfile:
        return RunPodPodRequestBuilder.profile_for_task_type(task_type)

    def _gpu_type_ids_for(self, profile: RunPodTaskProfile) -> tuple[str, ...]:
        return self._pod_request_builder.gpu_type_ids_for(profile)

    def _template_id_for(self, profile: RunPodTaskProfile) -> str:
        return self._pod_request_builder.template_id_for(profile)

    def _image_name_for(self, profile: RunPodTaskProfile) -> str:
        return self._pod_request_builder.image_name_for(profile)

    def _prod_image_name_for(self, profile: RunPodTaskProfile) -> str:
        return self._pod_request_builder.prod_image_name_for(profile)

    @staticmethod
    def _pending_image_name_for(profile: RunPodTaskProfile) -> str:
        return RunPodPodRequestBuilder.pending_image_name_for(profile)

    def _docker_start_cmd_for(self, profile: RunPodTaskProfile) -> tuple[str, ...]:
        return self._pod_request_builder.docker_start_cmd_for(profile)

    def _workflow_overrides_for(self, profile: RunPodTaskProfile) -> str:
        return self._pod_request_builder.workflow_overrides_for(profile)

    def _model_prefix_for(self, profile: RunPodTaskProfile) -> str:
        return self._pod_request_builder.model_prefix_for(profile)

    def _model_manifest_key_for(self, profile: RunPodTaskProfile) -> str:
        return self._pod_request_builder.model_manifest_key_for(profile)

    def _prod_supported_task_types_for(
        self,
        profile: RunPodTaskProfile,
    ) -> tuple[str, ...]:
        return self._pod_request_builder.prod_supported_task_types_for(profile)

    def _prod_model_prefix_for(self, profile: RunPodTaskProfile) -> str:
        return self._pod_request_builder.prod_model_prefix_for(profile)

    def _prod_model_manifest_key_for(
        self,
        profile: RunPodTaskProfile,
        model_prefix: str,
    ) -> str:
        return self._pod_request_builder.prod_model_manifest_key_for(
            profile,
            model_prefix,
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        if not self.settings.api_key:
            raise RunPodProviderError("missing_RUNPOD_API_KEY")
        headers = {
            "Authorization": f"Bearer {self.settings.api_key}",
            "Content-Type": "application/json",
        }
        if self._request_func is not None:
            return self._request_func(
                method,
                path,
                params=params,
                json_body=json_body,
                headers=headers,
            )

        url = f"{self.settings.base_url}{path}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params, doseq=True)}"
        data = None
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers=headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                text = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RunPodProviderError(f"runpod_http_{exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise RunPodProviderError(f"runpod_network_error: {exc.reason}") from exc
        if not text:
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise RunPodProviderError("runpod_invalid_json_response") from exc

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        return redact_text(str(exc))
