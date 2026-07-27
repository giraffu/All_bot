from __future__ import annotations

import json
import os
import re
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .providers.runpod import (
    RUNPOD_I2I_PRO_GPU_TYPE_IDS,
    RUNPOD_I2I_PRO_MODEL_MANIFEST_KEY,
    RUNPOD_I2I_PRO_MODEL_PREFIX,
    RUNPOD_I2I_PRO_SUPPORTED_TASK_TYPES,
    RUNPOD_I2I_PRO_WORKFLOW_OVERRIDES,
    RUNPOD_IMAGE_TO_VIDEO_MODEL_MANIFEST_KEY,
    RUNPOD_IMAGE_TO_VIDEO_MODEL_PREFIX,
    RUNPOD_LTX_VIDEO_GPU_TYPE_IDS,
    RUNPOD_LTX_VIDEO_MODEL_MANIFEST_KEY,
    RUNPOD_LTX_VIDEO_MODEL_PREFIX,
    RUNPOD_LTX_VIDEO_SUPPORTED_TASK_TYPES,
    RUNPOD_LTX_VIDEO_WORKFLOW_OVERRIDES,
    RUNPOD_LTX_T2V_GPU_TYPE_IDS,
    RUNPOD_LTX_T2V_MODEL_MANIFEST_KEY,
    RUNPOD_LTX_T2V_MODEL_PREFIX,
    RUNPOD_LTX_T2V_SUPPORTED_TASK_TYPES,
    RUNPOD_PROD_I2I_PRO_POD_NAME_PREFIX,
    RUNPOD_PROD_IMAGE_TO_VIDEO_POD_NAME_PREFIX,
    RUNPOD_PROD_LTX_VIDEO_POD_NAME_PREFIX,
    RUNPOD_PROD_LTX_T2V_POD_NAME_PREFIX,
    RUNPOD_PROD_POD_NAME_PREFIX,
    RUNPOD_PROD_SCAIL2_POD_NAME_PREFIX,
    RUNPOD_PROD_WAN22_VIDEO_V2_POD_NAME_PREFIX,
    RUNPOD_PUBLIC_LTX_VIDEO_IMAGE_PREFIX,
    RUNPOD_PUBLIC_LTX_T2V_IMAGE_PREFIX,
    RUNPOD_PUBLIC_SCAIL2_IMAGE_PREFIX,
    RUNPOD_SCAIL2_DOCKER_START_CMD,
    RUNPOD_SCAIL2_GPU_TYPE_IDS,
    RUNPOD_SCAIL2_MODEL_MANIFEST_KEY,
    RUNPOD_SCAIL2_MODEL_PREFIX,
    RUNPOD_SCAIL2_SUPPORTED_TASK_TYPES,
    RUNPOD_TASK_PROFILES,
    RUNPOD_WAN22_AIO_VIDEO_GPU_TYPE_IDS,
    RUNPOD_WAN22_VIDEO_V2_MODEL_MANIFEST_KEY,
    RUNPOD_WAN22_VIDEO_V2_MODEL_PREFIX,
    RunPodProvider,
    redact_payload,
    redact_text,
)
from .runpod_cloud_test_canary import (
    RunPodCloudTestCanaryAssets,
    RunPodCloudTestCanaryCaseBuilder,
    RunPodCloudTestCanaryConfig,
    RunPodCloudTestCanaryExecutor,
)
from .runpod_control import (
    RunPodControlClient,
    RunPodControlConfig,
    select_cloud_test_worker_ids_to_disable,
)
from .runpod_http import RunPodHttpClient


EXPECTED_RUNPOD_CLOUD_TEST_CENTRAL_URL = "https://worker-central-test.aivison.it.com"
EXPECTED_MODEL_BUCKET = "allbot-model-cache"
EXPECTED_MODEL_PREFIX = "img2img_lora/2026-06-10"
EXPECTED_MODEL_MANIFEST_KEY = "img2img_lora/2026-06-10/manifest.json"
EXPECTED_WAN22_AIO_VIDEO_MODEL_PREFIX = "wan22_aio_video/2026-07-18-lora5"
EXPECTED_WAN22_AIO_VIDEO_MODEL_MANIFEST_KEY = (
    "wan22_aio_video/2026-07-18-lora5/manifest.json"
)
EXPECTED_IMAGE_TO_VIDEO_MODEL_PREFIX = RUNPOD_IMAGE_TO_VIDEO_MODEL_PREFIX
EXPECTED_IMAGE_TO_VIDEO_MODEL_MANIFEST_KEY = RUNPOD_IMAGE_TO_VIDEO_MODEL_MANIFEST_KEY
EXPECTED_WAN22_VIDEO_V2_MODEL_PREFIX = RUNPOD_WAN22_VIDEO_V2_MODEL_PREFIX
EXPECTED_WAN22_VIDEO_V2_MODEL_MANIFEST_KEY = RUNPOD_WAN22_VIDEO_V2_MODEL_MANIFEST_KEY
EXPECTED_I2I_PRO_MODEL_PREFIX = RUNPOD_I2I_PRO_MODEL_PREFIX
EXPECTED_I2I_PRO_MODEL_MANIFEST_KEY = RUNPOD_I2I_PRO_MODEL_MANIFEST_KEY
EXPECTED_SCAIL2_MODEL_PREFIX = RUNPOD_SCAIL2_MODEL_PREFIX
EXPECTED_SCAIL2_MODEL_MANIFEST_KEY = RUNPOD_SCAIL2_MODEL_MANIFEST_KEY
EXPECTED_LTX_VIDEO_MODEL_PREFIX = RUNPOD_LTX_VIDEO_MODEL_PREFIX
EXPECTED_LTX_VIDEO_MODEL_MANIFEST_KEY = RUNPOD_LTX_VIDEO_MODEL_MANIFEST_KEY
EXPECTED_LTX_T2V_MODEL_PREFIX = RUNPOD_LTX_T2V_MODEL_PREFIX
EXPECTED_LTX_T2V_MODEL_MANIFEST_KEY = RUNPOD_LTX_T2V_MODEL_MANIFEST_KEY
EXPECTED_TEST_BUCKET = "user-data-test"
EXPECTED_IMAGE_REF_PREFIX = "ghcr.io/giraffu/allbot-comfy-runpod-img2img:"
EXPECTED_WAN22_AIO_VIDEO_IMAGE_REF_PREFIX = (
    "ghcr.io/giraffu/allbot-comfy-runpod-wan22-aio-video:"
)
EXPECTED_I2I_PRO_IMAGE_REF_PREFIX = "ghcr.io/giraffu/allbot-comfy-runpod-i2i-pro:"
EXPECTED_SCAIL2_IMAGE_REF_PREFIX = RUNPOD_PUBLIC_SCAIL2_IMAGE_PREFIX
EXPECTED_LTX_VIDEO_IMAGE_REF_PREFIX = RUNPOD_PUBLIC_LTX_VIDEO_IMAGE_PREFIX
EXPECTED_LTX_T2V_IMAGE_REF_PREFIX = RUNPOD_PUBLIC_LTX_T2V_IMAGE_PREFIX
DEFAULT_CONTROL_HOST = "100.82.124.91"
DEFAULT_WORKER_IDS = tuple(f"cloud_worker_test_{index:02d}" for index in range(1, 8))
EXPECTED_TASK_TYPES = ("img2img", "img2img_lora")
EXPECTED_WAN22_AIO_VIDEO_TASK_TYPES = ("image_to_video", "wan22_video_v2")
EXPECTED_WAN22_AIO_VIDEO_GPU_TYPE_IDS = RUNPOD_WAN22_AIO_VIDEO_GPU_TYPE_IDS
EXPECTED_I2I_PRO_GPU_TYPE_IDS = RUNPOD_I2I_PRO_GPU_TYPE_IDS
EXPECTED_SCAIL2_GPU_TYPE_IDS = RUNPOD_SCAIL2_GPU_TYPE_IDS
EXPECTED_LTX_VIDEO_GPU_TYPE_IDS = RUNPOD_LTX_VIDEO_GPU_TYPE_IDS
EXPECTED_LTX_T2V_GPU_TYPE_IDS = RUNPOD_LTX_T2V_GPU_TYPE_IDS
TERMINAL_TASK_STATUSES = {"done", "error", "cancelled"}
HEALTHY_WORKER_STATUSES = {"idle", "running"}
PROD_MANUAL_POD_NAME_PREFIXES = (
    RUNPOD_PROD_POD_NAME_PREFIX,
    RUNPOD_PROD_IMAGE_TO_VIDEO_POD_NAME_PREFIX,
    RUNPOD_PROD_WAN22_VIDEO_V2_POD_NAME_PREFIX,
    RUNPOD_PROD_I2I_PRO_POD_NAME_PREFIX,
    RUNPOD_PROD_SCAIL2_POD_NAME_PREFIX,
    RUNPOD_PROD_LTX_VIDEO_POD_NAME_PREFIX,
    RUNPOD_PROD_LTX_T2V_POD_NAME_PREFIX,
)
SCAIL2_SAMPLE_REFERENCE_URL = (
    "https://i.gyazo.com/567acaf722ca9e839ec7cb834c1ed344/max_size/1200.jpg"
)
SCAIL2_SAMPLE_MOTION_VIDEO_URL = (
    "https://i.gyazo.com/53461ca17746349fbd11e69798460ea6.mp4"
)
SCAIL2_CANARY_NEGATIVE_PROMPT = (
    "low quality, artifacts, text, watermark, distorted face, bad hands"
)


class RunPodCanaryError(ValueError):
    pass


@dataclass(frozen=True)
class RunPodCanaryProfileSpec:
    task_type: str
    image_ref_prefix: str
    supported_task_types: tuple[str, ...]
    model_prefix: str
    model_manifest_key: str
    allow_template_id: bool = False
    expected_gpu_type_ids: tuple[str, ...] = ()
    workflow_overrides: str = ""
    task_summary: str = ""
    worker_disable_summary: str = ""


RUNPOD_CANARY_PROFILE_SPECS: dict[str, RunPodCanaryProfileSpec] = {
    "img2img_lora": RunPodCanaryProfileSpec(
        task_type="img2img_lora",
        image_ref_prefix=EXPECTED_IMAGE_REF_PREFIX,
        supported_task_types=EXPECTED_TASK_TYPES,
        model_prefix=EXPECTED_MODEL_PREFIX,
        model_manifest_key=EXPECTED_MODEL_MANIFEST_KEY,
        task_summary="submit img2img and two img2img_lora Web tasks serially",
        worker_disable_summary="temporarily disable cloud_worker_test_01..07",
    ),
    "wan22_aio_video": RunPodCanaryProfileSpec(
        task_type="wan22_aio_video",
        image_ref_prefix=EXPECTED_WAN22_AIO_VIDEO_IMAGE_REF_PREFIX,
        supported_task_types=EXPECTED_WAN22_AIO_VIDEO_TASK_TYPES,
        model_prefix=EXPECTED_WAN22_AIO_VIDEO_MODEL_PREFIX,
        model_manifest_key=EXPECTED_WAN22_AIO_VIDEO_MODEL_MANIFEST_KEY,
        allow_template_id=True,
        expected_gpu_type_ids=EXPECTED_WAN22_AIO_VIDEO_GPU_TYPE_IDS,
        task_summary="submit image_to_video and wan22_video_v2 preview/5s Web tasks serially",
        worker_disable_summary="temporarily disable cloud-test workers supporting image_to_video or wan22_video_v2",
    ),
    "image_to_video": RunPodCanaryProfileSpec(
        task_type="image_to_video",
        image_ref_prefix=EXPECTED_WAN22_AIO_VIDEO_IMAGE_REF_PREFIX,
        supported_task_types=("image_to_video",),
        model_prefix=EXPECTED_IMAGE_TO_VIDEO_MODEL_PREFIX,
        model_manifest_key=EXPECTED_IMAGE_TO_VIDEO_MODEL_MANIFEST_KEY,
        allow_template_id=True,
        expected_gpu_type_ids=EXPECTED_WAN22_AIO_VIDEO_GPU_TYPE_IDS,
        task_summary="submit image_to_video preview/5s Web task",
        worker_disable_summary="temporarily disable cloud-test workers supporting image_to_video",
    ),
    "wan22_video_v2": RunPodCanaryProfileSpec(
        task_type="wan22_video_v2",
        image_ref_prefix=EXPECTED_WAN22_AIO_VIDEO_IMAGE_REF_PREFIX,
        supported_task_types=("wan22_video_v2",),
        model_prefix=EXPECTED_WAN22_VIDEO_V2_MODEL_PREFIX,
        model_manifest_key=EXPECTED_WAN22_VIDEO_V2_MODEL_MANIFEST_KEY,
        allow_template_id=True,
        expected_gpu_type_ids=EXPECTED_WAN22_AIO_VIDEO_GPU_TYPE_IDS,
        task_summary="submit wan22_video_v2 preview/5s Web task",
        worker_disable_summary="temporarily disable cloud-test workers supporting wan22_video_v2",
    ),
    "i2i_pro": RunPodCanaryProfileSpec(
        task_type="i2i_pro",
        image_ref_prefix=EXPECTED_I2I_PRO_IMAGE_REF_PREFIX,
        supported_task_types=RUNPOD_I2I_PRO_SUPPORTED_TASK_TYPES,
        model_prefix=EXPECTED_I2I_PRO_MODEL_PREFIX,
        model_manifest_key=EXPECTED_I2I_PRO_MODEL_MANIFEST_KEY,
        allow_template_id=True,
        expected_gpu_type_ids=EXPECTED_I2I_PRO_GPU_TYPE_IDS,
        workflow_overrides=RUNPOD_I2I_PRO_WORKFLOW_OVERRIDES,
        task_summary="submit i2i_pro, txt2img, and face_swap_v2 Web tasks serially",
        worker_disable_summary=(
            "temporarily disable cloud-test workers supporting i2i_pro, "
            "t2i-pornmaster-turbo, or face_swap_v2"
        ),
    ),
    "scail2": RunPodCanaryProfileSpec(
        task_type="scail2",
        image_ref_prefix=EXPECTED_SCAIL2_IMAGE_REF_PREFIX,
        supported_task_types=RUNPOD_SCAIL2_SUPPORTED_TASK_TYPES,
        model_prefix=EXPECTED_SCAIL2_MODEL_PREFIX,
        model_manifest_key=EXPECTED_SCAIL2_MODEL_MANIFEST_KEY,
        expected_gpu_type_ids=EXPECTED_SCAIL2_GPU_TYPE_IDS,
        task_summary=(
            "upload Nomadoor sample reference image and motion video, then submit "
            "scail2_action_transfer and scail2_video_replacement 5s Web tasks serially"
        ),
        worker_disable_summary=(
            "temporarily disable cloud-test workers supporting scail2_action_transfer "
            "or scail2_video_replacement"
        ),
    ),
    "ltx_video": RunPodCanaryProfileSpec(
        task_type="ltx_video",
        image_ref_prefix=EXPECTED_LTX_VIDEO_IMAGE_REF_PREFIX,
        supported_task_types=RUNPOD_LTX_VIDEO_SUPPORTED_TASK_TYPES,
        model_prefix=EXPECTED_LTX_VIDEO_MODEL_PREFIX,
        model_manifest_key=EXPECTED_LTX_VIDEO_MODEL_MANIFEST_KEY,
        expected_gpu_type_ids=EXPECTED_LTX_VIDEO_GPU_TYPE_IDS,
        workflow_overrides=RUNPOD_LTX_VIDEO_WORKFLOW_OVERRIDES,
        task_summary="submit ltx_video I2V preview/5s Web task",
        worker_disable_summary=(
            "temporarily disable cloud-test workers supporting ltx_video, "
            "ltx_video_flf2v, or ltx_video_v2v_audio"
        ),
    ),
    "ltx_t2v": RunPodCanaryProfileSpec(
        task_type="ltx_t2v",
        image_ref_prefix=EXPECTED_LTX_T2V_IMAGE_REF_PREFIX,
        supported_task_types=RUNPOD_LTX_T2V_SUPPORTED_TASK_TYPES,
        model_prefix=EXPECTED_LTX_T2V_MODEL_PREFIX,
        model_manifest_key=EXPECTED_LTX_T2V_MODEL_MANIFEST_KEY,
        expected_gpu_type_ids=EXPECTED_LTX_T2V_GPU_TYPE_IDS,
        task_summary="submit ltx_t2v and ltx_t2v_ic 5s Web tasks serially",
        worker_disable_summary=(
            "temporarily disable cloud-test workers supporting ltx_t2v or ltx_t2v_ic"
        ),
    ),
}


@dataclass(frozen=True)
class RunPodCanaryOptions:
    task_type: str = "img2img_lora"
    environment: str = "cloud-test"
    execute: bool = False
    cleanup: bool = True
    disable_workers: bool = True
    worker_ids: tuple[str, ...] = DEFAULT_WORKER_IDS
    worker_ids_explicit: bool = False
    web_api_url: str = ""
    central_url: str = ""
    web_user_id: int = 3
    web_pwd_ver: int = 1
    web_bearer_token: str = ""
    agent_token: str = ""
    input_object_key: str = ""
    scail2_reference_object_key: str = ""
    scail2_motion_video_object_key: str = ""
    output_dir: Path = Path("/tmp/allbot_runpod_canary")
    download_results_dir: Path | None = None
    readiness_timeout_seconds: float = 900.0
    worker_timeout_seconds: float = 600.0
    task_timeout_seconds: float = 1800.0
    poll_interval_seconds: float = 10.0
    task_poll_interval_seconds: float = 5.0
    control_ttl_seconds: int = 3600
    reuse_pod_ids: dict[str, str] = field(default_factory=dict)
    allow_existing_prod_managed_pods: bool = False
    prompt: str = "clean canary image transform, natural lighting, high quality"
    negative_prompt: str = "low quality, artifacts, text, watermark"
    quiet: bool = False


def load_env_file(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"loaded": False, "path": None}
    if not path.exists():
        raise RunPodCanaryError(f"env file not found: {path}")
    try:
        from dotenv import load_dotenv
    except Exception:
        _load_env_file_fallback(path)
    else:
        load_dotenv(path, override=False)
    return {"loaded": True, "path": str(path)}


def options_from_args_env(args: Any) -> RunPodCanaryOptions:
    control_host = (
        os.getenv("RUNPOD_CANARY_CONTROL_HOST")
        or os.getenv("CLOUD_TEST_CONTROL_HOST")
        or os.getenv("CLOUD_TEST_TAILSCALE_IP")
        or DEFAULT_CONTROL_HOST
    )
    arg_worker_ids = getattr(args, "worker_id", None)
    env_worker_ids = _worker_ids_from_env()
    worker_ids = tuple(arg_worker_ids or env_worker_ids)
    worker_ids_explicit = bool(arg_worker_ids) or bool(
        os.getenv("RUNPOD_CANARY_WORKER_IDS", "").strip()
    )
    return RunPodCanaryOptions(
        task_type=getattr(args, "task_type", "img2img_lora"),
        environment=getattr(args, "env", "cloud-test"),
        execute=bool(getattr(args, "execute", False)),
        cleanup=bool(getattr(args, "cleanup", True)),
        disable_workers=bool(getattr(args, "disable_workers", True)),
        worker_ids=worker_ids or DEFAULT_WORKER_IDS,
        worker_ids_explicit=worker_ids_explicit,
        web_api_url=(
            getattr(args, "web_api_url", None)
            or os.getenv("RUNPOD_CANARY_WEB_API_URL")
            or f"http://{control_host}:8001/api"
        ).rstrip("/"),
        central_url=(
            getattr(args, "central_url", None)
            or os.getenv("RUNPOD_CANARY_CENTRAL_URL")
            or f"http://{control_host}:8004"
        ).rstrip("/"),
        web_user_id=int(
            getattr(args, "web_user_id", None)
            or os.getenv("RUNPOD_CANARY_WEB_USER_ID")
            or "3"
        ),
        web_pwd_ver=int(
            getattr(args, "web_pwd_ver", None)
            or os.getenv("RUNPOD_CANARY_WEB_PWD_VER")
            or "1"
        ),
        web_bearer_token=os.getenv("RUNPOD_CANARY_WEB_BEARER_TOKEN", ""),
        agent_token=os.getenv("RUNPOD_CANARY_AGENT_TOKEN")
        or os.getenv("AGENT_SECRET_TOKEN", ""),
        input_object_key=(
            getattr(args, "input_object_key", None)
            or os.getenv("RUNPOD_CANARY_INPUT_OBJECT_KEY")
            or ""
        ),
        scail2_reference_object_key=(
            getattr(args, "scail2_reference_object_key", None)
            or os.getenv("RUNPOD_CANARY_SCAIL2_REFERENCE_OBJECT_KEY")
            or ""
        ),
        scail2_motion_video_object_key=(
            getattr(args, "scail2_motion_video_object_key", None)
            or os.getenv("RUNPOD_CANARY_SCAIL2_MOTION_VIDEO_OBJECT_KEY")
            or ""
        ),
        output_dir=Path(
            getattr(args, "output_dir", None)
            or os.getenv("RUNPOD_CANARY_OUTPUT_DIR")
            or "/tmp/allbot_runpod_canary"
        ),
        download_results_dir=_optional_path(
            getattr(args, "download_results_dir", None)
            or os.getenv("RUNPOD_CANARY_DOWNLOAD_RESULTS_DIR")
        ),
        readiness_timeout_seconds=float(getattr(args, "readiness_timeout", 900.0)),
        worker_timeout_seconds=float(getattr(args, "worker_timeout", 600.0)),
        task_timeout_seconds=float(getattr(args, "task_timeout", 1800.0)),
        poll_interval_seconds=float(getattr(args, "poll_interval", 10.0)),
        task_poll_interval_seconds=float(getattr(args, "task_poll_interval", 5.0)),
        control_ttl_seconds=int(getattr(args, "control_ttl", 3600)),
        reuse_pod_ids=_reuse_pod_ids_from_args_env(args),
        allow_existing_prod_managed_pods=bool(
            getattr(args, "allow_existing_prod_managed_pods", False)
        )
        or _bool_env(
            os.getenv("RUNPOD_CANARY_ALLOW_EXISTING_PROD_MANAGED_PODS"),
            default=False,
        ),
        prompt=(
            getattr(args, "prompt", None)
            or os.getenv("RUNPOD_CANARY_PROMPT")
            or RunPodCanaryOptions.prompt
        ),
        negative_prompt=(
            getattr(args, "negative_prompt", None)
            or os.getenv("RUNPOD_CANARY_NEGATIVE_PROMPT")
            or RunPodCanaryOptions.negative_prompt
        ),
        quiet=bool(getattr(args, "quiet", False)),
    )


def _load_env_file_fallback(path: Path) -> None:
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = _strip_env_quotes(value.strip())


def _strip_env_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _worker_ids_from_env() -> tuple[str, ...]:
    raw = os.getenv("RUNPOD_CANARY_WORKER_IDS", "")
    if not raw.strip():
        return DEFAULT_WORKER_IDS
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _bool_env(value: str | None, *, default: bool) -> bool:
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _reuse_pod_ids_from_args_env(args: Any) -> dict[str, str]:
    raw_values = list(getattr(args, "reuse_pod_id", None) or [])
    raw_env = os.getenv("RUNPOD_CANARY_REUSE_POD_IDS", "")
    if raw_env.strip():
        raw_values.extend(item.strip() for item in raw_env.split(",") if item.strip())
    reuse_pod_ids: dict[str, str] = {}
    for raw_value in raw_values:
        if "=" not in raw_value:
            raise RunPodCanaryError(
                "--reuse-pod-id must use PROFILE=POD_ID, for example "
                "wan22_video_v2=abc123"
            )
        profile, pod_id = (part.strip() for part in raw_value.split("=", 1))
        if not profile or not pod_id:
            raise RunPodCanaryError(
                "--reuse-pod-id must include both profile and pod id"
            )
        reuse_pod_ids[profile] = pod_id
    return reuse_pod_ids


def _optional_path(value: Any) -> Path | None:
    if value is None:
        return None
    raw = str(value).strip()
    return Path(raw) if raw else None


class RunPodCanaryRunner:
    def __init__(
        self,
        provider: RunPodProvider,
        options: RunPodCanaryOptions,
        *,
        sleep_func: Callable[[float], None] = time.sleep,
        emit_func: Callable[[str], None] | None = None,
    ) -> None:
        self.provider = provider
        self.options = options
        self._sleep = sleep_func
        self._emit_func = emit_func or (lambda message: print(message, file=sys.stderr))
        self._preflight_create_guard_pods: list[dict[str, Any]] = []
        self._http_client = RunPodHttpClient(error_type=RunPodCanaryError)

    def _control_config(self) -> RunPodControlConfig:
        return RunPodControlConfig(
            central_url=self.options.central_url,
            web_user_id=self.options.web_user_id,
            web_pwd_ver=self.options.web_pwd_ver,
            web_bearer_token=self.options.web_bearer_token,
            agent_token=self.options.agent_token,
            jwt_channel="runpod_canary",
            agent_token_required_message=(
                "AGENT_SECRET_TOKEN is required to disable/restore test workers"
            ),
        )

    def _control_client(self) -> RunPodControlClient:
        return RunPodControlClient(
            self._control_config(),
            http_json_func=self._http_json,
            error_type=RunPodCanaryError,
        )

    def _canary_config(self) -> RunPodCloudTestCanaryConfig:
        return RunPodCloudTestCanaryConfig(
            task_type=self.options.task_type,
            web_api_url=self.options.web_api_url,
            central_url=self.options.central_url,
            input_object_key=self.options.input_object_key,
            scail2_reference_object_key=self.options.scail2_reference_object_key,
            scail2_motion_video_object_key=self.options.scail2_motion_video_object_key,
            output_dir=self.options.output_dir,
            download_results_dir=self.options.download_results_dir,
            task_timeout_seconds=self.options.task_timeout_seconds,
            task_poll_interval_seconds=self.options.task_poll_interval_seconds,
            prompt=self.options.prompt,
            negative_prompt=self.options.negative_prompt,
            result_bucket=EXPECTED_TEST_BUCKET,
        )

    def _canary_cases(self) -> RunPodCloudTestCanaryCaseBuilder:
        return RunPodCloudTestCanaryCaseBuilder(
            self._canary_config(),
            error_type=RunPodCanaryError,
        )

    def _canary_assets(self) -> RunPodCloudTestCanaryAssets:
        return RunPodCloudTestCanaryAssets(
            self._canary_config(),
            http_json_func=self._http_json,
            http_request_func=self._http_request,
            web_auth_headers_func=self._web_auth_headers,
            phase_func=self._phase,
            error_type=RunPodCanaryError,
        )

    def _canary_executor(self) -> RunPodCloudTestCanaryExecutor:
        return RunPodCloudTestCanaryExecutor(
            self._canary_config(),
            http_json_func=self._http_json,
            http_request_func=self._http_request,
            web_auth_headers_func=self._web_auth_headers,
            fetch_workers_func=self._fetch_workers,
            sleep_func=self._sleep,
            phase_func=self._phase,
            error_type=RunPodCanaryError,
        )

    def run(self) -> dict[str, Any]:
        summary: dict[str, Any] = {
            "ok": False,
            "execute": self.options.execute,
            "environment": self.options.environment,
            "task_type": self.options.task_type,
            "started_at": _utc_now_iso(),
            "phases": [],
            "cleanup": {
                "requested": self.options.cleanup,
                "worker_restore": [],
            },
        }
        pod_id: str | None = None
        worker_controls: list[dict[str, Any]] = []
        target_agent_id: str | None = None
        pod_reused = False
        try:
            self._validate_static_options()
            self._run_runpod_preflight(summary)
            if not self.options.execute:
                spec = _canary_profile_spec(self.options.task_type)
                summary["ok"] = True
                summary["would_execute"] = [
                    "create one RunPod cloud-test pod",
                    "wait for infrastructure readiness and Central worker heartbeat",
                    spec.worker_disable_summary,
                    "upload or reuse test input object(s) in user-data-test",
                    spec.task_summary,
                    "optionally download generated results to a local directory",
                    "restore test workers and delete the RunPod pod",
                ]
            else:
                self._run_web_preflight(summary)
                if self.options.reuse_pod_ids:
                    create_payload = self._reuse_pod(summary)
                    pod_reused = True
                else:
                    create_payload = self._create_pod(summary)
                pod_id = _extract_pod_id(create_payload)
                pod_summary = _pod_summary(
                    create_payload,
                    self._render_image_ref(summary),
                )
                if pod_reused:
                    pod_summary["reused"] = True
                summary["pod"] = pod_summary
                self._wait_pod_readiness(pod_id, summary)
                runpod_worker = self._wait_runpod_worker(pod_id, summary)
                target_agent_id = str(runpod_worker.get("agent_id") or "")

                if (
                    RUNPOD_TASK_PROFILES[self.options.task_type].task_type == "ltx_t2v"
                    and not pod_reused
                ):
                    self._set_agent_control(
                        target_agent_id,
                        "disabled",
                        reason="runpod_ltx_t2v_default_disabled",
                        ttl_seconds=self.options.control_ttl_seconds,
                    )
                    summary["target_agent_control"] = {
                        "agent_id": target_agent_id,
                        "initial_state": "disabled",
                    }

                if self.options.disable_workers:
                    worker_controls = self._disable_test_workers(summary)

                if summary.get("target_agent_control"):
                    self._set_agent_control(
                        target_agent_id,
                        "enabled",
                        reason="runpod_ltx_t2v_canary",
                        ttl_seconds=self.options.control_ttl_seconds,
                    )
                    summary["target_agent_control"]["canary_state"] = "enabled"

                test_input = self._resolve_canary_inputs(summary)
                summary["test_input"] = test_input
                summary["tasks"] = []
                for task_case in self._task_cases(test_input):
                    task_result = self._run_task_case(task_case, runpod_worker, summary)
                    summary["tasks"].append(task_result)

                summary["ok"] = True
        except KeyboardInterrupt:
            summary["ok"] = False
            summary["error"] = "interrupted"
        except Exception as exc:
            summary["ok"] = False
            summary["error"] = redact_text(str(exc))
        finally:
            if self.options.execute:
                self._cleanup(
                    summary=summary,
                    pod_id=pod_id,
                    pod_reused=pod_reused,
                    worker_controls=worker_controls,
                    target_agent_id=target_agent_id,
                )
        return self._finish(summary)

    def _validate_static_options(self) -> None:
        if self.options.environment != "cloud-test":
            raise RunPodCanaryError("runpod canary only supports --env cloud-test")
        if self.options.task_type not in RUNPOD_TASK_PROFILES:
            supported = ", ".join(sorted(RUNPOD_TASK_PROFILES))
            raise RunPodCanaryError(f"runpod canary only supports: {supported}")
        if self.options.reuse_pod_ids:
            profile = RUNPOD_TASK_PROFILES[self.options.task_type].task_type
            reuse_profiles = set(self.options.reuse_pod_ids)
            if reuse_profiles != {profile}:
                raise RunPodCanaryError(
                    "--reuse-pod-id must provide exactly "
                    f"{profile}=POD_ID for this canary"
                )
        if self.options.execute:
            settings = self.provider.settings
            missing_gates: list[str] = []
            if settings.dry_run:
                missing_gates.append("RUNPOD_DRY_RUN=false")
            if not settings.autoscaler_enabled:
                missing_gates.append("RUNPOD_AUTOSCALER_ENABLED=true")
            if settings.max_pods_total != 1:
                missing_gates.append("RUNPOD_MAX_PODS_TOTAL=1")
            if settings.max_pods_per_type != 1:
                missing_gates.append("RUNPOD_MAX_PODS_PER_TYPE=1")
            if missing_gates:
                raise RunPodCanaryError(
                    "execute requires RunPod canary gates: " + ", ".join(missing_gates)
                )
            if self.options.disable_workers and not self.options.agent_token:
                raise RunPodCanaryError(
                    "AGENT_SECRET_TOKEN is required to disable/restore test workers"
                )

    def _run_runpod_preflight(self, summary: dict[str, Any]) -> None:
        self._phase(summary, "runpod_validate_key", "running")
        validate = self.provider.validate_key()
        self._require_ok(validate, "runpod validate-key failed")
        self._phase(summary, "runpod_validate_key", "ok")

        self._phase(summary, "runpod_list_pods", "running")
        listed = self.provider.list_pods(managed_only=True)
        self._require_ok(listed, "runpod list-pods failed")
        listed_pods = list(listed.get("pods") or [])
        guard_pods, ignored_pods = self._pods_relevant_to_canary(listed_pods)
        self._preflight_create_guard_pods = list(guard_pods)
        if self.options.execute and guard_pods:
            raise RunPodCanaryError(
                "refusing canary: managed RunPod pod count is not 0"
            )
        self._phase(
            summary,
            "runpod_list_pods",
            "ok",
            {
                "count": listed.get("count", 0),
                "effective_count": len(guard_pods),
                "ignored_prod_manual_count": len(ignored_pods),
                "reused_count": self._reused_pod_count(listed_pods),
            },
        )

        self._phase(summary, "runpod_reconcile", "running")
        reconcile = self.provider.reconcile_managed_pods(pods=guard_pods)
        self._require_ok(reconcile, "runpod reconcile-managed-pods failed")
        if self.options.execute and int(reconcile.get("managed_count") or 0) != 0:
            raise RunPodCanaryError(
                "refusing canary: managed RunPod reconcile count is not 0"
            )
        self._phase(
            summary,
            "runpod_reconcile",
            "ok",
            {
                "managed_count": reconcile.get("managed_count", 0),
                "orphans": reconcile.get("orphans", []),
                "ignored_prod_manual_count": len(ignored_pods),
            },
        )

        self._phase(summary, "runpod_render_create", "running")
        render = self.provider.render_create_pod_request(
            task_type=self.options.task_type,
            environment=self.options.environment,
            redact=False,
        )
        self._validate_render(render)
        summary["render"] = self._render_summary(render)
        self._phase(summary, "runpod_render_create", "ok", summary["render"])

    def _run_web_preflight(self, summary: dict[str, Any]) -> None:
        self._phase(summary, "web_and_central_preflight", "running")
        self._web_token()
        self._http_json("GET", _join_url(self.options.web_api_url, "health"))
        self._http_json("GET", _join_url(self.options.central_url, "health"))
        self._http_json(
            "GET",
            _join_url(self.options.web_api_url, "tasks", "queue-status"),
            headers=self._web_auth_headers(),
        )
        self._phase(
            summary,
            "web_and_central_preflight",
            "ok",
            {
                "web_api_url": self.options.web_api_url,
                "central_url": self.options.central_url,
                "web_user_id": self.options.web_user_id,
            },
        )

    def _create_pod(self, summary: dict[str, Any]) -> dict[str, Any]:
        self._phase(summary, "runpod_create_pod", "running")
        payload = self.provider.create_pod(
            task_type=self.options.task_type,
            environment=self.options.environment,
            existing_pods=self._preflight_create_guard_pods,
            execute=True,
        )
        self._require_ok(payload, "runpod create-pod failed")
        pod_id = _extract_pod_id(payload)
        self._phase(summary, "runpod_create_pod", "ok", {"pod_id": pod_id})
        return payload

    def _reuse_pod(self, summary: dict[str, Any]) -> dict[str, Any]:
        profile = RUNPOD_TASK_PROFILES[self.options.task_type].task_type
        pod_id = self.options.reuse_pod_ids[profile]
        self._phase(
            summary,
            "runpod_reuse_pod",
            "ok",
            {"profile": profile, "pod_id": pod_id},
        )
        return {"ok": True, "pod": {"id": pod_id}}

    def _wait_pod_readiness(self, pod_id: str, summary: dict[str, Any]) -> None:
        self._phase(summary, "pod_readiness", "running", {"pod_id": pod_id})
        deadline = time.monotonic() + self.options.readiness_timeout_seconds
        last_payload: dict[str, Any] | None = None
        while time.monotonic() <= deadline:
            payload = self.provider.pod_readiness(pod_id=pod_id)
            self._require_ok(payload, "runpod pod-readiness failed")
            last_payload = payload
            readiness = payload.get("readiness") or {}
            if readiness.get("infrastructure_ready") is True:
                summary["pod_readiness"] = {
                    "pod_id": pod_id,
                    "confidence": readiness.get("confidence"),
                    "network": readiness.get("network"),
                }
                self._phase(summary, "pod_readiness", "ok", summary["pod_readiness"])
                return
            self._sleep(self.options.poll_interval_seconds)
        raise RunPodCanaryError(
            "pod readiness timeout: "
            + json.dumps(redact_payload(last_payload), ensure_ascii=False)
        )

    def _wait_runpod_worker(
        self, pod_id: str, summary: dict[str, Any]
    ) -> dict[str, Any]:
        profile = RUNPOD_TASK_PROFILES[self.options.task_type]
        expected_agent_id = f"{profile.agent_id_prefix}_{pod_id}"
        self._phase(
            summary, "central_runpod_worker", "running", {"agent_id": expected_agent_id}
        )
        deadline = time.monotonic() + self.options.worker_timeout_seconds
        last_workers: list[dict[str, Any]] = []
        while time.monotonic() <= deadline:
            workers = self._fetch_workers()
            last_workers = workers
            worker = _find_runpod_worker(
                workers,
                expected_agent_id=expected_agent_id,
                agent_id_prefix=profile.agent_id_prefix,
            )
            if worker and _worker_supports_expected_types(
                worker,
                expected_types=_expected_task_types(self.options.task_type),
            ):
                status = str(worker.get("status") or "")
                if status in HEALTHY_WORKER_STATUSES:
                    summary["runpod_worker"] = _worker_summary(worker)
                    self._phase(
                        summary, "central_runpod_worker", "ok", summary["runpod_worker"]
                    )
                    return worker
            self._sleep(self.options.poll_interval_seconds)
        raise RunPodCanaryError(
            "runpod worker heartbeat timeout: "
            + json.dumps(
                {
                    "expected_agent_id": expected_agent_id,
                    "runpod_workers": [
                        _worker_summary(worker)
                        for worker in last_workers
                        if str(worker.get("agent_id") or "").startswith(
                            f"{profile.agent_id_prefix}_"
                        )
                    ],
                },
                ensure_ascii=False,
            )
        )

    def _disable_test_workers(self, summary: dict[str, Any]) -> list[dict[str, Any]]:
        self._phase(summary, "disable_test_workers", "running")
        controls: list[dict[str, Any]] = []
        agent_ids = self._worker_ids_to_disable()
        for agent_id in agent_ids:
            current = self._get_agent_control(agent_id)
            controls.append(
                {
                    "agent_id": agent_id,
                    "state": current.get("state", "enabled"),
                    "reason": current.get("reason", ""),
                }
            )
            self._set_agent_control(
                agent_id,
                "disabled",
                reason="runpod_canary",
                ttl_seconds=self.options.control_ttl_seconds,
            )
        self._phase(
            summary,
            "disable_test_workers",
            "ok",
            {"disabled": [item["agent_id"] for item in controls]},
        )
        return controls

    def _worker_ids_to_disable(self) -> tuple[str, ...]:
        profile = RUNPOD_TASK_PROFILES[self.options.task_type]
        if profile.task_type == "img2img_lora" or self.options.worker_ids_explicit:
            return self.options.worker_ids
        return select_cloud_test_worker_ids_to_disable(
            self._fetch_workers(),
            expected_types=_expected_task_types(self.options.task_type),
        )

    def _upload_canary_image(self, summary: dict[str, Any]) -> str:
        return self._canary_assets().upload_canary_image(summary)

    def _upload_bytes_to_user_data(
        self,
        *,
        filename: str,
        content_type: str,
        body: bytes,
    ) -> str:
        return self._canary_assets().upload_bytes_to_user_data(
            filename=filename,
            content_type=content_type,
            body=body,
        )

    def _resolve_canary_image(self, summary: dict[str, Any]) -> str:
        return self._canary_assets().resolve_canary_image(summary)

    def _resolve_canary_inputs(self, summary: dict[str, Any]) -> dict[str, str]:
        profile = RUNPOD_TASK_PROFILES[self.options.task_type]
        if profile.task_type == "scail2":
            return self._resolve_scail2_inputs(summary)
        image_object_key = self._resolve_canary_image(summary)
        return {"object_key": image_object_key}

    def _resolve_scail2_inputs(self, summary: dict[str, Any]) -> dict[str, str]:
        return self._canary_assets().resolve_scail2_inputs(summary)

    def _download_scail2_sample(self, url: str, *, label: str) -> bytes:
        return self._canary_assets().download_scail2_sample(url, label=label)

    def _run_task_case(
        self,
        task_case: dict[str, Any],
        runpod_worker: dict[str, Any],
        summary: dict[str, Any],
    ) -> dict[str, Any]:
        return self._canary_executor().run_task_case(
            task_case,
            runpod_worker,
            summary,
        )

    def _fetch_result_bytes(self, result_url: str) -> tuple[bytes, str]:
        return self._canary_executor().fetch_result_bytes(result_url)

    def _download_result_if_requested(
        self,
        *,
        label: str,
        task_id: str,
        result_url: str,
    ) -> dict[str, str]:
        return self._canary_executor().download_result_if_requested(
            label=label,
            task_id=task_id,
            result_url=result_url,
        )

    def _validate_wan22_last_frame_if_required(
        self,
        *,
        label: str,
        task_id: str,
        result_payload: dict[str, Any],
    ) -> dict[str, Any]:
        return self._canary_executor().validate_wan22_last_frame_if_required(
            label=label,
            task_id=task_id,
            result_payload=result_payload,
        )

    def _download_result_bytes_from_s3(self, result_url: str) -> bytes:
        return self._canary_executor().download_result_bytes_from_s3(result_url)

    def _wait_task_done(
        self,
        *,
        task_id: str,
        expected_worker_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        return self._canary_executor().wait_task_done(
            task_id=task_id,
            expected_worker_id=expected_worker_id,
        )

    def _wait_web_result(self, task_id: str) -> dict[str, Any]:
        return self._canary_executor().wait_web_result(task_id)

    def _cleanup(
        self,
        *,
        summary: dict[str, Any],
        pod_id: str | None,
        pod_reused: bool,
        worker_controls: list[dict[str, Any]],
        target_agent_id: str | None,
    ) -> None:
        cleanup = summary.setdefault("cleanup", {})
        cleanup_errors: list[str] = []
        if target_agent_id and summary.get("target_agent_control") and not pod_reused:
            try:
                self._set_agent_control(
                    target_agent_id,
                    "disabled",
                    reason="runpod_ltx_t2v_canary_complete",
                    ttl_seconds=self.options.control_ttl_seconds,
                )
                cleanup["target_agent_disable"] = {
                    "agent_id": target_agent_id,
                    "ok": True,
                }
            except Exception as exc:
                cleanup_errors.append(
                    f"disable target {target_agent_id}: {redact_text(str(exc))}"
                )
                cleanup["target_agent_disable"] = {
                    "agent_id": target_agent_id,
                    "ok": False,
                }
        if worker_controls:
            for control in worker_controls:
                agent_id = str(control.get("agent_id") or "")
                state = str(control.get("state") or "enabled")
                reason = str(control.get("reason") or "runpod_canary_restore")
                try:
                    self._set_agent_control(agent_id, state, reason=reason)
                    cleanup.setdefault("worker_restore", []).append(
                        {"agent_id": agent_id, "state": state, "ok": True}
                    )
                except Exception as exc:
                    cleanup_errors.append(
                        f"restore {agent_id}: {redact_text(str(exc))}"
                    )
                    cleanup.setdefault("worker_restore", []).append(
                        {"agent_id": agent_id, "state": state, "ok": False}
                    )
        if pod_id and self.options.cleanup and not pod_reused:
            try:
                delete_payload = self.provider.delete_pod(
                    pod_id=pod_id,
                    task_type=self.options.task_type,
                    execute=True,
                )
                if not delete_payload.get("ok"):
                    raise RunPodCanaryError(
                        str(delete_payload.get("error") or "delete failed")
                    )
                cleanup["pod_delete"] = {"pod_id": pod_id, "ok": True}
            except Exception as exc:
                cleanup_errors.append(f"delete pod {pod_id}: {redact_text(str(exc))}")
                cleanup["pod_delete"] = {"pod_id": pod_id, "ok": False}
        elif pod_id and pod_reused:
            cleanup["pod_delete"] = {
                "pod_id": pod_id,
                "ok": False,
                "skipped": True,
                "reused": True,
            }
        elif pod_id:
            cleanup["pod_delete"] = {"pod_id": pod_id, "ok": False, "skipped": True}
        try:
            listed = self.provider.list_pods(managed_only=True)
            listed_pods = list(listed.get("pods") or [])
            guard_pods, ignored_pods = self._pods_relevant_to_canary(listed_pods)
            reconcile = self.provider.reconcile_managed_pods(pods=guard_pods)
            cleanup["post_list_pods"] = {
                "ok": listed.get("ok"),
                "count": listed.get("count"),
                "effective_count": len(guard_pods),
                "ignored_prod_manual_count": len(ignored_pods),
                "reused_count": self._reused_pod_count(listed_pods),
            }
            cleanup["post_reconcile"] = {
                "ok": reconcile.get("ok"),
                "managed_count": reconcile.get("managed_count"),
            }
            if self.options.cleanup and int(reconcile.get("managed_count") or 0) != 0:
                cleanup_errors.append("post cleanup managed RunPod pod count is not 0")
        except Exception as exc:
            cleanup_errors.append(f"post cleanup reconcile: {redact_text(str(exc))}")
        if cleanup_errors:
            cleanup["errors"] = cleanup_errors
            summary["ok"] = False
            summary["error"] = summary.get("error") or "cleanup failed"

    def _pods_relevant_to_canary(
        self, pods: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        reused_pod_ids = set(self.options.reuse_pod_ids.values())
        relevant: list[dict[str, Any]] = []
        ignored: list[dict[str, Any]] = []
        for pod in pods:
            pod_id = _pod_identifier(pod)
            if pod_id in reused_pod_ids:
                ignored.append(pod)
                continue
            if self.options.allow_existing_prod_managed_pods and _is_prod_manual_pod(
                pod
            ):
                ignored.append(pod)
                continue
            relevant.append(pod)
        return relevant, ignored

    def _reused_pod_count(self, pods: list[dict[str, Any]]) -> int:
        reused_pod_ids = set(self.options.reuse_pod_ids.values())
        if not reused_pod_ids:
            return 0
        return sum(1 for pod in pods if _pod_identifier(pod) in reused_pod_ids)

    def _task_cases(self, test_input: str | dict[str, str]) -> list[dict[str, Any]]:
        return self._canary_cases().task_cases(test_input)

    def _img2img_task_cases(self, image_object_key: str) -> list[dict[str, Any]]:
        return self._canary_cases().img2img_task_cases(image_object_key)

    def _wan22_aio_video_task_cases(
        self, image_object_key: str
    ) -> list[dict[str, Any]]:
        return self._canary_cases().wan22_aio_video_task_cases(image_object_key)

    def _i2i_pro_task_cases(self, image_object_key: str) -> list[dict[str, Any]]:
        return self._canary_cases().i2i_pro_task_cases(image_object_key)

    def _scail2_task_cases(self, test_input: dict[str, str]) -> list[dict[str, Any]]:
        return self._canary_cases().scail2_task_cases(test_input)

    def _validate_render(self, render: dict[str, Any]) -> None:
        spec = _canary_profile_spec(self.options.task_type)
        body = render.get("json") or {}
        env = body.get("env") or {}
        failures: list[str] = []
        image_name = str(body.get("imageName") or "")
        template_id = str(body.get("templateId") or "")
        digest_prefix = spec.image_ref_prefix.removesuffix(":") + "@sha256:"
        uses_canonical_digest = bool(
            re.fullmatch(re.escape(digest_prefix) + r"[0-9a-f]{64}", image_name)
        )
        uses_public_image = (
            image_name.startswith(spec.image_ref_prefix) or uses_canonical_digest
        )
        if template_id and not spec.allow_template_id:
            failures.append("templateId must be empty for baked GHCR canary")
        if image_name and not uses_public_image:
            failures.append(
                f"imageName must use public GHCR prefix {spec.image_ref_prefix}"
            )
        if not template_id and not uses_public_image:
            failures.append(
                f"imageName must use public GHCR prefix {spec.image_ref_prefix}"
            )
        if spec.task_type == "ltx_t2v" and not uses_canonical_digest:
            failures.append("ltx_t2v imageName must use an exact sha256 digest")
        if (
            spec.expected_gpu_type_ids
            and tuple(body.get("gpuTypeIds") or ()) != spec.expected_gpu_type_ids
        ):
            failures.append(
                "gpuTypeIds must be " + ",".join(spec.expected_gpu_type_ids)
            )
        expected_env = {
            "CENTRAL_API_URL": EXPECTED_RUNPOD_CLOUD_TEST_CENTRAL_URL,
            "SUPPORTED_TASK_TYPES": ",".join(spec.supported_task_types),
            "MINIO_INPUT_BUCKET": EXPECTED_TEST_BUCKET,
            "MINIO_RESULT_BUCKET": EXPECTED_TEST_BUCKET,
            "MINIO_TEMPLATE_BUCKET": EXPECTED_TEST_BUCKET,
            "RUNPOD_MODEL_SYNC_ENABLED": "true",
            "RUNPOD_MODEL_BUCKET": EXPECTED_MODEL_BUCKET,
            "RUNPOD_MODEL_PREFIX": spec.model_prefix,
            "RUNPOD_MODEL_MANIFEST_KEY": spec.model_manifest_key,
            "RUNPOD_COMFY_CUSTOM_NODES_ENABLED": "false",
            "RUNPOD_COMFY_KJNODES_ENABLED": "false",
        }
        for key, expected in expected_env.items():
            if str(env.get(key) or "") != expected:
                failures.append(f"{key} must be {expected}")
        if (
            spec.workflow_overrides
            and str(env.get("TASK_TYPE_WORKFLOW_OVERRIDES") or "")
            != spec.workflow_overrides
        ):
            failures.append(
                "TASK_TYPE_WORKFLOW_OVERRIDES must match the i2i_pro multitask override"
            )
        if spec.task_type == "scail2" and tuple(body.get("dockerStartCmd") or ()) != (
            RUNPOD_SCAIL2_DOCKER_START_CMD
        ):
            failures.append(
                "dockerStartCmd must start the RunPod git bootstrap for scail2"
            )
        for key in (
            "AGENT_SECRET_TOKEN",
            "MINIO_ACCESS_KEY",
            "MINIO_SECRET_KEY",
            "RUNPOD_MODEL_ACCESS_KEY",
            "RUNPOD_MODEL_SECRET_KEY",
        ):
            value = str(env.get(key) or "")
            if not value.startswith("{{ RUNPOD_SECRET_"):
                failures.append(f"{key} must use a RunPod secret reference")
        if failures:
            raise RunPodCanaryError(
                "render-create sanity check failed: " + "; ".join(failures)
            )

    def _render_summary(self, render: dict[str, Any]) -> dict[str, Any]:
        body = render.get("json") or {}
        env = body.get("env") or {}
        return {
            "imageName": body.get("imageName"),
            "templateId": body.get("templateId"),
            "uses_template": bool(body.get("templateId")),
            "gpu_type_ids": body.get("gpuTypeIds") or [],
            "central_api_url": env.get("CENTRAL_API_URL"),
            "supported_task_types": env.get("SUPPORTED_TASK_TYPES"),
            "model_bucket": env.get("RUNPOD_MODEL_BUCKET"),
            "model_prefix": env.get("RUNPOD_MODEL_PREFIX"),
            "model_manifest_key": env.get("RUNPOD_MODEL_MANIFEST_KEY"),
            "workflow_overrides": env.get("TASK_TYPE_WORKFLOW_OVERRIDES"),
            "docker_start_cmd": body.get("dockerStartCmd") or [],
            "custom_nodes_enabled": env.get("RUNPOD_COMFY_CUSTOM_NODES_ENABLED"),
            "kjnodes_enabled": env.get("RUNPOD_COMFY_KJNODES_ENABLED"),
            "buckets": {
                "input": env.get("MINIO_INPUT_BUCKET"),
                "result": env.get("MINIO_RESULT_BUCKET"),
                "template": env.get("MINIO_TEMPLATE_BUCKET"),
            },
        }

    def _render_image_ref(self, summary: dict[str, Any]) -> str:
        render = summary.get("render") or {}
        return str(render.get("imageName") or "")

    def _get_agent_control(self, agent_id: str) -> dict[str, Any]:
        return self._control_client().get_agent_control(agent_id)

    def _set_agent_control(
        self,
        agent_id: str,
        state: str,
        *,
        reason: str,
        ttl_seconds: int | None = None,
    ) -> dict[str, Any]:
        return self._control_client().set_agent_control(
            agent_id,
            state,
            reason=reason,
            ttl_seconds=ttl_seconds,
        )

    def _fetch_workers(self) -> list[dict[str, Any]]:
        return self._control_client().fetch_workers()

    def _web_token(self) -> str:
        return self._control_client().web_token()

    def _web_auth_headers(self) -> dict[str, str]:
        return self._control_client().web_auth_headers()

    def _agent_headers(self) -> dict[str, str]:
        return self._control_client().agent_headers()

    def _http_json(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        expected_statuses: tuple[int, ...] = (200,),
        allow_statuses: tuple[int, ...] = (),
    ) -> dict[str, Any]:
        return self._http_client.json(
            method,
            url,
            params=params,
            json_body=json_body,
            headers=headers,
            expected_statuses=expected_statuses,
            allow_statuses=allow_statuses,
        )

    def _http_bytes(
        self,
        method: str,
        url: str,
        *,
        body: bytes,
        headers: dict[str, str] | None = None,
        expected_statuses: tuple[int, ...] = (200,),
    ) -> dict[str, Any]:
        return self._http_request(
            method,
            url,
            body=body,
            headers=headers or {},
            expected_statuses=expected_statuses,
        )

    def _http_request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
        expected_statuses: tuple[int, ...] = (200,),
        allow_statuses: tuple[int, ...] = (),
    ) -> dict[str, Any]:
        return self._http_client.request(
            method,
            url,
            params=params,
            body=body,
            headers=headers,
            expected_statuses=expected_statuses,
            allow_statuses=allow_statuses,
        )

    def _phase(
        self,
        summary: dict[str, Any],
        name: str,
        status: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        entry = {
            "name": name,
            "status": status,
            "at": _utc_now_iso(),
        }
        if details:
            entry["details"] = redact_payload(details)
        summary.setdefault("phases", []).append(entry)
        if not self.options.quiet:
            self._emit_func(f"[runpod-canary] {name}: {status}")

    @staticmethod
    def _require_ok(payload: dict[str, Any], message: str) -> None:
        if not payload.get("ok"):
            raise RunPodCanaryError(
                f"{message}: {redact_text(str(payload.get('error') or payload))}"
            )

    @staticmethod
    def _finish(summary: dict[str, Any]) -> dict[str, Any]:
        summary["ended_at"] = _utc_now_iso()
        return redact_payload(summary)


def write_canary_png(path: Path, *, width: int = 512, height: int = 512) -> None:
    rows = bytearray()
    for y in range(height):
        rows.append(0)
        for x in range(width):
            rows.extend(
                (
                    72 + (x % 48),
                    126 + (y % 48),
                    168 + ((x + y) % 48),
                )
            )
    png = bytearray(b"\x89PNG\r\n\x1a\n")
    png.extend(
        _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    )
    png.extend(_png_chunk(b"IDAT", zlib.compress(bytes(rows), level=6)))
    png.extend(_png_chunk(b"IEND", b""))
    path.write_bytes(bytes(png))


def result_url_path(url: str) -> str:
    if not url:
        return ""
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme or parsed.netloc:
        return parsed.path
    return urllib.parse.urlunsplit(parsed._replace(query="", fragment=""))


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    checksum = zlib.crc32(kind + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", checksum)


def _join_url(base: str, *parts: str) -> str:
    return "/".join([base.rstrip("/"), *(part.strip("/") for part in parts if part)])


def _utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


def _safe_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit(parsed._replace(query="", fragment=""))


def _extract_pod_id(payload: dict[str, Any]) -> str:
    pod = payload.get("pod") or payload.get("response") or payload
    if isinstance(pod, dict):
        for key in ("id", "podId", "pod_id"):
            value = pod.get(key)
            if value:
                return str(value)
        data = pod.get("data")
        if isinstance(data, dict):
            for key in ("id", "podId", "pod_id"):
                value = data.get(key)
                if value:
                    return str(value)
    raise RunPodCanaryError("RunPod create response did not include pod id")


def _pod_identifier(pod: dict[str, Any]) -> str:
    for key in ("id", "podId", "pod_id"):
        value = pod.get(key)
        if value:
            return str(value)
    return str(pod.get("name") or "")


def _is_prod_manual_pod(pod: dict[str, Any]) -> bool:
    name = str(pod.get("name") or "")
    return any(name.startswith(prefix) for prefix in PROD_MANUAL_POD_NAME_PREFIXES)


def _pod_summary(payload: dict[str, Any], image_ref: str) -> dict[str, Any]:
    pod = payload.get("pod") or payload.get("response") or payload
    if not isinstance(pod, dict):
        pod = {}
    machine = pod.get("machine") if isinstance(pod.get("machine"), dict) else {}
    return {
        "pod_id": _extract_pod_id(payload),
        "name": pod.get("name"),
        "gpu": (
            pod.get("gpuTypeId")
            or pod.get("gpuType")
            or machine.get("gpuDisplayName")
            or machine.get("gpuType")
        ),
        "image": pod.get("imageName") or pod.get("image") or image_ref,
        "created_at": pod.get("createdAt") or pod.get("created_at"),
        "cost_per_hr": pod.get("costPerHr") or pod.get("adjustedCostPerHr"),
    }


def _canary_profile_spec(task_type: str) -> RunPodCanaryProfileSpec:
    profile = RUNPOD_TASK_PROFILES[task_type]
    try:
        return RUNPOD_CANARY_PROFILE_SPECS[profile.task_type]
    except KeyError as exc:
        raise RunPodCanaryError(
            f"missing runpod canary profile spec: {profile.task_type}"
        ) from exc


def _expected_task_types(task_type: str) -> tuple[str, ...]:
    return _canary_profile_spec(task_type).supported_task_types


def _worker_types(worker: dict[str, Any]) -> set[str]:
    raw_types = worker.get("types") or worker.get("supported_task_types") or ""
    if isinstance(raw_types, (list, tuple, set)):
        return {str(item).strip() for item in raw_types if str(item).strip()}
    return {item.strip() for item in str(raw_types).split(",") if item.strip()}


def _is_cloud_test_non_runpod_worker(worker: dict[str, Any]) -> bool:
    agent_id = str(worker.get("agent_id") or "")
    provider = str(worker.get("provider") or "").strip().lower()
    return agent_id.startswith("cloud_worker_test_") and provider != "runpod"


def _find_runpod_worker(
    workers: list[dict[str, Any]],
    *,
    expected_agent_id: str,
    agent_id_prefix: str,
) -> dict[str, Any] | None:
    fallback: dict[str, Any] | None = None
    for worker in workers:
        agent_id = str(worker.get("agent_id") or "")
        if agent_id == expected_agent_id:
            return worker
        if agent_id.startswith(f"{agent_id_prefix}_"):
            fallback = worker
    return fallback


def _find_worker_current_task(
    workers: list[dict[str, Any]],
    expected_agent_id: str,
    task_id: str,
) -> dict[str, Any] | None:
    for worker in workers:
        if str(worker.get("agent_id") or "") != expected_agent_id:
            continue
        if str(worker.get("current_task_id") or "") == task_id:
            return worker
    return None


def _worker_supports_expected_types(
    worker: dict[str, Any],
    *,
    expected_types: tuple[str, ...],
) -> bool:
    return set(expected_types).issubset(_worker_types(worker))


def _worker_supports_any_expected_type(
    worker: dict[str, Any],
    *,
    expected_types: tuple[str, ...],
) -> bool:
    return bool(set(expected_types).intersection(_worker_types(worker)))


def _worker_summary(worker: dict[str, Any]) -> dict[str, Any]:
    return {
        "agent_id": worker.get("agent_id"),
        "types": worker.get("types"),
        "status": worker.get("status"),
        "provider": worker.get("provider"),
        "runtime_profile": worker.get("runtime_profile"),
        "image_ref": worker.get("image_ref"),
        "current_task_id": worker.get("current_task_id"),
        "current_task_type": worker.get("current_task_type"),
    }
