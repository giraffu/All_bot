from __future__ import annotations

import json
import os
from dataclasses import dataclass


RUNPOD_PROD_AGENT_ID_PREFIX = "runpod_prod_img2img_manual_"
RUNPOD_PROD_POD_NAME_PREFIX = "allbot-runpod-prod-img2img-manual-"
RUNPOD_PROD_WAN22_VIDEO_V2_AGENT_ID_PREFIX = "runpod_prod_wan22_video_v2_manual_"
RUNPOD_PROD_WAN22_VIDEO_V2_POD_NAME_PREFIX = (
    "allbot-runpod-prod-wan22-video-v2-manual-"
)
RUNPOD_PROD_IMAGE_TO_VIDEO_AGENT_ID_PREFIX = "runpod_prod_image_to_video_manual_"
RUNPOD_PROD_IMAGE_TO_VIDEO_POD_NAME_PREFIX = (
    "allbot-runpod-prod-image-to-video-manual-"
)
RUNPOD_PROD_I2I_PRO_AGENT_ID_PREFIX = "runpod_prod_i2i_pro_manual_"
RUNPOD_PROD_I2I_PRO_POD_NAME_PREFIX = "allbot-runpod-prod-i2i-pro-manual-"
RUNPOD_PROD_SCAIL2_AGENT_ID_PREFIX = "runpod_prod_scail2_manual_"
RUNPOD_PROD_SCAIL2_POD_NAME_PREFIX = "allbot-runpod-prod-scail2-manual-"
RUNPOD_PROD_LTX_VIDEO_AGENT_ID_PREFIX = "runpod_prod_ltx_video_manual_"
RUNPOD_PROD_LTX_VIDEO_POD_NAME_PREFIX = "allbot-runpod-prod-ltx-video-manual-"
RUNPOD_PROD_PORNMASTER_FLUX2_EDIT_AGENT_ID_PREFIX = (
    "runpod_prod_pornmaster_flux2_edit_manual_"
)
RUNPOD_PROD_PORNMASTER_FLUX2_EDIT_POD_NAME_PREFIX = (
    "allbot-runpod-prod-pornmaster-flux2-edit-manual-"
)
RUNPOD_PROD_PORNMASTER_FLUX2_EDIT_BF16_AGENT_ID_PREFIX = (
    "runpod_prod_pornmaster_flux2_edit_bf16_manual_"
)
RUNPOD_PROD_PORNMASTER_FLUX2_EDIT_BF16_POD_NAME_PREFIX = (
    "allbot-runpod-prod-pornmaster-flux2-edit-bf16-manual-"
)
RUNPOD_PROD_DEFAULT_MAX_MANUAL_SLOTS = 100
RUNPOD_PROD_MAX_MANUAL_SLOTS = RUNPOD_PROD_DEFAULT_MAX_MANUAL_SLOTS
RUNPOD_PROD_AGENT_ID = "runpod_prod_img2img_manual_01"
RUNPOD_PROD_NODE_ID = "runpod-cloud-prod"
RUNPOD_PROD_BUCKET = "user-data-prod"
RUNPOD_PROD_SUPPORTED_TASK_TYPES = ("img2img", "img2img_lora")
RUNPOD_PROD_GPU_TYPE_IDS = ("NVIDIA GeForce RTX 4090",)
RUNPOD_PUBLIC_IMG2IMG_LORA_IMAGE = (
    "ghcr.io/giraffu/allbot-comfy-runpod-img2img:20260716-img2img-baked-runtime-v1"
)
RUNPOD_PUBLIC_WAN22_AIO_VIDEO_REPOSITORY = (
    "ghcr.io/giraffu/allbot-comfy-runpod-wan22-aio-video"
)
RUNPOD_PUBLIC_WAN22_VIDEO_V2_IMAGE_PREFIX = (
    RUNPOD_PUBLIC_WAN22_AIO_VIDEO_REPOSITORY + ":"
)
RUNPOD_WAN22_AIO_VIDEO_RIFE_TAG = "20260619-wan22aio-rife-bcf3ebd"
RUNPOD_PUBLIC_WAN22_AIO_VIDEO_RIFE_IMAGE = (
    RUNPOD_PUBLIC_WAN22_VIDEO_V2_IMAGE_PREFIX + RUNPOD_WAN22_AIO_VIDEO_RIFE_TAG
)
RUNPOD_PUBLIC_SCAIL2_IMAGE_PREFIX = (
    "ghcr.io/giraffu/allbot-comfy-runpod-scail2:"
)
RUNPOD_PUBLIC_LTX_VIDEO_IMAGE_PREFIX = (
    "ghcr.io/giraffu/allbot-comfy-runpod-ltx-video-v2:"
)
RUNPOD_PUBLIC_PORNMASTER_FLUX2_EDIT_IMAGE_PREFIX = (
    "ghcr.io/giraffu/allbot-comfy-runpod-pornmaster-flux2-edit-baked:"
)
RUNPOD_PUBLIC_PORNMASTER_FLUX2_EDIT_IMAGE = (
    RUNPOD_PUBLIC_PORNMASTER_FLUX2_EDIT_IMAGE_PREFIX
    + "20260716-pornmaster-flux2-edit-baked-runtime-v1"
)
RUNPOD_PUBLIC_PORNMASTER_FLUX2_EDIT_IMAGE = (
    RUNPOD_PUBLIC_PORNMASTER_FLUX2_EDIT_IMAGE_PREFIX
    + "20260716-pornmaster-flux2-edit-baked-runtime-v1"
)
RUNPOD_WAN22_AIO_VIDEO_GPU_TYPE_IDS = (
    "NVIDIA GeForce RTX 5090",
    "NVIDIA GeForce RTX 4090",
)
RUNPOD_WAN22_AIO_VIDEO_MODEL_PREFIX = "wan22_aio_video/2026-07-18-lora5"
RUNPOD_WAN22_AIO_VIDEO_MODEL_MANIFEST_KEY = (
    "wan22_aio_video/2026-07-18-lora5/manifest.json"
)
RUNPOD_IMAGE_TO_VIDEO_MODEL_PREFIX = "image_to_video/2026-07-18-lora5"
RUNPOD_IMAGE_TO_VIDEO_MODEL_MANIFEST_KEY = (
    "image_to_video/2026-07-18-lora5/manifest.json"
)
RUNPOD_WAN22_VIDEO_V2_MODEL_PREFIX = "wan22_video_v2/2026-07-18-lora5"
RUNPOD_WAN22_VIDEO_V2_MODEL_MANIFEST_KEY = (
    "wan22_video_v2/2026-07-18-lora5/manifest.json"
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
    "face_swap_v2",
)
RUNPOD_I2I_PRO_WORKFLOW_OVERRIDES = json.dumps(
    {
        "t2i-pornmaster-turbo": "txt2img_from_i2i_pro.json",
        "face_swap_v2": "face_swap_v2.json",
    },
    separators=(",", ":"),
)
RUNPOD_SCAIL2_GPU_TYPE_IDS = (
    "NVIDIA GeForce RTX 5090",
    "NVIDIA GeForce RTX 4090",
)
RUNPOD_SCAIL2_MODEL_PREFIX = "scail2/2026-06-17-test"
RUNPOD_SCAIL2_MODEL_MANIFEST_KEY = "scail2/2026-06-17-test/manifest.json"
RUNPOD_SCAIL2_CONTAINER_DISK_GB = 120
RUNPOD_SCAIL2_SUPPORTED_TASK_TYPES = (
    "scail2_action_transfer",
    "scail2_video_replacement",
)
RUNPOD_BOOTSTRAP_DOCKER_START_CMD = (
    "bash",
    "-lc",
    "exec bash /opt/allbot/runpod_baked_runtime_entrypoint.sh",
)
RUNPOD_IMG2IMG_LORA_BOOTSTRAP_LOADER_SCRIPT = (
    "set -euo pipefail; "
    'BOOTSTRAP="${RUNPOD_BOOTSTRAP_SCRIPT_PATH:-/opt/allbot/runpod_baked_runtime_entrypoint.sh}"; '
    'test -x "$BOOTSTRAP" || { echo "baked RunPod entrypoint missing" >&2; exit 66; }; '
    'exec bash "$BOOTSTRAP"'
)
RUNPOD_IMG2IMG_LORA_DOCKER_START_CMD = (
    "bash",
    "-lc",
    RUNPOD_IMG2IMG_LORA_BOOTSTRAP_LOADER_SCRIPT,
)
RUNPOD_SCAIL2_DOCKER_START_CMD = RUNPOD_BOOTSTRAP_DOCKER_START_CMD
RUNPOD_LTX_VIDEO_GPU_TYPE_IDS = (
    "NVIDIA GeForce RTX 5090",
    "NVIDIA GeForce RTX 4090",
)
RUNPOD_LTX_VIDEO_MODEL_PREFIX = "ltx_video/2026-06-10"
RUNPOD_LTX_VIDEO_MODEL_MANIFEST_KEY = "ltx_video/2026-06-10/manifest.json"
RUNPOD_LTX_VIDEO_CONTAINER_DISK_GB = 180
RUNPOD_LTX_VIDEO_SUPPORTED_TASK_TYPES = (
    "ltx_video",
    "ltx_video_flf2v",
    "ltx_video_v2v_audio",
)
RUNPOD_LTX_VIDEO_WORKFLOW_OVERRIDES = json.dumps(
    {
        "ltx_video": "LTX 2.3 10Eros v1.2 I2V 6.1.json",
        "ltx_video_flf2v": "LTX 2.3 10Eros v1.2 FLF2V 6.1.json",
        "ltx_video_v2v_audio": "LTX 2.3 10Eros v1.2 V2V Audio 6.1.json",
    },
    separators=(",", ":"),
)
RUNPOD_LTX_VIDEO_DOCKER_START_CMD = RUNPOD_BOOTSTRAP_DOCKER_START_CMD
RUNPOD_PORNMASTER_FLUX2_EDIT_GPU_TYPE_IDS = (
    "NVIDIA GeForce RTX 4090",
    "NVIDIA L40S",
    "NVIDIA GeForce RTX 5090",
)
RUNPOD_PORNMASTER_FLUX2_EDIT_MODEL_PREFIX = "pornmaster_flux2_edit/2026-06-27"
RUNPOD_PORNMASTER_FLUX2_EDIT_MODEL_MANIFEST_KEY = (
    "pornmaster_flux2_edit/2026-06-27/manifest.json"
)
RUNPOD_PORNMASTER_FLUX2_EDIT_CONTAINER_DISK_GB = 120
RUNPOD_PORNMASTER_FLUX2_EDIT_SUPPORTED_TASK_TYPES = (
    "pornmaster_flux2_single_edit",
    "pornmaster_flux2_multi_edit",
)
RUNPOD_PORNMASTER_FLUX2_EDIT_DOCKER_START_CMD = RUNPOD_BOOTSTRAP_DOCKER_START_CMD
RUNPOD_PORNMASTER_FLUX2_EDIT_BF16_GPU_TYPE_IDS = ("NVIDIA GeForce RTX 4090",)
RUNPOD_PORNMASTER_FLUX2_EDIT_BF16_MODEL_PREFIX = (
    "pornmaster_flux2_edit_bf16/2026-07-12"
)
RUNPOD_PORNMASTER_FLUX2_EDIT_BF16_MODEL_MANIFEST_KEY = (
    "pornmaster_flux2_edit_bf16/2026-07-12/manifest.json"
)
RUNPOD_PORNMASTER_FLUX2_EDIT_BF16_CONTAINER_DISK_GB = 120
RUNPOD_PORNMASTER_FLUX2_EDIT_BF16_SUPPORTED_TASK_TYPES = (
    "pornmaster_flux2_edit_bf16",
    "pornmaster_flux2_multi_edit_bf16",
)
RUNPOD_PORNMASTER_FLUX2_EDIT_BF16_DOCKER_START_CMD = (
    RUNPOD_BOOTSTRAP_DOCKER_START_CMD
)
RUNPOD_PORNMASTER_FLUX2_EDIT_BF16_COMFY_EXTRA_ARGS = "--lowvram"


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
    "scail2": RunPodTaskProfile(
        task_type="scail2",
        supported_task_types=RUNPOD_SCAIL2_SUPPORTED_TASK_TYPES,
        runtime_profile="scail2",
        agent_id_prefix="runpod_test_scail2",
        template_env_key="RUNPOD_TEMPLATE_ID_SCAIL2",
        gpu_type_env_key="RUNPOD_GPU_TYPE_IDS_SCAIL2",
        image_env_key="RUNPOD_IMAGE_NAME_SCAIL2",
    ),
    "ltx_video": RunPodTaskProfile(
        task_type="ltx_video",
        supported_task_types=RUNPOD_LTX_VIDEO_SUPPORTED_TASK_TYPES,
        runtime_profile="ltx_video",
        agent_id_prefix="runpod_test_ltx_video",
        template_env_key="RUNPOD_TEMPLATE_ID_LTX_VIDEO",
        gpu_type_env_key="RUNPOD_GPU_TYPE_IDS_LTX_VIDEO",
        image_env_key="RUNPOD_IMAGE_NAME_LTX_VIDEO",
    ),
    "pornmaster_flux2_edit": RunPodTaskProfile(
        task_type="pornmaster_flux2_edit",
        supported_task_types=RUNPOD_PORNMASTER_FLUX2_EDIT_SUPPORTED_TASK_TYPES,
        runtime_profile="pornmaster_flux2_edit",
        agent_id_prefix="runpod_test_pornmaster_flux2_edit",
        template_env_key="RUNPOD_TEMPLATE_ID_PORNMASTER_FLUX2_EDIT",
        gpu_type_env_key="RUNPOD_GPU_TYPE_IDS_PORNMASTER_FLUX2_EDIT",
        image_env_key="RUNPOD_IMAGE_NAME_PORNMASTER_FLUX2_EDIT",
    ),
    "pornmaster_flux2_single_edit": RunPodTaskProfile(
        task_type="pornmaster_flux2_edit",
        supported_task_types=RUNPOD_PORNMASTER_FLUX2_EDIT_SUPPORTED_TASK_TYPES,
        runtime_profile="pornmaster_flux2_edit",
        agent_id_prefix="runpod_test_pornmaster_flux2_edit",
        template_env_key="RUNPOD_TEMPLATE_ID_PORNMASTER_FLUX2_EDIT",
        gpu_type_env_key="RUNPOD_GPU_TYPE_IDS_PORNMASTER_FLUX2_EDIT",
        image_env_key="RUNPOD_IMAGE_NAME_PORNMASTER_FLUX2_EDIT",
    ),
    "pornmaster_flux2_multi_edit": RunPodTaskProfile(
        task_type="pornmaster_flux2_edit",
        supported_task_types=RUNPOD_PORNMASTER_FLUX2_EDIT_SUPPORTED_TASK_TYPES,
        runtime_profile="pornmaster_flux2_edit",
        agent_id_prefix="runpod_test_pornmaster_flux2_edit",
        template_env_key="RUNPOD_TEMPLATE_ID_PORNMASTER_FLUX2_EDIT",
        gpu_type_env_key="RUNPOD_GPU_TYPE_IDS_PORNMASTER_FLUX2_EDIT",
        image_env_key="RUNPOD_IMAGE_NAME_PORNMASTER_FLUX2_EDIT",
    ),
    "pornmaster_flux2_edit_bf16": RunPodTaskProfile(
        task_type="pornmaster_flux2_edit_bf16",
        supported_task_types=RUNPOD_PORNMASTER_FLUX2_EDIT_BF16_SUPPORTED_TASK_TYPES,
        runtime_profile="pornmaster_flux2_edit",
        agent_id_prefix="runpod_test_pornmaster_flux2_edit_bf16",
        template_env_key="RUNPOD_TEMPLATE_ID_PORNMASTER_FLUX2_EDIT",
        gpu_type_env_key="RUNPOD_GPU_TYPE_IDS_PORNMASTER_FLUX2_EDIT_BF16",
        image_env_key="RUNPOD_IMAGE_NAME_PORNMASTER_FLUX2_EDIT",
    ),
}

RUNPOD_ADMIN_PROFILE_OPTIONS: tuple[dict[str, object], ...] = (
    {
        "profile": "img2img",
        "label": "img2img / img2img_lora",
        "supported_task_types": ["img2img", "img2img_lora"],
    },
    {
        "profile": "image_to_video",
        "label": "image_to_video",
        "supported_task_types": ["image_to_video", "video_insert", "video_edit"],
    },
    {
        "profile": "wan22_video_v2",
        "label": "wan22_video_v2",
        "supported_task_types": ["wan22_video_v2"],
    },
    {
        "profile": "i2i_pro",
        "label": "i2i_pro / txt2img / face_swap_v2",
        "supported_task_types": [
            "i2i_pro",
            "t2i-pornmaster-turbo",
            "face_swap_v2",
        ],
    },
    {
        "profile": "scail2",
        "label": "scail2 / 视频生视频",
        "supported_task_types": [
            "scail2_action_transfer",
            "scail2_video_replacement",
        ],
    },
    {
        "profile": "ltx_video",
        "label": "ltx_video / 高级图生视频",
        "supported_task_types": [
            "ltx_video",
            "ltx_video_flf2v",
            "ltx_video_v2v_audio",
        ],
    },
    {
        "profile": "pornmaster_flux2_edit",
        "label": "pornmaster_flux2 / 自由P图 v2",
        "supported_task_types": [
            "pornmaster_flux2_single_edit",
            "pornmaster_flux2_multi_edit",
        ],
    },
    {
        "profile": "pornmaster_flux2_edit_bf16",
        "label": "pornmaster_flux2 BF16 / 自由P图 v2.5 + v3 共用执行池",
        "supported_task_types": list(
            RUNPOD_PORNMASTER_FLUX2_EDIT_BF16_SUPPORTED_TASK_TYPES
        ),
    },
)

DASHBOARD_WORKER_PROFILE_OPTIONS: tuple[dict[str, object], ...] = (
    RUNPOD_ADMIN_PROFILE_OPTIONS
)

RUNPOD_AUTOSCALER_PROFILE_OPTIONS: tuple[dict[str, object], ...] = tuple(
    option
    for option in DASHBOARD_WORKER_PROFILE_OPTIONS
    if option.get("autoscaler_enabled", True) is not False
)


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
    normalized = normalize_prod_worker_slot(
        slot,
        max_manual_slots=max_manual_slots,
    )
    return f"{prod_agent_id_prefix_for(profile)}{normalized}"


def prod_slot_from_agent_id(
    agent_id: str,
    *,
    max_manual_slots: int | None = None,
    profile: str | None = None,
) -> str:
    profile_key = (
        prod_profile_from_agent_id(agent_id)
        if profile is None
        else normalize_prod_worker_profile(profile)
    )
    prefix = prod_agent_id_prefix_for(profile_key)
    if not agent_id.startswith(prefix):
        raise ValueError(f"prod RunPod {profile_key} agent_id must start with {prefix}")
    return normalize_prod_worker_slot(
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
        prod_profile_from_agent_id(agent_id)
        if profile is None
        else normalize_prod_worker_profile(profile)
    )
    slot = prod_slot_from_agent_id(
        agent_id,
        max_manual_slots=max_manual_slots,
        profile=profile_key,
    )
    return f"{prod_pod_name_prefix_for(profile_key)}{slot}"


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
    if value == "scail2":
        return "scail2"
    if value == "ltx_video":
        return "ltx_video"
    if value == "pornmaster_flux2_edit":
        return "pornmaster_flux2_edit"
    if value == "pornmaster_flux2_edit_bf16":
        return "pornmaster_flux2_edit_bf16"
    raise ValueError(
        "prod RunPod profile must be img2img, image_to_video, "
        "wan22_video_v2, i2i_pro, scail2, ltx_video, pornmaster_flux2_edit, "
        "or pornmaster_flux2_edit_bf16"
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
    if value == "scail2" or value in RUNPOD_SCAIL2_SUPPORTED_TASK_TYPES:
        return "scail2"
    if value == "ltx_video" or value in RUNPOD_LTX_VIDEO_SUPPORTED_TASK_TYPES:
        return "ltx_video"
    if (
        value == "pornmaster_flux2_edit"
        or value in RUNPOD_PORNMASTER_FLUX2_EDIT_SUPPORTED_TASK_TYPES
    ):
        return "pornmaster_flux2_edit"
    if value in RUNPOD_PORNMASTER_FLUX2_EDIT_BF16_SUPPORTED_TASK_TYPES:
        return "pornmaster_flux2_edit_bf16"
    raise ValueError(
        "prod RunPod worker only supports img2img, image_to_video, "
        "wan22_video_v2, i2i_pro, scail2, ltx_video, pornmaster_flux2_edit, "
        "or pornmaster_flux2_edit_bf16"
    )


def prod_worker_profile_from_agent_id(agent_id: str) -> str:
    return prod_profile_from_agent_id(agent_id)


def prod_profile_from_agent_id(agent_id: str) -> str:
    raw = str(agent_id or "")
    if raw.startswith(RUNPOD_PROD_AGENT_ID_PREFIX):
        return "img2img"
    if raw.startswith(RUNPOD_PROD_IMAGE_TO_VIDEO_AGENT_ID_PREFIX):
        return "image_to_video"
    if raw.startswith(RUNPOD_PROD_WAN22_VIDEO_V2_AGENT_ID_PREFIX):
        return "wan22_video_v2"
    if raw.startswith(RUNPOD_PROD_I2I_PRO_AGENT_ID_PREFIX):
        return "i2i_pro"
    if raw.startswith(RUNPOD_PROD_SCAIL2_AGENT_ID_PREFIX):
        return "scail2"
    if raw.startswith(RUNPOD_PROD_LTX_VIDEO_AGENT_ID_PREFIX):
        return "ltx_video"
    if raw.startswith(RUNPOD_PROD_PORNMASTER_FLUX2_EDIT_AGENT_ID_PREFIX):
        return "pornmaster_flux2_edit"
    if raw.startswith(RUNPOD_PROD_PORNMASTER_FLUX2_EDIT_BF16_AGENT_ID_PREFIX):
        return "pornmaster_flux2_edit_bf16"
    raise ValueError(
        "prod RunPod agent_id must start with one of "
        f"{RUNPOD_PROD_AGENT_ID_PREFIX}, "
        f"{RUNPOD_PROD_IMAGE_TO_VIDEO_AGENT_ID_PREFIX}, "
        f"{RUNPOD_PROD_WAN22_VIDEO_V2_AGENT_ID_PREFIX}, "
        f"{RUNPOD_PROD_I2I_PRO_AGENT_ID_PREFIX}, "
        f"{RUNPOD_PROD_SCAIL2_AGENT_ID_PREFIX}, "
        f"{RUNPOD_PROD_LTX_VIDEO_AGENT_ID_PREFIX}, "
        f"{RUNPOD_PROD_PORNMASTER_FLUX2_EDIT_AGENT_ID_PREFIX}, "
        f"{RUNPOD_PROD_PORNMASTER_FLUX2_EDIT_BF16_AGENT_ID_PREFIX}"
    )


def prod_agent_id_prefix_for(profile: str | None) -> str:
    profile_key = normalize_prod_worker_profile(profile)
    if profile_key == "image_to_video":
        return RUNPOD_PROD_IMAGE_TO_VIDEO_AGENT_ID_PREFIX
    if profile_key == "wan22_video_v2":
        return RUNPOD_PROD_WAN22_VIDEO_V2_AGENT_ID_PREFIX
    if profile_key == "i2i_pro":
        return RUNPOD_PROD_I2I_PRO_AGENT_ID_PREFIX
    if profile_key == "scail2":
        return RUNPOD_PROD_SCAIL2_AGENT_ID_PREFIX
    if profile_key == "ltx_video":
        return RUNPOD_PROD_LTX_VIDEO_AGENT_ID_PREFIX
    if profile_key == "pornmaster_flux2_edit":
        return RUNPOD_PROD_PORNMASTER_FLUX2_EDIT_AGENT_ID_PREFIX
    if profile_key == "pornmaster_flux2_edit_bf16":
        return RUNPOD_PROD_PORNMASTER_FLUX2_EDIT_BF16_AGENT_ID_PREFIX
    return RUNPOD_PROD_AGENT_ID_PREFIX


def prod_pod_name_prefix_for(profile: str | None) -> str:
    profile_key = normalize_prod_worker_profile(profile)
    if profile_key == "image_to_video":
        return RUNPOD_PROD_IMAGE_TO_VIDEO_POD_NAME_PREFIX
    if profile_key == "wan22_video_v2":
        return RUNPOD_PROD_WAN22_VIDEO_V2_POD_NAME_PREFIX
    if profile_key == "i2i_pro":
        return RUNPOD_PROD_I2I_PRO_POD_NAME_PREFIX
    if profile_key == "scail2":
        return RUNPOD_PROD_SCAIL2_POD_NAME_PREFIX
    if profile_key == "ltx_video":
        return RUNPOD_PROD_LTX_VIDEO_POD_NAME_PREFIX
    if profile_key == "pornmaster_flux2_edit":
        return RUNPOD_PROD_PORNMASTER_FLUX2_EDIT_POD_NAME_PREFIX
    if profile_key == "pornmaster_flux2_edit_bf16":
        return RUNPOD_PROD_PORNMASTER_FLUX2_EDIT_BF16_POD_NAME_PREFIX
    return RUNPOD_PROD_POD_NAME_PREFIX


def normalize_prod_worker_slot(
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
        else prod_max_manual_slots_from_env()
    )
    if value < 1 or value > max_slots:
        raise ValueError(f"prod RunPod slot must be between 01 and {max_slots:02d}")
    return f"{value:02d}"


def prod_max_manual_slots_from_env() -> int:
    return _int_env(
        os.getenv("RUNPOD_PROD_MAX_MANUAL_SLOTS"),
        default=RUNPOD_PROD_DEFAULT_MAX_MANUAL_SLOTS,
    )


# Compatibility aliases for the previous provider module private helpers.
_prod_profile_from_agent_id = prod_profile_from_agent_id
_prod_agent_id_prefix_for = prod_agent_id_prefix_for
_prod_pod_name_prefix_for = prod_pod_name_prefix_for
_normalize_prod_worker_slot = normalize_prod_worker_slot
_prod_max_manual_slots_from_env = prod_max_manual_slots_from_env
