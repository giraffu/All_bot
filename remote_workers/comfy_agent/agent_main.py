import asyncio
import json
import logging
import os
import sys
import time
from typing import Any, Dict, Optional

import httpx
import urllib3
import websockets  # type: ignore
from asgi_correlation_id import correlation_id
from agent_input_preparation import (
    prepare_task_inputs as prepare_agent_task_inputs,
    process_single_input_asset as process_agent_single_input_asset,
)
from agent_result_assets import (
    build_safe_result_object_name,
    extract_ws_data_content,
    pick_first_output_asset,
    result_asset_priority,
)
from agent_result_materialization import (
    materialize_task_outputs,
    resolve_execution_result_from_history,
)
from agent_result_reporting import (
    report_materialized_outputs,
    spool_materialized_outputs,
    upload_materialized_outputs,
    upload_spooled_outputs_via_sidecar,
)
from agent_runtime_types import TaskExecutionContext
from agent_workflow_execution import (
    TaskExecutionTimeoutError,
    submit_task_workflow,
    wait_for_task_completion,
)
from comfy_client import ComfyClient
from dotenv import load_dotenv
from minio import Minio  # type: ignore
from PIL import Image, ImageOps, UnidentifiedImageError
from workflow_patcher import WorkflowPatcher

# Load environment variables
load_dotenv()

# Unset proxies to prevent internal requests from being routed through system VPN/proxies
for proxy_var in [
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
]:
    os.environ.pop(proxy_var, None)
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"

TRUE_ENV_VALUES = {
    "1",
    "true",
    "yes",
    "on",
}


class CorrelationIdFilter(logging.Filter):
    def filter(self, record):
        trace_id = correlation_id.get()
        record.correlation_id = f"TraceID: {trace_id}" if trace_id else "TraceID: None"
        return True


# Configuration
AGENT_ID = os.getenv("AGENT_ID", "worker_local_01")
SUPPORTED_TASK_TYPES = os.getenv("SUPPORTED_TASK_TYPES", "img2img,face_swap")
MASTER_API_URL = os.getenv("MASTER_API_URL", "http://127.0.0.1:8000")
AGENT_SECRET_TOKEN = os.getenv("AGENT_SECRET_TOKEN", "")
POOL_NODE_ID = os.getenv("POOL_NODE_ID", "")
POOL_PROVIDER = os.getenv("POOL_PROVIDER", "")
POOL_GPU_INDEX = os.getenv("POOL_GPU_INDEX", "")
POOL_RUNTIME_PROFILE = os.getenv("POOL_RUNTIME_PROFILE", "")
POOL_IMAGE_REF = os.getenv("POOL_IMAGE_REF", "")
POOL_MODEL_BUNDLE_VERSIONS = os.getenv("POOL_MODEL_BUNDLE_VERSIONS", "")
POOL_MANAGED = os.getenv("POOL_MANAGED", "")

COMFY_API_URL = os.getenv("COMFY_API_URL", "http://127.0.0.1:8188")
COMFY_WS_URL = os.getenv("COMFY_WS_URL", "ws://127.0.0.1:8188/ws")
COMFY_INPUT_DIR = os.getenv("COMFY_INPUT_DIR", "/tmp/input")
COMFY_OUTPUT_DIR = os.getenv("COMFY_OUTPUT_DIR", "/tmp/output")

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "play.min.io:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "your_key")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "your_secret")
MINIO_INPUT_BUCKET = os.getenv("MINIO_INPUT_BUCKET", "comfyui-input")
MINIO_RESULT_BUCKET = os.getenv("MINIO_RESULT_BUCKET", "comfyui-output")
MINIO_TEMPLATE_BUCKET = os.getenv("MINIO_TEMPLATE_BUCKET", "bot-template")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
MINIO_CONNECT_TIMEOUT_SECONDS = float(os.getenv("MINIO_CONNECT_TIMEOUT_SECONDS", "10"))
MINIO_READ_TIMEOUT_SECONDS = float(os.getenv("MINIO_READ_TIMEOUT_SECONDS", "45"))
MINIO_HTTP_RETRY_TOTAL = int(os.getenv("MINIO_HTTP_RETRY_TOTAL", "2"))
MINIO_DOWNLOAD_TIMEOUT_SECONDS = float(
    os.getenv("MINIO_DOWNLOAD_TIMEOUT_SECONDS", "300")
)
MINIO_DOWNLOAD_RETRY_ATTEMPTS = int(os.getenv("MINIO_DOWNLOAD_RETRY_ATTEMPTS", "2"))
MINIO_DOWNLOAD_RETRY_DELAY_SECONDS = float(
    os.getenv("MINIO_DOWNLOAD_RETRY_DELAY_SECONDS", "2")
)
COMFY_READY_RETRY_ATTEMPTS = int(os.getenv("COMFY_READY_RETRY_ATTEMPTS", "5"))
COMFY_READY_RETRY_DELAY_SECONDS = float(
    os.getenv("COMFY_READY_RETRY_DELAY_SECONDS", "2")
)
COMFY_UPLOAD_RETRY_ATTEMPTS = int(os.getenv("COMFY_UPLOAD_RETRY_ATTEMPTS", "3"))
COMFY_HEALTH_FAILURE_THRESHOLD = int(os.getenv("COMFY_HEALTH_FAILURE_THRESHOLD", "3"))
COMFY_HEALTH_RECOVERY_THRESHOLD = int(os.getenv("COMFY_HEALTH_RECOVERY_THRESHOLD", "2"))
COMFY_ERROR_POLL_SECONDS = float(os.getenv("COMFY_ERROR_POLL_SECONDS", "15"))
COMFY_WS_LOST_PROBE_FAILURE_THRESHOLD = int(
    os.getenv("COMFY_WS_LOST_PROBE_FAILURE_THRESHOLD", "2")
)
COMFY_TASK_INFRA_FAILURE_THRESHOLD = int(
    os.getenv("COMFY_TASK_INFRA_FAILURE_THRESHOLD", "3")
)
COMFY_QUARANTINE_SECONDS = float(os.getenv("COMFY_QUARANTINE_SECONDS", "300"))
COMPLETE_REPORT_MAX_ATTEMPTS = int(os.getenv("COMPLETE_REPORT_MAX_ATTEMPTS", "5"))
COMPLETE_REPORT_RETRY_BASE_SECONDS = float(
    os.getenv("COMPLETE_REPORT_RETRY_BASE_SECONDS", "1.0")
)
COMPLETE_REPORT_RETRY_MAX_SECONDS = float(
    os.getenv("COMPLETE_REPORT_RETRY_MAX_SECONDS", "10.0")
)
STATUS_REPORT_MAX_ATTEMPTS = int(os.getenv("STATUS_REPORT_MAX_ATTEMPTS", "3"))
STATUS_REPORT_RETRY_BASE_SECONDS = float(
    os.getenv("STATUS_REPORT_RETRY_BASE_SECONDS", "0.5")
)
STATUS_REPORT_RETRY_MAX_SECONDS = float(
    os.getenv("STATUS_REPORT_RETRY_MAX_SECONDS", "3.0")
)
UPLOAD_SIDECAR_URL = os.getenv("UPLOAD_SIDECAR_URL", "").rstrip("/")
RESULT_SPOOL_DIR = os.getenv("RESULT_SPOOL_DIR", "/app/spool")
AGENT_LOG_DIR = os.getenv("AGENT_LOG_DIR", "./logs")
PREFETCH_ENABLED = os.getenv("PREFETCH_ENABLED", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
PREFETCH_DEPTH = int(os.getenv("PREFETCH_DEPTH", "1"))
PREFETCH_TASK_TYPES = os.getenv(
    "PREFETCH_TASK_TYPES",
    "img2img,img2img_lora,face_swap,i2i_draw,i2i_pro",
)
PREFETCH_CACHE_DIR = os.getenv("PREFETCH_CACHE_DIR", "/app/prefetch-cache")
PREFETCH_CONSUME_WAIT_SECONDS = float(
    os.getenv("PREFETCH_CONSUME_WAIT_SECONDS", "0.25")
)
PIPELINE_ENABLED = os.getenv("PIPELINE_ENABLED", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
PIPELINE_MAX_RUNNING_TASKS = max(
    1,
    int(os.getenv("PIPELINE_MAX_RUNNING_TASKS", "2")),
)
PIPELINE_TASK_TYPES = os.getenv("PIPELINE_TASK_TYPES", "all")
CANCEL_LOCK_ON_POP = os.getenv("CANCEL_LOCK_ON_POP", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
TASK_COMPLETION_TIMEOUT_SECONDS = float(
    os.getenv("TASK_COMPLETION_TIMEOUT_SECONDS", "1800")
)
WAN22_VIDEO_V2_COMPLETION_TIMEOUT_SECONDS = float(
    os.getenv("WAN22_VIDEO_V2_COMPLETION_TIMEOUT_SECONDS", "600")
)
RUNPOD_RUNTIME = (
    os.getenv("RUNPOD_MANAGED", "").strip().lower() in TRUE_ENV_VALUES
    or os.getenv("ALLBOT_RUNPOD_MANAGED", "").strip().lower() in TRUE_ENV_VALUES
    or bool(os.getenv("RUNPOD_POD_ID") or os.getenv("RUNPOD_TASK_TYPE"))
)
WAN22_VIDEO_V2_EXIT_ON_TIMEOUT = (
    os.getenv(
        "WAN22_VIDEO_V2_EXIT_ON_TIMEOUT",
        "true" if RUNPOD_RUNTIME else "false",
    )
    .strip()
    .lower()
    in TRUE_ENV_VALUES
)
WAN22_VIDEO_V2_TIMEOUT_EXIT_CODE = int(
    os.getenv("WAN22_VIDEO_V2_TIMEOUT_EXIT_CODE", "75")
)

USER_INPUT_ERROR_MARKERS = (
    "downloaded file is not a valid image",
    "prompt is required",
    "invalid input",
    "bad request",
    "validation",
)
INFRA_ERROR_MARKERS = (
    "comfyui",
    "websocket",
    "history probe",
    "queue prompt",
    "prompt_id",
    "connection",
    "timeout",
    "timed out",
    "service lost",
    "upload",
    "minio",
    "result processing",
    "no result path",
    "workflow",
    "model",
    "node",
    "out of memory",
    "oom",
    "cuda",
)

log_format = (
    "%(asctime)s - %(name)s - %(levelname)s - [%(correlation_id)s] - %(message)s"
)
formatter = logging.Formatter(log_format)

handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(formatter)
handler.addFilter(CorrelationIdFilter())

# Also log to file if the directory exists
handlers = [handler]
os.makedirs(AGENT_LOG_DIR, exist_ok=True)
file_handler = logging.FileHandler(
    os.path.join(AGENT_LOG_DIR, f"agent_{AGENT_ID}.log"),
    encoding="utf-8",
)
file_handler.setFormatter(formatter)
file_handler.addFilter(CorrelationIdFilter())
handlers.append(file_handler)

logging.basicConfig(level=logging.INFO, handlers=handlers)
logger = logging.getLogger("agent_main")


class ComfyAgent:
    def __init__(self):
        self.comfy_client = ComfyClient(base_url=COMFY_API_URL)
        self.patcher = WorkflowPatcher(
            workflows_dir=os.path.join(os.path.dirname(__file__), "workflows")
        )
        self.master_client = httpx.AsyncClient(
            base_url=MASTER_API_URL,
            headers={"Authorization": f"Bearer {AGENT_SECRET_TOKEN}"},
            timeout=30.0,
        )

        # Init MinIO
        try:
            self.minio_client = Minio(
                MINIO_ENDPOINT,
                access_key=MINIO_ACCESS_KEY,
                secret_key=MINIO_SECRET_KEY,
                secure=MINIO_SECURE,
                http_client=urllib3.PoolManager(
                    timeout=urllib3.Timeout(
                        connect=MINIO_CONNECT_TIMEOUT_SECONDS,
                        read=MINIO_READ_TIMEOUT_SECONDS,
                    ),
                    retries=urllib3.Retry(
                        total=MINIO_HTTP_RETRY_TOTAL,
                        backoff_factor=0.5,
                        status_forcelist=[500, 502, 503, 504],
                    ),
                ),
            )
            logger.info("MinIO client initialized")
        except Exception as e:
            logger.error(f"Failed to init MinIO: {e}")
            self.minio_client = None

        self.tasks = []
        self._idle_completed_event = asyncio.Event()
        self._active_execution: Optional[TaskExecutionContext] = None
        self._executions: dict[str, TaskExecutionContext] = {}
        self._prompt_executions: dict[str, TaskExecutionContext] = {}
        self._execution_tasks: set[asyncio.Task] = set()
        self.running = False
        self._comfy_poll_paused = False
        self.consecutive_failures = 0
        self.consecutive_successes = 0
        self.is_error_state = False
        self.health_reason = ""
        self.last_error = ""
        self.last_error_at: float | None = None
        self.task_infra_failures = 0
        self.quarantined_until: float | None = None
        self._prefetch_cache: dict[str, dict[str, Any]] = {}
        self._prefetch_task: asyncio.Task | None = None
        self._prefetch_task_types = {
            task_type.strip()
            for task_type in PREFETCH_TASK_TYPES.split(",")
            if task_type.strip()
        }
        self._pipeline_task_types = {
            task_type.strip()
            for task_type in PIPELINE_TASK_TYPES.split(",")
            if task_type.strip()
        }

    @property
    def task_completed_event(self) -> asyncio.Event:
        if self._active_execution:
            return self._active_execution.completed_event
        return self._idle_completed_event

    def _start_task_execution(
        self, *, task_id: str, task_type: str
    ) -> TaskExecutionContext:
        execution = TaskExecutionContext(task_id=task_id, task_type=task_type)
        self._active_execution = execution
        self._executions[task_id] = execution
        return execution

    def _register_prompt_execution(self, execution: TaskExecutionContext) -> None:
        if execution.prompt_id:
            self._prompt_executions[execution.prompt_id] = execution

    def _clear_task_execution(
        self, execution: TaskExecutionContext | None = None
    ) -> None:
        if execution is not None:
            self._executions.pop(execution.task_id, None)
            if execution.prompt_id:
                self._prompt_executions.pop(execution.prompt_id, None)
            if self._active_execution is execution:
                self._active_execution = next(
                    iter(self._executions.values()),
                    None,
                )
            self._idle_completed_event.clear()
            return
        self._executions.clear()
        self._prompt_executions.clear()
        self._active_execution = None
        self._idle_completed_event.clear()

    async def _probe_comfy_ready(self) -> bool:
        try:
            response = await self.comfy_client.client.get("/system_stats")
            return response.status_code == 200
        except Exception:
            return False

    def _now(self) -> float:
        return time.time()

    def _record_health_failure(self, *, reason: str, error: str) -> None:
        self.consecutive_failures += 1
        self.consecutive_successes = 0
        self.health_reason = reason
        self.last_error = error
        self.last_error_at = self._now()
        if self.consecutive_failures >= COMFY_HEALTH_FAILURE_THRESHOLD:
            if not self.is_error_state:
                logger.error(
                    "Agent %s reached ComfyUI health failure threshold; marking worker as error",
                    AGENT_ID,
                )
            self.is_error_state = True

    def _record_health_success(self) -> None:
        self.consecutive_successes += 1
        if (
            self.is_error_state
            and self.consecutive_successes < COMFY_HEALTH_RECOVERY_THRESHOLD
        ):
            return
        self.consecutive_failures = 0
        self.consecutive_successes = 0
        if self.is_error_state:
            logger.info("ComfyUI health recovered; clearing worker error state")
        self.is_error_state = False
        self.health_reason = ""
        self.last_error = ""
        self.last_error_at = None

    def _is_quarantined(self) -> bool:
        return (
            self.quarantined_until is not None and self.quarantined_until > self._now()
        )

    def _clear_expired_quarantine(self) -> bool:
        if self.quarantined_until is None:
            return False
        if self.quarantined_until > self._now():
            return False
        logger.info("Worker quarantine expired; health checks may resume task polling")
        self.quarantined_until = None
        self.task_infra_failures = 0
        if self.health_reason == "task_infra_failures":
            self.health_reason = ""
            self.last_error = ""
            self.last_error_at = None
        return True

    def _enter_quarantine(self, *, error: str) -> None:
        self.quarantined_until = self._now() + COMFY_QUARANTINE_SECONDS
        self.health_reason = "task_infra_failures"
        self.last_error = error
        self.last_error_at = self._now()
        logger.error(
            "Agent %s entered quarantine for %.0fs after %s consecutive infrastructure failures",
            AGENT_ID,
            COMFY_QUARANTINE_SECONDS,
            self.task_infra_failures,
        )

    @staticmethod
    def _is_infrastructure_failure(error: Exception) -> bool:
        message = str(error).lower()
        if any(marker in message for marker in USER_INPUT_ERROR_MARKERS):
            return False
        return any(marker in message for marker in INFRA_ERROR_MARKERS)

    def _record_task_failure_for_health(self, error: Exception) -> None:
        if not self._is_infrastructure_failure(error):
            self.task_infra_failures = 0
            return
        self.task_infra_failures += 1
        if self.task_infra_failures >= COMFY_TASK_INFRA_FAILURE_THRESHOLD:
            self._enter_quarantine(error=str(error))

    def _record_task_success_for_health(self) -> None:
        self.task_infra_failures = 0

    @staticmethod
    def _completion_timeout_seconds_for_task(task_type: str) -> float:
        if task_type == "wan22_video_v2":
            return WAN22_VIDEO_V2_COMPLETION_TIMEOUT_SECONDS
        return TASK_COMPLETION_TIMEOUT_SECONDS

    @staticmethod
    def _should_self_restart_after_timeout(
        execution: TaskExecutionContext,
        error: Exception,
    ) -> bool:
        return (
            execution.task_type == "wan22_video_v2"
            and isinstance(error, TaskExecutionTimeoutError)
            and WAN22_VIDEO_V2_EXIT_ON_TIMEOUT
        )

    async def _interrupt_comfy_for_wan22_timeout(
        self,
        execution: TaskExecutionContext,
    ) -> None:
        if execution.task_type != "wan22_video_v2":
            return
        logger.warning(
            "Interrupting ComfyUI after wan22_video_v2 timeout: task=%s prompt=%s",
            execution.task_id,
            execution.prompt_id,
        )
        interrupted = await self.comfy_client.interrupt()
        if interrupted:
            logger.info(
                "ComfyUI interrupt accepted for wan22_video_v2 task %s",
                execution.task_id,
            )

    def _worker_status(self) -> str:
        if self._is_quarantined():
            return "quarantined"
        if self.is_error_state:
            return "error"
        return "running" if self._executions or self._active_execution else "idle"

    def _heartbeat_executions(self) -> list[TaskExecutionContext]:
        executions = list(self._executions.values())
        if not executions and self._active_execution:
            executions.append(self._active_execution)
        return executions

    def _heartbeat_health_payload(self) -> dict[str, Any]:
        failure_count = (
            self.task_infra_failures
            if self._is_quarantined()
            else self.consecutive_failures
        )
        return {
            "health_reason": self.health_reason,
            "last_error": self.last_error,
            "last_error_at": self.last_error_at,
            "consecutive_failures": failure_count,
            "quarantined_until": self.quarantined_until,
        }

    @staticmethod
    def _heartbeat_pool_payload() -> dict[str, Any]:
        payload = {
            "node_id": POOL_NODE_ID,
            "provider": POOL_PROVIDER,
            "gpu_index": POOL_GPU_INDEX,
            "runtime_profile": POOL_RUNTIME_PROFILE,
            "image_ref": POOL_IMAGE_REF,
            "model_bundle_versions": POOL_MODEL_BUNDLE_VERSIONS,
            "pool_managed": POOL_MANAGED,
        }
        return {key: value for key, value in payload.items() if value not in (None, "")}

    async def _handle_ws_connection_error(self, error: Exception | str) -> None:
        executions = [
            execution
            for execution in self._prompt_executions.values()
            if not execution.completed_event.is_set()
        ]
        if not executions and self._active_execution:
            executions = [self._active_execution]
        if not executions:
            return

        probe_failures = 0
        for _ in range(COMFY_WS_LOST_PROBE_FAILURE_THRESHOLD):
            if await self._probe_comfy_ready():
                logger.warning(
                    "HTTP probe succeeded after WebSocket error; keeping execution wait alive"
                )
                return
            probe_failures += 1
            await asyncio.sleep(COMFY_READY_RETRY_DELAY_SECONDS)

        if probe_failures >= COMFY_WS_LOST_PROBE_FAILURE_THRESHOLD:
            task_error = f"ComfyUI service lost during execution: {error}"
            for execution in executions:
                execution.task_error = task_error
                execution.completed_event.set()
            self._record_health_failure(
                reason="comfy_ws_lost",
                error=task_error,
            )

    async def _wait_for_comfy_ready(self, *, operation: str) -> None:
        for attempt in range(1, COMFY_READY_RETRY_ATTEMPTS + 1):
            if await self._probe_comfy_ready():
                return
            if attempt < COMFY_READY_RETRY_ATTEMPTS:
                logger.warning(
                    "ComfyUI unavailable before %s (attempt %s/%s), retrying in %.1fs",
                    operation,
                    attempt,
                    COMFY_READY_RETRY_ATTEMPTS,
                    COMFY_READY_RETRY_DELAY_SECONDS,
                )
                await asyncio.sleep(COMFY_READY_RETRY_DELAY_SECONDS)
                continue
            raise RuntimeError(f"ComfyUI unavailable before {operation}")

    @staticmethod
    def _should_normalize_image_input(param_key: str, object_name: str) -> bool:
        if param_key == "video":
            return False
        lowered = object_name.lower()
        return lowered.endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp"))

    @staticmethod
    def _normalize_input_image_for_comfy(local_path: str) -> str:
        normalized_path = f"{os.path.splitext(local_path)[0]}_normalized.png"
        try:
            with Image.open(local_path) as image:
                image.load()
                normalized = ImageOps.exif_transpose(image)
                if normalized.mode not in ("RGB", "RGBA"):
                    normalized = normalized.convert(
                        "RGBA" if "A" in normalized.getbands() else "RGB"
                    )
                normalized.save(normalized_path, format="PNG")
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise RuntimeError(
                f"Downloaded file is not a valid image: {local_path}"
            ) from exc
        return normalized_path

    async def _upload_prepared_input(
        self,
        *,
        upload_path: str,
        upload_name: str,
        source_name: str,
    ) -> None:
        last_error: Exception | None = None
        for attempt in range(1, COMFY_UPLOAD_RETRY_ATTEMPTS + 1):
            await self._wait_for_comfy_ready(operation=f"uploading {upload_name}")
            try:
                with open(upload_path, "rb") as file_obj:
                    file_content = file_obj.read()
                await self.comfy_client.upload_image(file_content, upload_name)
                logger.info(f"Uploaded {upload_name} to ComfyUI via API")
                return
            except Exception as upload_err:
                last_error = upload_err
                if attempt >= COMFY_UPLOAD_RETRY_ATTEMPTS:
                    logger.error(
                        f"Failed to upload {upload_name} to ComfyUI via API: {upload_err}"
                    )
                    break
                logger.warning(
                    "Upload attempt %s/%s failed for %s (%s), retrying in %.1fs",
                    attempt,
                    COMFY_UPLOAD_RETRY_ATTEMPTS,
                    upload_name,
                    upload_err,
                    COMFY_READY_RETRY_DELAY_SECONDS,
                )
                await asyncio.sleep(COMFY_READY_RETRY_DELAY_SECONDS)
        raise RuntimeError(
            f"Failed to upload prepared input '{source_name}' to ComfyUI"
        ) from last_error

    async def _process_single_input_asset(
        self,
        *,
        params: dict[str, Any],
        downloaded_input_paths: list[str],
        img_filename: str,
        param_key: str,
        comfy_input_dir: str = COMFY_INPUT_DIR,
    ) -> None:
        await process_agent_single_input_asset(
            params=params,
            downloaded_input_paths=downloaded_input_paths,
            img_filename=img_filename,
            param_key=param_key,
            comfy_input_dir=comfy_input_dir,
            download_input_func=self.download_input_from_minio,
            should_normalize_image_input_func=self._should_normalize_image_input,
            normalize_input_image_func=self._normalize_input_image_for_comfy,
            upload_prepared_input_func=self._upload_prepared_input,
            logger=logger,
            download_timeout_seconds=MINIO_DOWNLOAD_TIMEOUT_SECONDS,
            download_retry_attempts=MINIO_DOWNLOAD_RETRY_ATTEMPTS,
            download_retry_delay_seconds=MINIO_DOWNLOAD_RETRY_DELAY_SECONDS,
        )

    async def _prepare_task_inputs(
        self,
        *,
        params: dict[str, Any],
        downloaded_input_paths: list[str],
        comfy_input_dir: str = COMFY_INPUT_DIR,
    ) -> None:
        async def process_with_input_dir(**kwargs):
            await self._process_single_input_asset(
                **kwargs,
                comfy_input_dir=comfy_input_dir,
            )

        await prepare_agent_task_inputs(
            params=params,
            downloaded_input_paths=downloaded_input_paths,
            process_single_input_asset_func=process_with_input_dir,
        )

    @staticmethod
    def _parse_task_params(task: dict[str, Any]) -> dict[str, Any]:
        params_str = task.get("params", "{}")
        if isinstance(params_str, str):
            parsed = json.loads(params_str)
        else:
            parsed = params_str
        return dict(parsed or {})

    def _should_prefetch_task_type(self, task_type: str) -> bool:
        if not PREFETCH_ENABLED or PREFETCH_DEPTH <= 0:
            return False
        return task_type in self._prefetch_task_types

    def _cleanup_input_paths(self, paths: list[str]) -> None:
        for path in paths:
            try:
                if os.path.exists(path):
                    os.remove(path)
                    logger.info(f"Cleaned up input file: {path}")
            except Exception as e:
                logger.warning(f"Failed to clean up input file {path}: {e}")

    def _discard_prefetch_cache(self, *, except_task_id: str | None = None) -> None:
        task_ids = list(self._prefetch_cache.keys())
        for cached_task_id in task_ids:
            if except_task_id and cached_task_id == except_task_id:
                continue
            cached = self._prefetch_cache.pop(cached_task_id, None)
            if cached:
                self._cleanup_input_paths(cached.get("downloaded_input_paths", []))

    async def _wait_for_prefetch_settle(self) -> None:
        if not self._prefetch_task or self._prefetch_task.done():
            return
        try:
            await asyncio.wait_for(
                asyncio.shield(self._prefetch_task),
                timeout=max(0.0, PREFETCH_CONSUME_WAIT_SECONDS),
            )
        except asyncio.TimeoutError:
            return
        except Exception as exc:
            logger.debug("Prefetch settle failed: %s", exc)

    async def _cancel_prefetch_task(self) -> None:
        if not self._prefetch_task or self._prefetch_task.done():
            return
        self._prefetch_task.cancel()
        try:
            await self._prefetch_task
        except asyncio.CancelledError:
            pass

    def _consume_prefetched_inputs(
        self,
        *,
        task_id: str,
        task_type: str,
    ) -> dict[str, Any] | None:
        cached = self._prefetch_cache.pop(task_id, None)
        self._discard_prefetch_cache()
        if not cached:
            return None
        if cached.get("task_type") != task_type:
            self._cleanup_input_paths(cached.get("downloaded_input_paths", []))
            return None
        logger.info("Using prefetched inputs for task %s", task_id)
        return cached

    async def _prefetch_next_task_inputs(
        self,
        *,
        task_type_filter: str | None = None,
    ) -> None:
        if not PREFETCH_ENABLED or PREFETCH_DEPTH <= 0:
            return
        if self._prefetch_cache:
            return

        params = {"limit": PREFETCH_DEPTH}
        if task_type_filter and task_type_filter in self._prefetch_task_types:
            prefetch_types = task_type_filter
        else:
            prefetch_types = ",".join(sorted(self._prefetch_task_types))
        if prefetch_types:
            params["types"] = prefetch_types

        try:
            response = await self.master_client.get(
                "/api/agent/task/peek", params=params
            )
            if response.status_code != 200:
                logger.debug("Prefetch peek returned HTTP %s", response.status_code)
                return
            task = response.json().get("task")
            if not task:
                return

            task_id = str(task.get("task_id", ""))
            task_type = str(task.get("type", ""))
            if not task_id or not self._should_prefetch_task_type(task_type):
                return

            prefetch_params = self._parse_task_params(task)
            downloaded_input_paths: list[str] = []
            await self._prepare_task_inputs(
                params=prefetch_params,
                downloaded_input_paths=downloaded_input_paths,
                comfy_input_dir=PREFETCH_CACHE_DIR,
            )
            self._discard_prefetch_cache()
            self._prefetch_cache[task_id] = {
                "task_id": task_id,
                "task_type": task_type,
                "params": prefetch_params,
                "downloaded_input_paths": downloaded_input_paths,
            }
            logger.info(
                "Prefetched inputs for pending task %s (%s)", task_id, task_type
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Prefetch failed: %s", exc)

    def _schedule_prefetch(self, *, current_task_type: str) -> None:
        if not PREFETCH_ENABLED:
            return
        if not self._should_prefetch_task_type(current_task_type):
            return
        if self._prefetch_task and not self._prefetch_task.done():
            return
        self._prefetch_task = asyncio.create_task(
            self._prefetch_next_task_inputs(task_type_filter=current_task_type)
        )

    async def report_heartbeat(self):
        try:
            status = self._worker_status()
            await self.master_client.post(
                "/api/agent/task/heartbeat",
                json={
                    "agent_id": AGENT_ID,
                    "types": SUPPORTED_TASK_TYPES,
                    "status": status,
                    **self._heartbeat_health_payload(),
                    **self._heartbeat_pool_payload(),
                },
            )
            for execution in self._heartbeat_executions():
                await self.master_client.post(
                    "/api/agent/task/task_heartbeat",
                    json={"task_id": execution.task_id, "agent_id": AGENT_ID},
                )
        except Exception as e:
            logger.debug(f"Failed to report heartbeat: {e}")

    async def heartbeat_loop(self):
        logger.info(f"Agent {AGENT_ID} started heartbeat loop...")
        while getattr(self, "running", True):
            await self.report_heartbeat()
            await asyncio.sleep(15)  # Send heartbeat every 15 seconds

    async def report_status(
        self,
        task_id: str,
        status: str,
        progress: float = 0.0,
        error: str = "",
        *,
        execution_phase: str | None = None,
        cancel_locked: bool | None = None,
        set_current: bool = True,
    ):
        payload = {
            "task_id": task_id,
            "agent_id": AGENT_ID,
            "status": status,
            "progress": progress,
            "error": error,
        }
        if execution_phase is not None:
            payload["execution_phase"] = execution_phase
        if cancel_locked is not None:
            payload["cancel_locked"] = cancel_locked
        if not set_current:
            payload["set_current"] = False
        attempts = max(1, STATUS_REPORT_MAX_ATTEMPTS)

        for attempt in range(1, attempts + 1):
            try:
                response = await self.master_client.post(
                    "/api/agent/task/status",
                    json=payload,
                )
                status_code = getattr(response, "status_code", 200)
                if status_code >= 400:
                    raise RuntimeError(
                        f"Central API returned HTTP {status_code} for status report"
                    )
                return
            except Exception as e:
                if attempt >= attempts:
                    logger.error(
                        "Failed to report status for task %s after %s attempts: %s",
                        task_id,
                        attempts,
                        e,
                    )
                    return
                delay = min(
                    STATUS_REPORT_RETRY_BASE_SECONDS * (2 ** (attempt - 1)),
                    STATUS_REPORT_RETRY_MAX_SECONDS,
                )
                logger.debug(
                    "Failed to report status for task %s on attempt %s/%s; retrying in %.1fs: %s",
                    task_id,
                    attempt,
                    attempts,
                    delay,
                    e,
                )
                await asyncio.sleep(delay)

    async def report_complete(
        self,
        task_id: str,
        result_path: str,
        *,
        extra_outputs: dict[str, Any] | None = None,
    ):
        payload = {
            "task_id": task_id,
            "agent_id": AGENT_ID,
            "result": result_path,
            "extra_outputs": extra_outputs or {},
        }
        attempts = max(1, COMPLETE_REPORT_MAX_ATTEMPTS)
        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                response = await self.master_client.post(
                    "/api/agent/task/complete",
                    json=payload,
                )
                status_code = getattr(response, "status_code", 200)
                if status_code >= 400:
                    raise RuntimeError(
                        f"Central API returned HTTP {status_code} for completion"
                    )
                return
            except Exception as e:
                last_error = e
                if attempt >= attempts:
                    logger.error(
                        "Failed to report completion for task %s after %s attempts: %s",
                        task_id,
                        attempts,
                        e,
                    )
                    raise RuntimeError(
                        f"Failed to report completion for task {task_id}"
                    ) from e

                delay = min(
                    COMPLETE_REPORT_RETRY_BASE_SECONDS * (2 ** (attempt - 1)),
                    COMPLETE_REPORT_RETRY_MAX_SECONDS,
                )
                logger.warning(
                    "Failed to report completion for task %s (attempt %s/%s): %s; retrying in %.1fs",
                    task_id,
                    attempt,
                    attempts,
                    e,
                    delay,
                )
                await asyncio.sleep(delay)

        raise RuntimeError(
            f"Failed to report completion for task {task_id}"
        ) from last_error

    async def report_cancelled(self, task_id: str):
        await self.report_status(task_id, "cancelled")

    async def _receive_ws_message(self, websocket):
        try:
            return await asyncio.wait_for(websocket.recv(), timeout=60.0)
        except asyncio.TimeoutError:
            if websocket.state == websockets.protocol.State.CLOSED:
                raise ConnectionError("WebSocket closed unexpectedly")
            try:
                await websocket.ping()
            except Exception as exc:
                raise ConnectionError(f"WebSocket ping failed: {exc}") from exc
            return None

    @staticmethod
    def _decode_ws_message(message) -> dict[str, Any] | None:
        if message is None or isinstance(message, bytes):
            return None
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None

    async def _route_ws_event(self, data: dict[str, Any]) -> None:
        msg_type = data.get("type")
        data_content = extract_ws_data_content(data)
        prompt_id = data_content.get("prompt_id")
        execution = self._prompt_executions.get(prompt_id or "")

        if not execution or not prompt_id:
            return

        if msg_type == "execution_start":
            logger.info(f"Execution started for prompt {prompt_id}")
            execution.phase = "running"
            if execution.task_id:
                await self.report_status(
                    execution.task_id,
                    "running",
                    execution_phase="running",
                )
            return

        if msg_type == "progress":
            value = data_content.get("value", 0)
            max_val = data_content.get("max", 1)
            if max_val > 0 and execution.task_id:
                await self.report_status(
                    execution.task_id,
                    "running",
                    progress=value / max_val,
                    execution_phase="running",
                )
            return

        if msg_type == "executing":
            node = data_content.get("node")
            if node is None:
                logger.info(f"Execution fully completed for prompt {prompt_id}")
                execution.phase = "gpu_done"
                execution.completed_event.set()
            return

        if msg_type == "execution_success":
            logger.info(f"Execution success received for prompt {prompt_id}")
            execution.phase = "gpu_done"
            execution.completed_event.set()
            return

        if msg_type == "executed":
            logger.info(f"Node executed for prompt {prompt_id}")
            output = data_content.get("output") or {}
            asset = pick_first_output_asset(output, task_type=execution.task_type)
            if asset and execution.task_id:
                asset_priority = result_asset_priority(
                    asset,
                    task_type=execution.task_type,
                )
                if asset_priority >= execution.task_result_priority:
                    execution.task_result = build_safe_result_object_name(
                        execution.task_id,
                        asset,
                    )
                    execution.task_result_priority = asset_priority
            return

        if msg_type == "execution_error":
            error_msg = str(data_content.get("exception_message", "Unknown error"))
            logger.error(f"Execution error for prompt {prompt_id}: {error_msg}")
            execution.task_error = error_msg
            execution.completed_event.set()

    async def ws_listener_loop(self):
        client_id = f"agent_{AGENT_ID}"
        uri = f"{COMFY_WS_URL}?clientId={client_id}"

        while getattr(self, "running", True):
            try:
                async with websockets.connect(
                    uri, max_size=None, ping_interval=20, ping_timeout=20
                ) as websocket:
                    logger.info(f"Connected to ComfyUI WebSocket at {uri}")
                    while True:
                        try:
                            message = await self._receive_ws_message(websocket)
                        except ConnectionError as exc:
                            logger.error(str(exc))
                            await self._handle_ws_connection_error(exc)
                            break

                        data = self._decode_ws_message(message)
                        if data is None:
                            continue
                        try:
                            await self._route_ws_event(data)
                        except Exception as message_error:
                            logger.warning(
                                "Failed to parse WS message type=%s: %s",
                                data.get("type"),
                                message_error,
                            )
                            continue

            except Exception as e:
                logger.error(f"WebSocket connection error: {e}")
                await self._handle_ws_connection_error(e)
                await asyncio.sleep(5)

    def download_input_from_minio(self, object_name: str, local_path: str):
        if not self.minio_client:
            raise Exception("MinIO client not initialized")

        bucket_name = MINIO_INPUT_BUCKET
        real_object_name = object_name

        if object_name.startswith("template:"):
            bucket_name = MINIO_TEMPLATE_BUCKET
            real_object_name = object_name.replace("template:", "")
        elif object_name.startswith("comfyui-temp/"):
            bucket_name = MINIO_RESULT_BUCKET
            real_object_name = object_name.replace("comfyui-temp/", "", 1)
        elif object_name.startswith(f"{MINIO_RESULT_BUCKET}/"):
            bucket_name = MINIO_RESULT_BUCKET
            real_object_name = object_name.replace(f"{MINIO_RESULT_BUCKET}/", "", 1)
        elif object_name.startswith(f"{MINIO_INPUT_BUCKET}/"):
            bucket_name = MINIO_INPUT_BUCKET
            real_object_name = object_name.replace(f"{MINIO_INPUT_BUCKET}/", "", 1)

        logger.info(
            f"Downloading {real_object_name} from MinIO bucket {bucket_name} to {local_path}"
        )
        self.minio_client.fget_object(bucket_name, real_object_name, local_path)

    def upload_result_to_minio(self, local_path: str, object_name: str):
        if not self.minio_client:
            raise Exception("MinIO client not initialized")

        content_type = "image/png"
        if object_name.endswith(".mp4"):
            content_type = "video/mp4"
        elif object_name.endswith(".gif"):
            content_type = "image/gif"
        elif object_name.endswith(".jpg") or object_name.endswith(".jpeg"):
            content_type = "image/jpeg"

        logger.info(
            f"Uploading {local_path} to MinIO bucket {MINIO_RESULT_BUCKET} as {object_name}"
        )
        self.minio_client.fput_object(
            MINIO_RESULT_BUCKET, object_name, local_path, content_type=content_type
        )

    async def check_task_cancelled(self, task_id: str) -> bool:
        try:
            response = await self.master_client.get(f"/api/agent/task/check/{task_id}")
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "cancelled" or data.get("cancel_requested"):
                    return True
        except Exception as e:
            logger.debug(f"Failed to check task status: {e}")
        return False

    def _pipeline_enabled_for_task_type(self, task_type: str) -> bool:
        if not PIPELINE_ENABLED or PIPELINE_MAX_RUNNING_TASKS <= 1:
            return False
        if "all" in self._pipeline_task_types:
            return True
        return task_type in self._pipeline_task_types

    def _pipeline_pop_types(self) -> str:
        supported_types = {
            task_type.strip()
            for task_type in SUPPORTED_TASK_TYPES.split(",")
            if task_type.strip()
        }
        if not self._pipeline_task_types or "all" in self._pipeline_task_types:
            return SUPPORTED_TASK_TYPES
        if not supported_types:
            return ",".join(sorted(self._pipeline_task_types))
        return ",".join(sorted(supported_types & self._pipeline_task_types))

    def _build_pop_params(self, *, pipeline: bool = False) -> dict[str, str]:
        params: dict[str, str] = {"agent_id": AGENT_ID}
        types = self._pipeline_pop_types() if pipeline else SUPPORTED_TASK_TYPES
        if types:
            params["types"] = types
        if CANCEL_LOCK_ON_POP:
            params["cancel_lock"] = "true"
        return params

    async def _pop_next_task(self, *, pipeline: bool = False) -> dict[str, Any] | None:
        response = await self.master_client.get(
            "/api/agent/task/pop",
            params=self._build_pop_params(pipeline=pipeline),
        )
        if response.status_code == 200:
            data = response.json()
            return data.get("task")
        if response.status_code != 404:
            logger.warning(f"Unexpected response from master: {response.status_code}")
        return None

    async def _prepare_and_submit_task(
        self,
        task: Dict[str, Any],
        *,
        allow_cancel_check: bool = True,
    ) -> TaskExecutionContext | None:
        trace_id = task.get("trace_id", "")
        if trace_id:
            correlation_id.set(trace_id)

        task_id = str(task.get("task_id", ""))
        if not task_id:
            logger.error("Received task without task_id")
            return

        task_type = str(task.get("type", ""))
        params = self._parse_task_params(task)

        logger.info(f"Processing task {task_id} of type {task_type}")
        execution = self._start_task_execution(task_id=task_id, task_type=task_type)
        downloaded_input_paths = execution.downloaded_input_paths

        if allow_cancel_check and await self.check_task_cancelled(task_id):
            logger.info(f"Task {task_id} was cancelled before processing.")
            self._discard_prefetch_cache(except_task_id=None)
            await self.report_cancelled(task_id)
            self._clear_task_execution(execution)
            return None

        await self.report_status(
            task_id,
            "running",
            execution_phase="preparing",
            cancel_locked=CANCEL_LOCK_ON_POP,
        )

        await self._wait_for_prefetch_settle()
        prefetched_inputs = self._consume_prefetched_inputs(
            task_id=task_id,
            task_type=task_type,
        )
        if prefetched_inputs:
            params = dict(prefetched_inputs["params"])
            downloaded_input_paths.extend(
                prefetched_inputs.get("downloaded_input_paths", [])
            )
        else:
            await self._cancel_prefetch_task()
            await self._prepare_task_inputs(
                params=params,
                downloaded_input_paths=downloaded_input_paths,
            )

        await submit_task_workflow(
            task_id=task_id,
            task_type=task_type,
            params=params,
            execution=execution,
            patcher=self.patcher,
            comfy_client=self.comfy_client,
            wait_for_comfy_ready_func=self._wait_for_comfy_ready,
            report_status_func=self.report_status,
            agent_id=AGENT_ID,
            logger=logger,
        )
        self._register_prompt_execution(execution)
        execution.phase = "queued"
        await self.report_status(task_id, "running", execution_phase="queued")
        self._schedule_prefetch(current_task_type=task_type)
        return execution

    async def _finalize_execution(self, execution: TaskExecutionContext) -> None:
        task_id = execution.task_id
        task_type = execution.task_type
        exit_after_timeout = False
        try:
            task_completed = await wait_for_task_completion(
                task_id=task_id,
                execution=execution,
                check_task_cancelled_func=self.check_task_cancelled,
                logger=logger,
                comfy_client=self.comfy_client,
                task_type=task_type,
                timeout_seconds=self._completion_timeout_seconds_for_task(task_type),
            )
            if not task_completed:
                await self.report_cancelled(task_id)
                return

            execution.phase = "finalizing"
            await self.report_status(
                task_id,
                "running",
                execution_phase="finalizing",
                set_current=False,
            )

            await resolve_execution_result_from_history(
                comfy_client=self.comfy_client,
                execution=execution,
                task_type=task_type,
                logger=logger,
            )

            if not execution.task_result:
                raise Exception("Task completed but no result path found")

            if not CANCEL_LOCK_ON_POP and await self.check_task_cancelled(task_id):
                logger.info(
                    f"Task {task_id} was cancelled during execution, skipping upload."
                )
                await self.report_cancelled(task_id)
                return

            try:
                materialized_outputs = await materialize_task_outputs(
                    comfy_client=self.comfy_client,
                    execution=execution,
                    task_type=task_type,
                    logger=logger,
                )
                if UPLOAD_SIDECAR_URL:
                    spooled_outputs = await spool_materialized_outputs(
                        outputs=materialized_outputs,
                        spool_dir=RESULT_SPOOL_DIR,
                        task_id=task_id,
                        logger=logger,
                    )
                    extra_outputs_payload = await upload_spooled_outputs_via_sidecar(
                        sidecar_url=UPLOAD_SIDECAR_URL,
                        result_bucket=MINIO_RESULT_BUCKET,
                        task_id=task_id,
                        spooled_outputs=spooled_outputs,
                        logger=logger,
                    )
                else:
                    extra_outputs_payload = await upload_materialized_outputs(
                        minio_client=self.minio_client,
                        result_bucket=MINIO_RESULT_BUCKET,
                        outputs=materialized_outputs,
                        logger=logger,
                    )
            except Exception as e:
                logger.error(f"Failed to fetch from ComfyUI or upload result: {e}")
                raise Exception(f"Result processing failed: {e}")

            await report_materialized_outputs(
                report_complete_func=self.report_complete,
                task_id=task_id,
                result_path=execution.task_result,
                extra_outputs_payload=extra_outputs_payload,
            )
            self._record_task_success_for_health()
            logger.info(f"Task {task_id} completed successfully")

        except Exception as e:
            logger.error(f"Task {task_id} failed: {e}")
            if (
                isinstance(e, TaskExecutionTimeoutError)
                and task_type == "wan22_video_v2"
            ):
                await self._interrupt_comfy_for_wan22_timeout(execution)
                exit_after_timeout = self._should_self_restart_after_timeout(
                    execution,
                    e,
                )
            self._record_task_failure_for_health(e)
            await self.report_status(task_id, "failed", error=str(e))
        finally:
            self._clear_task_execution(execution)
            self._cleanup_input_paths(execution.downloaded_input_paths)
        if exit_after_timeout:
            logger.error(
                "Exiting agent after wan22_video_v2 timeout so the supervisor can restart a clean ComfyUI runtime"
            )
            os._exit(WAN22_VIDEO_V2_TIMEOUT_EXIT_CODE)

    def _track_execution_task(self, task: asyncio.Task) -> None:
        self._execution_tasks.add(task)
        task.add_done_callback(self._execution_tasks.discard)

    async def _launch_pipeline_task(self, task: Dict[str, Any]) -> None:
        task_id = str(task.get("task_id", ""))
        try:
            execution = await self._prepare_and_submit_task(
                task,
                allow_cancel_check=not CANCEL_LOCK_ON_POP,
            )
            if not execution:
                return
            finalizer_task = asyncio.create_task(self._finalize_execution(execution))
            self._track_execution_task(finalizer_task)
        except Exception as e:
            logger.error(f"Task {task_id} failed before pipeline submission: {e}")
            self._record_task_failure_for_health(e)
            if task_id:
                await self.report_status(task_id, "failed", error=str(e))
            execution = self._executions.get(task_id)
            if execution:
                self._clear_task_execution(execution)
                self._cleanup_input_paths(execution.downloaded_input_paths)

    async def process_task(self, task: Dict[str, Any]):
        task_id = str(task.get("task_id", ""))
        execution: TaskExecutionContext | None = None
        try:
            execution = await self._prepare_and_submit_task(task)
            if not execution:
                return
            await self._finalize_execution(execution)
        except Exception as e:
            logger.error(f"Task {task_id} failed: {e}")
            self._record_task_failure_for_health(e)
            if task_id:
                await self.report_status(task_id, "failed", error=str(e))
            if execution is None and task_id:
                execution = self._executions.get(task_id)
            if execution:
                self._clear_task_execution(execution)
                self._cleanup_input_paths(execution.downloaded_input_paths)

    async def poll_loop(self):
        logger.info(
            f"Agent {AGENT_ID} started polling {MASTER_API_URL} for tasks (types: {SUPPORTED_TASK_TYPES or 'all'})..."
        )
        while getattr(self, "running", True):
            try:
                if self._is_quarantined():
                    self._comfy_poll_paused = True
                    await asyncio.sleep(COMFY_ERROR_POLL_SECONDS)
                    continue

                self._clear_expired_quarantine()

                if not await self._probe_comfy_ready():
                    self._comfy_poll_paused = True
                    self._record_health_failure(
                        reason="comfy_probe_failed",
                        error="ComfyUI /system_stats probe failed",
                    )
                    logger.warning(
                        "ComfyUI pre-flight check failed (%s/%s).",
                        self.consecutive_failures,
                        COMFY_HEALTH_FAILURE_THRESHOLD,
                    )
                    sleep_seconds = (
                        COMFY_ERROR_POLL_SECONDS
                        if self.is_error_state
                        else COMFY_READY_RETRY_DELAY_SECONDS
                    )
                    await asyncio.sleep(sleep_seconds)
                    continue

                self._record_health_success()
                if self.is_error_state:
                    await asyncio.sleep(COMFY_ERROR_POLL_SECONDS)
                    continue

                if self._comfy_poll_paused:
                    logger.info("ComfyUI is reachable again; resuming task polling")
                    self._comfy_poll_paused = False

                if PIPELINE_ENABLED:
                    if len(self._executions) >= PIPELINE_MAX_RUNNING_TASKS:
                        await asyncio.sleep(0.5)
                        continue
                    task = await self._pop_next_task(pipeline=True)
                    if task:
                        task_type = str(task.get("type", ""))
                        if self._pipeline_enabled_for_task_type(task_type):
                            await self._launch_pipeline_task(task)
                        else:
                            await self.process_task(task)
                        continue
                else:
                    task = await self._pop_next_task()
                    if task:
                        await self.process_task(task)
                        continue  # Immediately poll again after finishing

            except httpx.RequestError as e:
                logger.error(f"Connection to master failed: {e}")
            except Exception as e:
                logger.error(f"Polling error: {e}")

            # Wait before next poll
            await asyncio.sleep(2)

    async def start(self):
        # Ensure directories exist
        os.makedirs(COMFY_INPUT_DIR, exist_ok=True)
        os.makedirs(COMFY_OUTPUT_DIR, exist_ok=True)
        os.makedirs(PREFETCH_CACHE_DIR, exist_ok=True)
        os.makedirs(RESULT_SPOOL_DIR, exist_ok=True)

        # Start WS listener, polling loops, and heartbeat
        self.running = True
        self.tasks = [
            asyncio.create_task(self.ws_listener_loop()),
            asyncio.create_task(self.poll_loop()),
            asyncio.create_task(self.heartbeat_loop()),
        ]
        await asyncio.gather(*self.tasks)

    async def shutdown(self):
        logger.info("Initiating graceful shutdown...")
        self.running = False

        # Return unfinished local tasks to Central as failed/interrupted.
        active_executions = self._heartbeat_executions()
        for active_execution in active_executions:
            logger.info(
                f"Returning task {active_execution.task_id} to master due to shutdown"
            )
            try:
                await self.report_status(
                    active_execution.task_id,
                    "failed",
                    error="Agent was shut down while processing the task. Task should be retried.",
                )
            except Exception as e:
                logger.error(f"Failed to report task failure during shutdown: {e}")

        # Cancel all running background loops
        for task in list(getattr(self, "tasks", [])):
            task.cancel()
        for task in list(self._execution_tasks):
            task.cancel()
        if self._execution_tasks:
            await asyncio.gather(*self._execution_tasks, return_exceptions=True)
        await self._cancel_prefetch_task()
        self._discard_prefetch_cache(except_task_id=None)

        # Close HTTP clients
        await self.master_client.aclose()
        await self.comfy_client.close()
        logger.info("Shutdown complete.")


if __name__ == "__main__":
    agent = ComfyAgent()

    # Setup graceful shutdown signals
    import signal
    import sys

    loop = asyncio.get_event_loop()

    if sys.platform != "win32":
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(agent.shutdown()))

    try:
        loop.run_until_complete(agent.start())
    except asyncio.CancelledError:
        pass
    except KeyboardInterrupt:
        # 捕获 Ctrl+C，触发优雅退出逻辑，防止 Master 端任务卡死
        loop.run_until_complete(agent.shutdown())
    finally:
        loop.close()
