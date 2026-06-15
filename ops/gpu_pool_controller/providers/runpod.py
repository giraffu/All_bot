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
RUNPOD_PROD_AGENT_ID_PREFIX = "runpod_prod_img2img_manual_"
RUNPOD_PROD_POD_NAME_PREFIX = "allbot-runpod-prod-img2img-manual-"
RUNPOD_PROD_WAN22_VIDEO_V2_AGENT_ID_PREFIX = "runpod_prod_wan22_video_v2_manual_"
RUNPOD_PROD_WAN22_VIDEO_V2_POD_NAME_PREFIX = "allbot-runpod-prod-wan22-video-v2-manual-"
RUNPOD_PROD_IMAGE_TO_VIDEO_AGENT_ID_PREFIX = "runpod_prod_image_to_video_manual_"
RUNPOD_PROD_IMAGE_TO_VIDEO_POD_NAME_PREFIX = "allbot-runpod-prod-image-to-video-manual-"
RUNPOD_PROD_I2I_PRO_AGENT_ID_PREFIX = "runpod_prod_i2i_pro_manual_"
RUNPOD_PROD_I2I_PRO_POD_NAME_PREFIX = "allbot-runpod-prod-i2i-pro-manual-"
RUNPOD_PROD_DEFAULT_MAX_MANUAL_SLOTS = 2
RUNPOD_PROD_MAX_MANUAL_SLOTS = RUNPOD_PROD_DEFAULT_MAX_MANUAL_SLOTS
RUNPOD_PROD_AGENT_ID = "runpod_prod_img2img_manual_01"
RUNPOD_PROD_NODE_ID = "runpod-cloud-prod"
RUNPOD_PROD_BUCKET = "user-data-prod"
RUNPOD_PROD_SUPPORTED_TASK_TYPES = ("img2img", "img2img_lora")
RUNPOD_PROD_GPU_TYPE_IDS = ("NVIDIA GeForce RTX 4090",)
RUNPOD_PUBLIC_IMG2IMG_LORA_IMAGE = (
    "ghcr.io/giraffu/allbot-comfy-runpod-img2img:20260612-img2img-lora-kjnodes7967a946"
)
RUNPOD_PUBLIC_WAN22_VIDEO_V2_IMAGE_PREFIX = (
    "ghcr.io/giraffu/allbot-comfy-runpod-wan22-aio-video:"
)
RUNPOD_WAN22_AIO_VIDEO_GPU_TYPE_IDS = (
    "NVIDIA GeForce RTX 5090",
    "NVIDIA GeForce RTX 4090",
)
RUNPOD_WAN22_AIO_VIDEO_MODEL_PREFIX = "wan22_aio_video/2026-06-12-test"
RUNPOD_WAN22_AIO_VIDEO_MODEL_MANIFEST_KEY = (
    "wan22_aio_video/2026-06-12-test/manifest.json"
)
RUNPOD_IMAGE_TO_VIDEO_MODEL_PREFIX = "image_to_video/2026-06-13-test"
RUNPOD_IMAGE_TO_VIDEO_MODEL_MANIFEST_KEY = (
    "image_to_video/2026-06-13-test/manifest.json"
)
RUNPOD_WAN22_VIDEO_V2_MODEL_PREFIX = "wan22_video_v2/2026-06-13-test"
RUNPOD_WAN22_VIDEO_V2_MODEL_MANIFEST_KEY = (
    "wan22_video_v2/2026-06-13-test/manifest.json"
)
RUNPOD_WAN22_VIDEO_V2_COMPLETION_TIMEOUT_SECONDS = 600.0
RUNPOD_WAN22_VIDEO_V2_COMFY_EXTRA_ARGS = "--disable-dynamic-vram"
RUNPOD_I2I_PRO_GPU_TYPE_IDS = ("NVIDIA GeForce RTX 4090",)
RUNPOD_I2I_PRO_MODEL_PREFIX = "i2i_pro/2026-06-14-test"
RUNPOD_I2I_PRO_MODEL_MANIFEST_KEY = "i2i_pro/2026-06-14-test/manifest.json"
RUNPOD_I2I_PRO_CONTAINER_DISK_GB = 120
RUNPOD_I2I_PRO_SUPPORTED_TASK_TYPES = (
    "i2i_pro",
    "t2i-pornmaster-turbo",
    "face_swap",
)
RUNPOD_I2I_PRO_WORKFLOW_OVERRIDES = json.dumps(
    {
        "t2i-pornmaster-turbo": "txt2img_from_i2i_pro.json",
        "face_swap": "face_swap_v2.json",
    },
    separators=(",", ":"),
)
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


@dataclass(frozen=True)
class RunPodTaskProfile:
    task_type: str
    supported_task_types: tuple[str, ...]
    runtime_profile: str
    agent_id_prefix: str
    template_env_key: str
    gpu_type_env_key: str
    image_env_key: str


RUNPOD_TASK_PROFILES: dict[str, RunPodTaskProfile] = {
    "img2img_lora": RunPodTaskProfile(
        task_type="img2img_lora",
        supported_task_types=("img2img", "img2img_lora"),
        runtime_profile="img2img_lora",
        agent_id_prefix="runpod_test_img2img_lora",
        template_env_key="RUNPOD_TEMPLATE_ID_IMG2IMG_LORA",
        gpu_type_env_key="RUNPOD_GPU_TYPE_IDS_IMG2IMG_LORA",
        image_env_key="RUNPOD_IMAGE_NAME_IMG2IMG_LORA",
    ),
    "img2img": RunPodTaskProfile(
        task_type="img2img_lora",
        supported_task_types=("img2img", "img2img_lora"),
        runtime_profile="img2img_lora",
        agent_id_prefix="runpod_test_img2img_lora",
        template_env_key="RUNPOD_TEMPLATE_ID_IMG2IMG_LORA",
        gpu_type_env_key="RUNPOD_GPU_TYPE_IDS_IMG2IMG_LORA",
        image_env_key="RUNPOD_IMAGE_NAME_IMG2IMG_LORA",
    ),
    "wan22_aio_video": RunPodTaskProfile(
        task_type="wan22_aio_video",
        supported_task_types=("image_to_video", "wan22_video_v2"),
        runtime_profile="wan22_aio_video",
        agent_id_prefix="runpod_test_wan22_aio_video",
        template_env_key="RUNPOD_TEMPLATE_ID_WAN22_AIO_VIDEO",
        gpu_type_env_key="RUNPOD_GPU_TYPE_IDS_WAN22_AIO_VIDEO",
        image_env_key="RUNPOD_IMAGE_NAME_WAN22_AIO_VIDEO",
    ),
    "image_to_video": RunPodTaskProfile(
        task_type="image_to_video",
        supported_task_types=("image_to_video",),
        runtime_profile="image_to_video",
        agent_id_prefix="runpod_test_image_to_video",
        template_env_key="RUNPOD_TEMPLATE_ID_IMAGE_TO_VIDEO",
        gpu_type_env_key="RUNPOD_GPU_TYPE_IDS_IMAGE_TO_VIDEO",
        image_env_key="RUNPOD_IMAGE_NAME_IMAGE_TO_VIDEO",
    ),
    "wan22_video_v2": RunPodTaskProfile(
        task_type="wan22_video_v2",
        supported_task_types=("wan22_video_v2",),
        runtime_profile="wan22_video_v2",
        agent_id_prefix="runpod_test_wan22_video_v2",
        template_env_key="RUNPOD_TEMPLATE_ID_WAN22_VIDEO_V2",
        gpu_type_env_key="RUNPOD_GPU_TYPE_IDS_WAN22_VIDEO_V2",
        image_env_key="RUNPOD_IMAGE_NAME_WAN22_VIDEO_V2",
    ),
    "i2i_pro": RunPodTaskProfile(
        task_type="i2i_pro",
        supported_task_types=RUNPOD_I2I_PRO_SUPPORTED_TASK_TYPES,
        runtime_profile="i2i_pro",
        agent_id_prefix="runpod_test_i2i_pro",
        template_env_key="RUNPOD_TEMPLATE_ID_I2I_PRO",
        gpu_type_env_key="RUNPOD_GPU_TYPE_IDS_I2I_PRO",
        image_env_key="RUNPOD_IMAGE_NAME_I2I_PRO",
    ),
}


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


def prod_agent_id_from_slot(
    slot: str | int,
    *,
    max_manual_slots: int | None = None,
    profile: str | None = "img2img",
) -> str:
    normalized = _normalize_prod_worker_slot(
        slot,
        max_manual_slots=max_manual_slots,
    )
    return f"{_prod_agent_id_prefix_for(profile)}{normalized}"


def prod_slot_from_agent_id(
    agent_id: str,
    *,
    max_manual_slots: int | None = None,
    profile: str | None = None,
) -> str:
    profile_key = (
        _prod_profile_from_agent_id(agent_id)
        if profile is None
        else normalize_prod_worker_profile(profile)
    )
    prefix = _prod_agent_id_prefix_for(profile_key)
    if not agent_id.startswith(prefix):
        raise ValueError(f"prod RunPod {profile_key} agent_id must start with {prefix}")
    return _normalize_prod_worker_slot(
        agent_id.removeprefix(prefix),
        max_manual_slots=max_manual_slots,
    )


def prod_pod_name_from_agent_id(
    agent_id: str,
    *,
    max_manual_slots: int | None = None,
    profile: str | None = None,
) -> str:
    profile_key = (
        _prod_profile_from_agent_id(agent_id)
        if profile is None
        else normalize_prod_worker_profile(profile)
    )
    slot = prod_slot_from_agent_id(
        agent_id,
        max_manual_slots=max_manual_slots,
        profile=profile_key,
    )
    return f"{_prod_pod_name_prefix_for(profile_key)}{slot}"


def normalize_prod_worker_profile(profile: str | None) -> str:
    value = (profile or "img2img").strip().lower()
    if value in {"img2img", "img2img_lora"}:
        return "img2img"
    if value == "image_to_video":
        return "image_to_video"
    if value == "wan22_video_v2":
        return "wan22_video_v2"
    if value == "i2i_pro":
        return "i2i_pro"
    raise ValueError(
        "prod RunPod profile must be img2img, image_to_video, "
        "wan22_video_v2, or i2i_pro"
    )


def prod_worker_profile_for_task_type(task_type: str) -> str:
    value = str(task_type or "").strip()
    if value in {"img2img", "img2img_lora"}:
        return "img2img"
    if value == "image_to_video":
        return "image_to_video"
    if value == "wan22_video_v2":
        return "wan22_video_v2"
    if value in RUNPOD_I2I_PRO_SUPPORTED_TASK_TYPES:
        return "i2i_pro"
    raise ValueError(
        "prod RunPod worker only supports img2img, image_to_video, "
        "wan22_video_v2, or i2i_pro"
    )


def prod_worker_profile_from_agent_id(agent_id: str) -> str:
    return _prod_profile_from_agent_id(agent_id)


def _prod_profile_from_agent_id(agent_id: str) -> str:
    raw = str(agent_id or "")
    if raw.startswith(RUNPOD_PROD_AGENT_ID_PREFIX):
        return "img2img"
    if raw.startswith(RUNPOD_PROD_IMAGE_TO_VIDEO_AGENT_ID_PREFIX):
        return "image_to_video"
    if raw.startswith(RUNPOD_PROD_WAN22_VIDEO_V2_AGENT_ID_PREFIX):
        return "wan22_video_v2"
    if raw.startswith(RUNPOD_PROD_I2I_PRO_AGENT_ID_PREFIX):
        return "i2i_pro"
    raise ValueError(
        "prod RunPod agent_id must start with one of "
        f"{RUNPOD_PROD_AGENT_ID_PREFIX}, "
        f"{RUNPOD_PROD_IMAGE_TO_VIDEO_AGENT_ID_PREFIX}, "
        f"{RUNPOD_PROD_WAN22_VIDEO_V2_AGENT_ID_PREFIX}, "
        f"{RUNPOD_PROD_I2I_PRO_AGENT_ID_PREFIX}"
    )


def _prod_agent_id_prefix_for(profile: str | None) -> str:
    profile_key = normalize_prod_worker_profile(profile)
    if profile_key == "image_to_video":
        return RUNPOD_PROD_IMAGE_TO_VIDEO_AGENT_ID_PREFIX
    if profile_key == "wan22_video_v2":
        return RUNPOD_PROD_WAN22_VIDEO_V2_AGENT_ID_PREFIX
    if profile_key == "i2i_pro":
        return RUNPOD_PROD_I2I_PRO_AGENT_ID_PREFIX
    return RUNPOD_PROD_AGENT_ID_PREFIX


def _prod_pod_name_prefix_for(profile: str | None) -> str:
    profile_key = normalize_prod_worker_profile(profile)
    if profile_key == "image_to_video":
        return RUNPOD_PROD_IMAGE_TO_VIDEO_POD_NAME_PREFIX
    if profile_key == "wan22_video_v2":
        return RUNPOD_PROD_WAN22_VIDEO_V2_POD_NAME_PREFIX
    if profile_key == "i2i_pro":
        return RUNPOD_PROD_I2I_PRO_POD_NAME_PREFIX
    return RUNPOD_PROD_POD_NAME_PREFIX


def _normalize_prod_worker_slot(
    slot: str | int,
    *,
    max_manual_slots: int | None = None,
) -> str:
    raw = str(slot).strip()
    if not raw:
        raise ValueError("prod RunPod slot is required")
    if not raw.isdigit():
        raise ValueError("prod RunPod slot must be numeric")
    value = int(raw, 10)
    max_slots = (
        max_manual_slots
        if max_manual_slots is not None
        else _prod_max_manual_slots_from_env()
    )
    if value < 1 or value > max_slots:
        raise ValueError(f"prod RunPod slot must be between 01 and {max_slots:02d}")
    return f"{value:02d}"


def _prod_max_manual_slots_from_env() -> int:
    return _int_env(
        os.getenv("RUNPOD_PROD_MAX_MANUAL_SLOTS"),
        default=RUNPOD_PROD_DEFAULT_MAX_MANUAL_SLOTS,
    )


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
    data_center_ids: tuple[str, ...] = ()
    container_disk_gb: int = 80
    volume_gb: int = 0
    volume_mount_path: str = "/workspace"
    network_volume_id: str = ""
    pod_ports: tuple[str, ...] = ()
    use_template_img2img_lora: bool = True
    use_template_wan22_aio_video: bool = False
    use_template_image_to_video: bool = False
    use_template_wan22_video_v2: bool = False
    use_template_i2i_pro: bool = False
    docker_start_cmd_img2img_lora: tuple[str, ...] = ()
    docker_start_cmd_wan22_aio_video: tuple[str, ...] = ()
    docker_start_cmd_image_to_video: tuple[str, ...] = ()
    docker_start_cmd_wan22_video_v2: tuple[str, ...] = ()
    docker_start_cmd_i2i_pro: tuple[str, ...] = ()
    template_id_img2img_lora: str = ""
    template_id_wan22_aio_video: str = ""
    template_id_image_to_video: str = ""
    template_id_wan22_video_v2: str = ""
    template_id_i2i_pro: str = ""
    image_name_img2img_lora: str = ""
    image_name_wan22_aio_video: str = ""
    image_name_image_to_video: str = ""
    image_name_wan22_video_v2: str = ""
    image_name_i2i_pro: str = ""
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
    bootstrap_git_url: str = "https://github.com/giraffu/All_bot.git"
    bootstrap_git_branch: str = "deploy"
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
        wan22_aio_use_template_raw = os.getenv("RUNPOD_USE_TEMPLATE_WAN22_AIO_VIDEO")
        wan22_aio_image = os.getenv("RUNPOD_IMAGE_NAME_WAN22_AIO_VIDEO", "")
        wan22_aio_template = os.getenv("RUNPOD_TEMPLATE_ID_WAN22_AIO_VIDEO", "")
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
            "RUNPOD_USE_TEMPLATE_IMAGE_TO_VIDEO",
            wan22_aio_use_template_raw,
        )
        wan22_video_v2_use_template_raw = os.getenv(
            "RUNPOD_USE_TEMPLATE_WAN22_VIDEO_V2",
            wan22_aio_use_template_raw,
        )
        image_to_video_image = os.getenv(
            "RUNPOD_IMAGE_NAME_IMAGE_TO_VIDEO",
            wan22_aio_image,
        )
        wan22_video_v2_image = os.getenv(
            "RUNPOD_IMAGE_NAME_WAN22_VIDEO_V2",
            wan22_aio_image,
        )
        image_to_video_template = os.getenv(
            "RUNPOD_TEMPLATE_ID_IMAGE_TO_VIDEO",
            wan22_aio_template,
        )
        wan22_video_v2_template = os.getenv(
            "RUNPOD_TEMPLATE_ID_WAN22_VIDEO_V2",
            wan22_aio_template,
        )
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
            data_center_ids=_csv(os.getenv("RUNPOD_ALLOWED_DATACENTERS")),
            container_disk_gb=_int_env(
                os.getenv("RUNPOD_CONTAINER_DISK_GB"),
                default=80,
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
            docker_start_cmd_img2img_lora=_docker_start_cmd_env(
                os.getenv("RUNPOD_DOCKER_START_CMD_JSON_IMG2IMG_LORA"),
                os.getenv("RUNPOD_DOCKER_START_SCRIPT_IMG2IMG_LORA"),
                os.getenv("RUNPOD_DOCKER_START_SCRIPT_FILE_IMG2IMG_LORA"),
                json_env_name="RUNPOD_DOCKER_START_CMD_JSON_IMG2IMG_LORA",
            ),
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
            template_id_img2img_lora=os.getenv("RUNPOD_TEMPLATE_ID_IMG2IMG_LORA", ""),
            template_id_wan22_aio_video=os.getenv(
                "RUNPOD_TEMPLATE_ID_WAN22_AIO_VIDEO",
                "",
            ),
            template_id_image_to_video=image_to_video_template,
            template_id_wan22_video_v2=wan22_video_v2_template,
            template_id_i2i_pro=os.getenv("RUNPOD_TEMPLATE_ID_I2I_PRO", ""),
            image_name_img2img_lora=os.getenv("RUNPOD_IMAGE_NAME_IMG2IMG_LORA", ""),
            image_name_wan22_aio_video=wan22_aio_image,
            image_name_image_to_video=image_to_video_image,
            image_name_wan22_video_v2=wan22_video_v2_image,
            image_name_i2i_pro=os.getenv("RUNPOD_IMAGE_NAME_I2I_PRO", ""),
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
            bootstrap_git_url=os.getenv(
                "RUNPOD_BOOTSTRAP_GIT_URL",
                "https://github.com/giraffu/All_bot.git",
            ),
            bootstrap_git_branch=os.getenv("RUNPOD_BOOTSTRAP_GIT_BRANCH", "deploy"),
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
        env = pod.get("env") or {}
        name = str(pod.get("name") or "")
        return (
            str(env.get("RUNPOD_MANAGED", "")).strip().lower() == "true"
            or str(env.get("ALLBOT_RUNPOD_MANAGED", "")).strip().lower() == "true"
            or name.startswith("allbot-")
        )

    @classmethod
    def _pod_readiness_from_payload(
        cls,
        pod: dict[str, Any],
        *,
        require_port_mappings: bool = False,
    ) -> dict[str, Any]:
        desired_status = str(pod.get("desiredStatus") or pod.get("status") or "")
        ports = cls._normalized_ports(pod.get("ports"))
        port_mappings = pod.get("portMappings") or {}
        public_ip = str(pod.get("publicIp") or "")
        machine = pod.get("machine") or {}
        reasons: list[str] = []
        exposed_ports = bool(ports)
        tcp_ports = [port for port in ports if port.endswith("/tcp")]
        public_ip_expected = (
            str(pod.get("cloudType") or "").upper() == "SECURE"
            or machine.get("secureCloud") is True
            or machine.get("supportPublicIp") is True
        )
        public_ip_present = bool(public_ip.strip())
        port_mappings_present = bool(port_mappings)

        if desired_status != "RUNNING":
            reasons.append("desired_status_not_running")
        # AllBot RunPod workers only need outbound access to Central. RunPod may
        # reflect Dockerfile EXPOSE ports even when we did not ask for public
        # port mappings, so only require public IP/mappings for explicit ports.
        if require_port_mappings and public_ip_expected and not public_ip_present:
            reasons.append("public_ip_missing")
        if require_port_mappings and not port_mappings_present:
            reasons.append("port_mappings_empty_for_exposed_ports")
        if require_port_mappings and tcp_ports and not public_ip_present:
            reasons.append("public_ip_missing_for_tcp_ports")

        confidence = "status_only_no_exposed_ports"
        if require_port_mappings:
            confidence = (
                "network_mapping_confirmed"
                if not reasons
                else "initializing_or_unmapped"
            )
        elif exposed_ports:
            confidence = "status_only_with_image_exposed_ports"

        network = {
            "public_ip_expected": public_ip_expected,
            "public_ip_present": public_ip_present,
            "exposed_ports": ports,
            "tcp_ports": tcp_ports,
            "port_mappings_present": port_mappings_present,
            "port_mappings": port_mappings,
        }

        return {
            "infrastructure_ready": not reasons,
            "confidence": confidence,
            "reasons": reasons,
            "network": network,
            "signals": {
                "desired_status": desired_status or "unknown",
                **network,
            },
            "notes": [
                "RunPod REST Pod schema does not expose uptimeSeconds; do not infer readiness from a missing uptime field.",
                "For AllBot business readiness, verify the expected runpod_test_* heartbeat in cloud-test Central /system/workers.",
            ],
        }

    @staticmethod
    def _normalized_ports(raw_ports: Any) -> list[str]:
        if raw_ports is None:
            return []
        if isinstance(raw_ports, str):
            return [item.strip() for item in raw_ports.split(",") if item.strip()]
        if isinstance(raw_ports, list):
            return [str(item).strip() for item in raw_ports if str(item).strip()]
        return []

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
            and self.settings.max_pods_total >= 1
            and 1
            <= self.settings.max_pods_per_type
            <= self.settings.prod_max_manual_slots
        )

    def _create_pod_body(self, *, task_type: str, environment: str) -> dict[str, Any]:
        if environment not in {"cloud-test", "cloud-prod"}:
            raise ValueError(
                "RunPodProvider v0 only supports environment=cloud-test/cloud-prod"
            )
        profile = self._profile_for_task_type(task_type)
        if environment == "cloud-prod":
            prod_profile = prod_worker_profile_for_task_type(profile.task_type)
            prod_slot_from_agent_id(
                self.settings.prod_agent_id,
                max_manual_slots=self.settings.prod_max_manual_slots,
                profile=prod_profile,
            )
        if environment == "cloud-prod" and profile.task_type not in {
            "img2img_lora",
            "image_to_video",
            "wan22_video_v2",
            "i2i_pro",
        }:
            raise ValueError(
                "RunPodProvider v0 cloud-prod only supports "
                "img2img/img2img_lora, image_to_video, wan22_video_v2, "
                "and i2i_pro profiles"
            )
        gpu_type_ids = (
            self.settings.prod_gpu_type_ids
            if environment == "cloud-prod"
            else self._gpu_type_ids_for(profile)
        )
        template_id = (
            "" if environment == "cloud-prod" else self._template_id_for(profile)
        )
        image_name = self._image_name_for(profile)
        if (
            environment == "cloud-prod"
            and profile.task_type == "img2img_lora"
            and not image_name
        ):
            image_name = RUNPOD_PUBLIC_IMG2IMG_LORA_IMAGE
        if (
            environment == "cloud-prod"
            and profile.task_type
            in {
                "image_to_video",
                "wan22_video_v2",
                "i2i_pro",
            }
            and not image_name
        ):
            raise ValueError(f"{profile.image_env_key} is required for cloud-prod")
        if not template_id and not image_name:
            image_name = self._pending_image_name_for(profile)
        body: dict[str, Any] = {
            "name": self._pod_name(profile=profile, environment=environment),
            "cloudType": self.settings.cloud_type,
            "computeType": "GPU",
            "gpuCount": 1,
            "gpuTypeIds": list(gpu_type_ids),
            "gpuTypePriority": "availability",
            "containerDiskInGb": self._container_disk_gb_for(
                profile=profile,
                environment=environment,
            ),
            "volumeMountPath": self.settings.volume_mount_path,
            "interruptible": self.settings.interruptible,
            "env": self._pod_env(profile=profile, environment=environment),
        }
        if self.settings.network_volume_id:
            body["networkVolumeId"] = self.settings.network_volume_id
        else:
            body["volumeInGb"] = self.settings.volume_gb
        if self.settings.data_center_ids:
            body["dataCenterIds"] = list(self.settings.data_center_ids)
            body["dataCenterPriority"] = "availability"
        if template_id:
            body["templateId"] = template_id
        else:
            body["imageName"] = image_name
        if self.settings.pod_ports:
            body["ports"] = list(self.settings.pod_ports)
        docker_start_cmd = self._docker_start_cmd_for(profile)
        if docker_start_cmd:
            body["dockerStartCmd"] = list(docker_start_cmd)
        return body

    def _container_disk_gb_for(
        self,
        *,
        profile: RunPodTaskProfile,
        environment: str,
    ) -> int:
        if profile.task_type == "i2i_pro":
            return max(
                self.settings.container_disk_gb, RUNPOD_I2I_PRO_CONTAINER_DISK_GB
            )
        return self.settings.container_disk_gb

    def _pod_env(
        self,
        *,
        profile: RunPodTaskProfile,
        environment: str,
    ) -> dict[str, str]:
        env_config = self._environment_config(profile=profile, environment=environment)
        env = {
            "ENVIRONMENT": env_config["app_environment"],
            "RUNPOD_MANAGED": "true",
            "ALLBOT_RUNPOD_MANAGED": "true",
            "RUNPOD_ENVIRONMENT": environment,
            "RUNPOD_TASK_TYPE": profile.task_type,
            "ALLBOT_RUNPOD_GIT_URL": self.settings.bootstrap_git_url,
            "ALLBOT_RUNPOD_GIT_BRANCH": self.settings.bootstrap_git_branch,
            "AGENT_ID_PREFIX": profile.agent_id_prefix,
            "AGENT_ID": f"{profile.agent_id_prefix}_${{RUNPOD_POD_ID:-pending}}",
            "ALLBOT_RUNPOD_ROOT": f"{self.settings.volume_mount_path.rstrip('/')}/allbot",
            "RUNPOD_WORKSPACE_DIR": self.settings.volume_mount_path,
            "RUNPOD_VOLUME_COMFYUI_DIR": f"{self.settings.volume_mount_path.rstrip('/')}/ComfyUI",
            "RUNPOD_PREPARE_COMFYUI_ON_VOLUME": (
                "true" if self.settings.network_volume_id else "false"
            ),
            "RUNPOD_KEEPALIVE_ON_BOOTSTRAP_FAILURE": (
                "true"
                if environment != "cloud-prod"
                and self.settings.keepalive_on_bootstrap_failure
                else "false"
            ),
            "RUNPOD_START_SSHD": env_config["start_sshd"],
            "RUNPOD_INSTALL_SSHD_IF_MISSING": env_config["install_sshd_if_missing"],
            "AGENT_SECRET_TOKEN": env_config["agent_secret_token_ref"],
            "CENTRAL_API_URL": env_config["central_api_url"],
            "MASTER_API_URL": "http://127.0.0.1:8013",
            "UPLOAD_SIDECAR_URL": "http://127.0.0.1:8013",
            "LOCAL_RELAY_HOST": "127.0.0.1",
            "LOCAL_RELAY_PORT": "8013",
            "SUPPORTED_TASK_TYPES": ",".join(env_config["supported_task_types"]),
            "POOL_MANAGED": "true",
            "POOL_PROVIDER": "runpod",
            "POOL_NODE_ID": env_config["node_id"],
            "POOL_GPU_INDEX": "0",
            "POOL_RUNTIME_PROFILE": profile.runtime_profile,
            "COMFY_API_URL": "http://127.0.0.1:8188",
            "COMFY_WS_URL": "ws://127.0.0.1:8188/ws",
            "COMFY_INPUT_DIR": "./input",
            "COMFY_OUTPUT_DIR": "./output",
            "MINIO_ENDPOINT": self.settings.minio_endpoint
            or "<RUNPOD_SECRET:MINIO_ENDPOINT>",
            "MINIO_ACCESS_KEY": env_config["minio_access_key_ref"],
            "MINIO_SECRET_KEY": env_config["minio_secret_key_ref"],
            "MINIO_BUCKET": env_config["bucket"],
            "MINIO_INPUT_BUCKET": env_config["bucket"],
            "MINIO_RESULT_BUCKET": env_config["bucket"],
            "MINIO_TEMPLATE_BUCKET": env_config["bucket"],
            "MINIO_SECURE": "true",
            "RUNPOD_MODEL_SYNC_ENABLED": (
                "true" if env_config["model_sync_enabled"] else "false"
            ),
            "RUNPOD_MODEL_BUCKET": env_config["model_bucket"],
            "RUNPOD_MODEL_PREFIX": env_config["model_prefix"],
            "RUNPOD_MODEL_MANIFEST_KEY": env_config["model_manifest_key"],
            "RUNPOD_MODEL_ENDPOINT": self.settings.model_endpoint
            or self.settings.minio_endpoint,
            "RUNPOD_MODEL_ACCESS_KEY": env_config["model_access_key_ref"],
            "RUNPOD_MODEL_SECRET_KEY": env_config["model_secret_key_ref"],
            "RUNPOD_MODEL_SECURE": "true" if self.settings.model_secure else "false",
            "RUNPOD_COMFY_CUSTOM_NODES_ENABLED": (
                "true" if env_config["comfy_custom_nodes_enabled"] else "false"
            ),
            "RUNPOD_COMFY_KJNODES_ENABLED": (
                "true" if env_config["comfy_kjnodes_enabled"] else "false"
            ),
            "PIPELINE_ENABLED": "true",
            "PIPELINE_MAX_RUNNING_TASKS": "1",
            "CANCEL_LOCK_ON_POP": "true",
            "PREFETCH_ENABLED": "false",
        }
        if environment == "cloud-prod":
            env["AGENT_ID"] = env_config["agent_id"]
            env["AGENT_ID_PREFIX"] = env_config["agent_id"]
            env["POOL_IMAGE_REF"] = self._prod_image_name_for(profile)
        if profile.task_type == "wan22_video_v2":
            env["WAN22_VIDEO_V2_COMPLETION_TIMEOUT_SECONDS"] = _format_seconds_env(
                self.settings.wan22_video_v2_completion_timeout_seconds
            )
            env["WAN22_VIDEO_V2_EXIT_ON_TIMEOUT"] = (
                "true" if self.settings.wan22_video_v2_exit_on_timeout else "false"
            )
            if self.settings.wan22_video_v2_comfy_extra_args:
                env["COMFY_EXTRA_ARGS"] = self.settings.wan22_video_v2_comfy_extra_args
        workflow_overrides = self._workflow_overrides_for(profile)
        if workflow_overrides:
            env["TASK_TYPE_WORKFLOW_OVERRIDES"] = workflow_overrides
        env.update(self.settings.extra_env)
        return env

    def _pod_name(self, *, profile: RunPodTaskProfile, environment: str) -> str:
        if environment == "cloud-prod":
            return prod_pod_name_from_agent_id(
                self.settings.prod_agent_id,
                max_manual_slots=self.settings.prod_max_manual_slots,
                profile=prod_worker_profile_for_task_type(profile.task_type),
            )
        return f"allbot-runpod-test-{profile.runtime_profile.replace('_', '-')}"

    def _environment_config(
        self,
        *,
        profile: RunPodTaskProfile,
        environment: str,
    ) -> dict[str, Any]:
        if environment == "cloud-test":
            return {
                "app_environment": "test",
                "agent_id": f"{profile.agent_id_prefix}_${{RUNPOD_POD_ID:-pending}}",
                "central_api_url": self.settings.worker_central_url_cloud_test,
                "supported_task_types": profile.supported_task_types,
                "bucket": "user-data-test",
                "node_id": "runpod-cloud-test",
                "agent_secret_token_ref": self.settings.agent_secret_token_ref,
                "minio_access_key_ref": self.settings.minio_access_key_ref,
                "minio_secret_key_ref": self.settings.minio_secret_key_ref,
                "start_sshd": "true",
                "install_sshd_if_missing": "true",
                "model_sync_enabled": self.settings.model_sync_enabled,
                "model_bucket": self.settings.model_bucket,
                "model_prefix": self._model_prefix_for(profile),
                "model_manifest_key": self._model_manifest_key_for(profile),
                "model_access_key_ref": self.settings.model_access_key_ref,
                "model_secret_key_ref": self.settings.model_secret_key_ref,
                "comfy_custom_nodes_enabled": self.settings.comfy_custom_nodes_enabled,
                "comfy_kjnodes_enabled": self.settings.comfy_kjnodes_enabled,
            }
        if environment == "cloud-prod":
            model_prefix = self._prod_model_prefix_for(profile)
            model_manifest_key = self._prod_model_manifest_key_for(
                profile, model_prefix
            )
            return {
                "app_environment": "prod",
                "agent_id": self.settings.prod_agent_id,
                "central_api_url": self.settings.worker_central_url_cloud_prod,
                "supported_task_types": self._prod_supported_task_types_for(profile),
                "bucket": self.settings.prod_bucket,
                "node_id": self.settings.prod_node_id,
                "agent_secret_token_ref": self.settings.prod_agent_secret_token_ref,
                "minio_access_key_ref": self.settings.prod_minio_access_key_ref,
                "minio_secret_key_ref": self.settings.prod_minio_secret_key_ref,
                "start_sshd": "false",
                "install_sshd_if_missing": "false",
                "model_sync_enabled": True,
                "model_bucket": self.settings.model_bucket or "allbot-model-cache",
                "model_prefix": model_prefix,
                "model_manifest_key": model_manifest_key,
                "model_access_key_ref": self.settings.model_access_key_ref,
                "model_secret_key_ref": self.settings.model_secret_key_ref,
                "comfy_custom_nodes_enabled": False,
                "comfy_kjnodes_enabled": False,
            }
        raise ValueError(
            "RunPodProvider v0 only supports environment=cloud-test/cloud-prod"
        )

    def _mutation_guard(
        self,
        *,
        action: str,
        task_type: str,
        existing_pods: list[dict[str, Any]],
        projected_new_cost_per_hr: float,
    ) -> dict[str, Any]:
        reasons: list[str] = []
        if self.settings.dry_run:
            reasons.append("RUNPOD_DRY_RUN=true")
        if not self.settings.autoscaler_enabled:
            reasons.append("RUNPOD_AUTOSCALER_ENABLED=false")
        max_manual_slots = self.settings.prod_max_manual_slots
        if self.settings.max_pods_total < 1:
            reasons.append("RUNPOD_MAX_PODS_TOTAL must be >= 1 for v0")
        if not 1 <= self.settings.max_pods_per_type <= max_manual_slots:
            reasons.append(
                "RUNPOD_MAX_PODS_PER_TYPE must be between "
                f"1 and {max_manual_slots} for v0"
            )
        if self.settings.max_pods_per_type > self.settings.max_pods_total:
            reasons.append(
                "RUNPOD_MAX_PODS_PER_TYPE must not exceed RUNPOD_MAX_PODS_TOTAL"
            )

        if action in {"create", "start"}:
            active = [pod for pod in existing_pods if self._is_active(pod)]
            active_same_type = [
                pod
                for pod in active
                if str((pod.get("env") or {}).get("RUNPOD_TASK_TYPE") or "")
                == task_type
            ]
            if len(active) >= self.settings.max_pods_total:
                reasons.append("runpod active pod total limit reached")
            if len(active_same_type) >= self.settings.max_pods_per_type:
                reasons.append(f"runpod active pod limit reached for {task_type}")
            current_cost = sum(self._pod_cost(pod) for pod in active)
            if (
                current_cost + projected_new_cost_per_hr
                > self.settings.max_hourly_cost_usd
            ):
                reasons.append("RUNPOD_MAX_HOURLY_COST_USD would be exceeded")

        return {
            "allowed": not reasons,
            "reasons": reasons,
            "settings": {
                "dry_run": self.settings.dry_run,
                "autoscaler_enabled": self.settings.autoscaler_enabled,
                "max_pods_total": self.settings.max_pods_total,
                "max_pods_per_type": self.settings.max_pods_per_type,
                "max_hourly_cost_usd": self.settings.max_hourly_cost_usd,
                "projected_new_cost_per_hr": projected_new_cost_per_hr,
            },
        }

    def _projected_profile_cost(
        self,
        profile: RunPodTaskProfile,
        pods: list[dict[str, Any]],
    ) -> float:
        configured = self._configured_projected_cost(profile)
        if configured > 0:
            return configured
        costs = [self._pod_cost(pod) for pod in pods if self._pod_cost(pod) > 0]
        return costs[0] if costs else 0.0

    def _configured_projected_cost(self, profile: RunPodTaskProfile) -> float:
        if profile.task_type == "img2img_lora":
            return self.settings.projected_cost_per_hr_img2img_lora
        if profile.task_type == "wan22_aio_video":
            return self.settings.projected_cost_per_hr_wan22_aio_video
        if profile.task_type == "image_to_video":
            return self.settings.projected_cost_per_hr_image_to_video
        if profile.task_type == "wan22_video_v2":
            return self.settings.projected_cost_per_hr_wan22_video_v2
        if profile.task_type == "i2i_pro":
            return self.settings.projected_cost_per_hr_i2i_pro
        return 0.0

    @staticmethod
    def _is_active(pod: dict[str, Any]) -> bool:
        return (
            str(pod.get("desiredStatus") or pod.get("status") or "")
            in RUNPOD_ACTIVE_STATUSES
        )

    @staticmethod
    def _pod_cost(pod: dict[str, Any]) -> float:
        for key in ("adjustedCostPerHr", "costPerHr"):
            raw = pod.get(key)
            if raw is None:
                continue
            try:
                return float(raw)
            except (TypeError, ValueError):
                continue
        return 0.0

    @staticmethod
    def _profile_for_task_type(task_type: str) -> RunPodTaskProfile:
        try:
            return RUNPOD_TASK_PROFILES[task_type]
        except KeyError as exc:
            raise ValueError(
                "RunPodProvider v0 only supports "
                "img2img_lora/img2img/wan22_aio_video/image_to_video/"
                "wan22_video_v2/i2i_pro profiles"
            ) from exc

    def _gpu_type_ids_for(self, profile: RunPodTaskProfile) -> tuple[str, ...]:
        if profile.gpu_type_env_key == "RUNPOD_GPU_TYPE_IDS_IMG2IMG_LORA":
            return self.settings.gpu_type_ids_img2img_lora
        if profile.gpu_type_env_key == "RUNPOD_GPU_TYPE_IDS_WAN22_AIO_VIDEO":
            return self.settings.gpu_type_ids_wan22_aio_video
        if profile.gpu_type_env_key == "RUNPOD_GPU_TYPE_IDS_IMAGE_TO_VIDEO":
            return self.settings.gpu_type_ids_image_to_video
        if profile.gpu_type_env_key == "RUNPOD_GPU_TYPE_IDS_WAN22_VIDEO_V2":
            return self.settings.gpu_type_ids_wan22_video_v2
        if profile.gpu_type_env_key == "RUNPOD_GPU_TYPE_IDS_I2I_PRO":
            return self.settings.gpu_type_ids_i2i_pro
        raise ValueError(f"unsupported RunPod task profile: {profile.task_type}")

    def _template_id_for(self, profile: RunPodTaskProfile) -> str:
        if profile.template_env_key == "RUNPOD_TEMPLATE_ID_IMG2IMG_LORA":
            if not self.settings.use_template_img2img_lora:
                return ""
            return self.settings.template_id_img2img_lora
        if profile.template_env_key == "RUNPOD_TEMPLATE_ID_WAN22_AIO_VIDEO":
            if not self.settings.use_template_wan22_aio_video:
                return ""
            return self.settings.template_id_wan22_aio_video
        if profile.template_env_key == "RUNPOD_TEMPLATE_ID_IMAGE_TO_VIDEO":
            if not self.settings.use_template_image_to_video:
                return ""
            return self.settings.template_id_image_to_video
        if profile.template_env_key == "RUNPOD_TEMPLATE_ID_WAN22_VIDEO_V2":
            if not self.settings.use_template_wan22_video_v2:
                return ""
            return self.settings.template_id_wan22_video_v2
        if profile.template_env_key == "RUNPOD_TEMPLATE_ID_I2I_PRO":
            if not self.settings.use_template_i2i_pro:
                return ""
            return self.settings.template_id_i2i_pro
        raise ValueError(f"unsupported RunPod task profile: {profile.task_type}")

    def _image_name_for(self, profile: RunPodTaskProfile) -> str:
        if profile.image_env_key == "RUNPOD_IMAGE_NAME_IMG2IMG_LORA":
            return self.settings.image_name_img2img_lora
        if profile.image_env_key == "RUNPOD_IMAGE_NAME_WAN22_AIO_VIDEO":
            return self.settings.image_name_wan22_aio_video
        if profile.image_env_key == "RUNPOD_IMAGE_NAME_IMAGE_TO_VIDEO":
            return self.settings.image_name_image_to_video
        if profile.image_env_key == "RUNPOD_IMAGE_NAME_WAN22_VIDEO_V2":
            return self.settings.image_name_wan22_video_v2
        if profile.image_env_key == "RUNPOD_IMAGE_NAME_I2I_PRO":
            return self.settings.image_name_i2i_pro
        raise ValueError(f"unsupported RunPod task profile: {profile.task_type}")

    def _prod_image_name_for(self, profile: RunPodTaskProfile) -> str:
        image_name = self._image_name_for(profile)
        if profile.task_type == "img2img_lora" and not image_name:
            return RUNPOD_PUBLIC_IMG2IMG_LORA_IMAGE
        return image_name

    @staticmethod
    def _pending_image_name_for(profile: RunPodTaskProfile) -> str:
        if profile.task_type in {"wan22_aio_video", "image_to_video", "wan22_video_v2"}:
            return "allbot/comfy-runpod-wan22-aio-video:pending"
        if profile.task_type == "i2i_pro":
            return "allbot/comfy-runpod-i2i-pro:pending"
        return "allbot/comfy-runpod-img2img:pending"

    def _docker_start_cmd_for(self, profile: RunPodTaskProfile) -> tuple[str, ...]:
        if profile.task_type == "img2img_lora":
            return self.settings.docker_start_cmd_img2img_lora
        if profile.task_type == "wan22_aio_video":
            return self.settings.docker_start_cmd_wan22_aio_video
        if profile.task_type == "image_to_video":
            return self.settings.docker_start_cmd_image_to_video
        if profile.task_type == "wan22_video_v2":
            return self.settings.docker_start_cmd_wan22_video_v2
        if profile.task_type == "i2i_pro":
            return self.settings.docker_start_cmd_i2i_pro
        return ()

    def _workflow_overrides_for(self, profile: RunPodTaskProfile) -> str:
        if profile.task_type == "i2i_pro":
            raw = self.settings.task_type_workflow_overrides_i2i_pro.strip()
            if raw:
                parsed = json.loads(raw)
                if not isinstance(parsed, dict) or not all(
                    isinstance(key, str) and isinstance(value, str)
                    for key, value in parsed.items()
                ):
                    raise ValueError(
                        "RUNPOD_TASK_TYPE_WORKFLOW_OVERRIDES_I2I_PRO "
                        "must be a JSON object of task_type to workflow filename"
                    )
                return json.dumps(parsed, separators=(",", ":"))
        return ""

    def _model_prefix_for(self, profile: RunPodTaskProfile) -> str:
        if profile.task_type == "wan22_aio_video":
            return self.settings.model_prefix_wan22_aio_video
        if profile.task_type == "image_to_video":
            return self.settings.model_prefix_image_to_video
        if profile.task_type == "wan22_video_v2":
            return self.settings.model_prefix_wan22_video_v2
        if profile.task_type == "i2i_pro":
            return self.settings.model_prefix_i2i_pro
        return self.settings.model_prefix

    def _model_manifest_key_for(self, profile: RunPodTaskProfile) -> str:
        if profile.task_type == "wan22_aio_video":
            return self.settings.model_manifest_key_wan22_aio_video
        if profile.task_type == "image_to_video":
            return self.settings.model_manifest_key_image_to_video
        if profile.task_type == "wan22_video_v2":
            return self.settings.model_manifest_key_wan22_video_v2
        if profile.task_type == "i2i_pro":
            return self.settings.model_manifest_key_i2i_pro
        return self.settings.model_manifest_key

    def _prod_supported_task_types_for(
        self,
        profile: RunPodTaskProfile,
    ) -> tuple[str, ...]:
        if profile.task_type == "img2img_lora":
            return self.settings.prod_supported_task_types
        if profile.task_type == "image_to_video":
            return profile.supported_task_types
        if profile.task_type == "wan22_video_v2":
            return profile.supported_task_types
        if profile.task_type == "i2i_pro":
            return profile.supported_task_types
        raise ValueError(
            f"unsupported cloud-prod RunPod task profile: {profile.task_type}"
        )

    def _prod_model_prefix_for(self, profile: RunPodTaskProfile) -> str:
        if profile.task_type == "img2img_lora":
            return self.settings.model_prefix or "img2img_lora/2026-06-10"
        return self._model_prefix_for(profile)

    def _prod_model_manifest_key_for(
        self,
        profile: RunPodTaskProfile,
        model_prefix: str,
    ) -> str:
        if profile.task_type == "img2img_lora":
            return self.settings.model_manifest_key or f"{model_prefix}/manifest.json"
        return self._model_manifest_key_for(profile) or f"{model_prefix}/manifest.json"

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
