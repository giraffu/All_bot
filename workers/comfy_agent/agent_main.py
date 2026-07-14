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
try:
    import boto3  # type: ignore
    from boto3.s3.transfer import TransferConfig  # type: ignore
    from botocore.config import Config as BotoConfig  # type: ignore
except Exception:  # pragma: no cover - optional dependency fallback
    boto3 = None
    TransferConfig = None
    BotoConfig = None
from agent_input_preparation import (
    prepare_task_inputs as prepare_agent_task_inputs,
    process_single_input_asset as process_agent_single_input_asset,
)
from agent_finalizer import AgentFinalizer
from agent_health import AgentHealthManager
from agent_pipeline_coordinator import AgentPipelineCoordinator
from agent_prefetch_manager import AgentPrefetchManager
from agent_reporting_client import AgentReportingClient
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
from agent_result_quality import assess_materialized_output_quality
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
from scail2_face_swap_v10_pipeline import prepare_scail2_face_swap_v10_reference
from workflow_patcher import WorkflowPatcher

__all__ = [
    "ComfyAgent",
    "ControlPlaneRecoveryExit",
    "TaskExecutionTimeoutError",
]

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

CONTROL_PLANE_RECOVERY_EXIT_CODE = 75


class ControlPlaneRecoveryExit(BaseException):
    """Raised when the agent should exit and let Docker restart it."""

    pass


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
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").strip().lower() in TRUE_ENV_VALUES
MINIO_CONNECT_TIMEOUT_SECONDS = float(os.getenv("MINIO_CONNECT_TIMEOUT_SECONDS", "10"))
MINIO_READ_TIMEOUT_SECONDS = float(os.getenv("MINIO_READ_TIMEOUT_SECONDS", "45"))
MINIO_HTTP_RETRY_TOTAL = int(os.getenv("MINIO_HTTP_RETRY_TOTAL", "2"))
MINIO_HTTP_POOL_MAXSIZE = int(os.getenv("MINIO_HTTP_POOL_MAXSIZE", "8"))
MINIO_REGION = os.getenv("MINIO_REGION") or (
    "auto" if "r2.cloudflarestorage.com" in MINIO_ENDPOINT else "us-east-1"
)
MINIO_BOTO3_DOWNLOAD_ENABLED = (
    os.getenv("MINIO_BOTO3_DOWNLOAD_ENABLED", "true").strip().lower()
    in TRUE_ENV_VALUES
)
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
PREFETCH_RESERVE_TASK = os.getenv("PREFETCH_RESERVE_TASK", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
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
CANCEL_LOCK_ON_POP = (
    os.getenv("CANCEL_LOCK_ON_POP", "true").strip().lower() in TRUE_ENV_VALUES
)
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
    os.getenv("WAN22_VIDEO_V2_TIMEOUT_EXIT_CODE", str(CONTROL_PLANE_RECOVERY_EXIT_CODE))
)
AGENT_CONTROL_PLANE_RECOVERY_ENABLED = (
    os.getenv("AGENT_CONTROL_PLANE_RECOVERY_ENABLED", "true").strip().lower()
    in TRUE_ENV_VALUES
)
AGENT_CONTROL_PLANE_RECOVERY_MIN_FAILURES = int(
    os.getenv("AGENT_CONTROL_PLANE_RECOVERY_MIN_FAILURES", "12")
)
AGENT_CONTROL_PLANE_RECOVERY_SECONDS = float(
    os.getenv("AGENT_CONTROL_PLANE_RECOVERY_SECONDS", "300")
)
I2I_PRO_QUALITY_RETRY_ATTEMPTS = max(
    0,
    int(os.getenv("I2I_PRO_QUALITY_RETRY_ATTEMPTS", "1")),
)
SCAIL2_FACE_SWAP_V10_ENABLED = (
    os.getenv("SCAIL2_FACE_SWAP_V10_ENABLED", "false").strip().lower()
    in TRUE_ENV_VALUES
)
SCAIL2_FACE_SWAP_V10_FACE_SWAP_COMFY_API_URL = os.getenv(
    "SCAIL2_FACE_SWAP_V10_FACE_SWAP_COMFY_API_URL",
    "",
).rstrip("/")
SCAIL2_FACE_SWAP_V10_FACE_SWAP_WORKFLOW = os.getenv(
    "SCAIL2_FACE_SWAP_V10_FACE_SWAP_WORKFLOW",
    "face_swap_v2.json",
)
SCAIL2_FACE_SWAP_V10_TIMEOUT_SECONDS = float(
    os.getenv("SCAIL2_FACE_SWAP_V10_TIMEOUT_SECONDS", "600")
)
SCAIL2_FACE_SWAP_V10_POLL_INTERVAL_SECONDS = float(
    os.getenv("SCAIL2_FACE_SWAP_V10_POLL_INTERVAL_SECONDS", "2")
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
os.makedirs("/app/logs", exist_ok=True)
file_handler = logging.FileHandler(f"/app/logs/agent_{AGENT_ID}.log")
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
                    maxsize=MINIO_HTTP_POOL_MAXSIZE,
                ),
            )
            logger.info("MinIO client initialized")
        except Exception as e:
            logger.error(f"Failed to init MinIO: {e}")
            self.minio_client = None

        self.s3_download_client = None
        self.s3_transfer_config = None
        if MINIO_BOTO3_DOWNLOAD_ENABLED and boto3 is not None and BotoConfig is not None:
            try:
                endpoint_url = (
                    f"{'https' if MINIO_SECURE else 'http'}://{MINIO_ENDPOINT}"
                )
                self.s3_download_client = boto3.client(
                    "s3",
                    endpoint_url=endpoint_url,
                    aws_access_key_id=MINIO_ACCESS_KEY,
                    aws_secret_access_key=MINIO_SECRET_KEY,
                    region_name=MINIO_REGION,
                    config=BotoConfig(
                        signature_version="s3v4",
                        connect_timeout=MINIO_CONNECT_TIMEOUT_SECONDS,
                        read_timeout=MINIO_READ_TIMEOUT_SECONDS,
                        max_pool_connections=MINIO_HTTP_POOL_MAXSIZE,
                        retries={
                            "max_attempts": max(1, MINIO_HTTP_RETRY_TOTAL + 1),
                            "mode": "standard",
                        },
                    ),
                )
                if TransferConfig is not None:
                    self.s3_transfer_config = TransferConfig(
                        max_concurrency=max(2, min(MINIO_HTTP_POOL_MAXSIZE, 8)),
                        multipart_threshold=8 * 1024 * 1024,
                        multipart_chunksize=8 * 1024 * 1024,
                    )
                logger.info("S3 download client initialized")
            except Exception as e:
                logger.warning("Failed to init S3 download client: %s", e)
                self.s3_download_client = None
                self.s3_transfer_config = None
        elif MINIO_BOTO3_DOWNLOAD_ENABLED:
            logger.warning("boto3 unavailable; falling back to MinIO input downloads")

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
        self.control_plane_failures = 0
        self.control_plane_failure_started_at: float | None = None
        self.control_plane_last_error = ""
        self.control_plane_recovery_requested = False
        self._prefetch_cache: dict[str, dict[str, Any]] = {}
        self._prefetch_task: asyncio.Task | None = None
        self._reserved_prefetch_task: dict[str, Any] | None = None
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
        self._health_manager = AgentHealthManager(agent=self, logger=logger)
        self._prefetch_manager = AgentPrefetchManager(agent=self, logger=logger)
        self._pipeline_coordinator = AgentPipelineCoordinator(
            agent=self,
            logger=logger,
        )
        self._finalizer = AgentFinalizer(agent=self, logger=logger)
        self._reporting_client = AgentReportingClient(
            master_client=self.master_client,
            logger=logger,
            record_control_plane_success=self._record_control_plane_success,
            record_control_plane_failure=self._record_control_plane_failure,
        )

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

    def _record_control_plane_success(self) -> None:
        self._health_manager.record_control_plane_success()

    def _record_control_plane_failure(self, error: Exception | str) -> None:
        self._health_manager.record_control_plane_failure(
            error,
            recovery_enabled=AGENT_CONTROL_PLANE_RECOVERY_ENABLED,
            min_failures=AGENT_CONTROL_PLANE_RECOVERY_MIN_FAILURES,
            recovery_seconds=AGENT_CONTROL_PLANE_RECOVERY_SECONDS,
            agent_id=AGENT_ID,
            exit_code=CONTROL_PLANE_RECOVERY_EXIT_CODE,
            recovery_exit_cls=ControlPlaneRecoveryExit,
        )

    async def _master_get(self, path: str, **kwargs):
        return await self._reporting_client.master_get(path, **kwargs)

    async def _master_post(self, path: str, **kwargs):
        return await self._reporting_client.master_post(path, **kwargs)

    def _record_health_failure(self, *, reason: str, error: str) -> None:
        self._health_manager.record_health_failure(
            reason=reason,
            error=error,
            failure_threshold=COMFY_HEALTH_FAILURE_THRESHOLD,
            agent_id=AGENT_ID,
        )

    def _record_health_success(self) -> None:
        self._health_manager.record_health_success(
            recovery_threshold=COMFY_HEALTH_RECOVERY_THRESHOLD
        )

    def _is_quarantined(self) -> bool:
        return self._health_manager.is_quarantined()

    def _clear_expired_quarantine(self) -> bool:
        return self._health_manager.clear_expired_quarantine()

    def _enter_quarantine(self, *, error: str) -> None:
        self._health_manager.enter_quarantine(
            error=error,
            quarantine_seconds=COMFY_QUARANTINE_SECONDS,
            agent_id=AGENT_ID,
        )

    @staticmethod
    def _is_infrastructure_failure(error: Exception) -> bool:
        return AgentHealthManager.is_infrastructure_failure(
            error,
            user_input_markers=USER_INPUT_ERROR_MARKERS,
            infra_error_markers=INFRA_ERROR_MARKERS,
        )

    def _record_task_failure_for_health(self, error: Exception) -> None:
        self._health_manager.record_task_failure_for_health(
            error,
            user_input_markers=USER_INPUT_ERROR_MARKERS,
            infra_error_markers=INFRA_ERROR_MARKERS,
            failure_threshold=COMFY_TASK_INFRA_FAILURE_THRESHOLD,
            quarantine_seconds=COMFY_QUARANTINE_SECONDS,
            agent_id=AGENT_ID,
        )

    def _record_task_success_for_health(self) -> None:
        self._health_manager.record_task_success_for_health()

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
        return self._health_manager.worker_status()

    def _heartbeat_executions(self) -> list[TaskExecutionContext]:
        executions = list(self._executions.values())
        if not executions and self._active_execution:
            executions.append(self._active_execution)
        return executions

    def _heartbeat_health_payload(self) -> dict[str, Any]:
        return self._health_manager.heartbeat_health_payload()

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

    async def _maybe_prepare_scail2_face_swap_v10_reference(
        self,
        *,
        task_id: str,
        task_type: str,
        params: dict[str, Any],
        downloaded_input_paths: list[str],
    ) -> None:
        if task_type != "scail2_face_swap_v2" or not SCAIL2_FACE_SWAP_V10_ENABLED:
            return
        if not SCAIL2_FACE_SWAP_V10_FACE_SWAP_COMFY_API_URL:
            raise RuntimeError(
                "SCAIL2_FACE_SWAP_V10_ENABLED requires "
                "SCAIL2_FACE_SWAP_V10_FACE_SWAP_COMFY_API_URL"
            )

        await self.report_status(
            task_id,
            "running",
            execution_phase="preparing_v10_face_swap",
        )
        await prepare_scail2_face_swap_v10_reference(
            task_id=task_id,
            params=params,
            downloaded_input_paths=downloaded_input_paths,
            comfy_input_dir=COMFY_INPUT_DIR,
            workflows_dir=self.patcher.workflows_dir,
            patcher=self.patcher,
            primary_comfy_client=self.comfy_client,
            face_swap_comfy_api_url=SCAIL2_FACE_SWAP_V10_FACE_SWAP_COMFY_API_URL,
            face_swap_workflow_filename=SCAIL2_FACE_SWAP_V10_FACE_SWAP_WORKFLOW,
            client_id=f"agent_{AGENT_ID}_v10",
            logger=logger,
            timeout_seconds=SCAIL2_FACE_SWAP_V10_TIMEOUT_SECONDS,
            poll_interval_seconds=SCAIL2_FACE_SWAP_V10_POLL_INTERVAL_SECONDS,
        )

    @staticmethod
    def _parse_task_params(task: dict[str, Any]) -> dict[str, Any]:
        return AgentPrefetchManager.parse_task_params(task)

    def _should_prefetch_task_type(self, task_type: str) -> bool:
        return self._prefetch_manager.should_prefetch_task_type(
            task_type,
            prefetch_enabled=PREFETCH_ENABLED,
            prefetch_depth=PREFETCH_DEPTH,
        )

    def _cleanup_input_paths(self, paths: list[str]) -> None:
        self._prefetch_manager.cleanup_input_paths(paths)

    def _discard_prefetch_cache(self, *, except_task_id: str | None = None) -> None:
        self._prefetch_manager.discard_prefetch_cache(except_task_id=except_task_id)

    async def _wait_for_prefetch_settle(self) -> None:
        await self._prefetch_manager.wait_for_prefetch_settle(
            consume_wait_seconds=PREFETCH_CONSUME_WAIT_SECONDS,
        )

    async def _cancel_prefetch_task(self) -> None:
        await self._prefetch_manager.cancel_prefetch_task()

    def _consume_prefetched_inputs(
        self,
        *,
        task_id: str,
        task_type: str,
    ) -> dict[str, Any] | None:
        return self._prefetch_manager.consume_prefetched_inputs(
            task_id=task_id,
            task_type=task_type,
        )

    async def _prefetch_next_task_inputs(
        self,
        *,
        task_type_filter: str | None = None,
    ) -> None:
        await self._prefetch_manager.prefetch_next_task_inputs(
            task_type_filter=task_type_filter,
            prefetch_enabled=PREFETCH_ENABLED,
            prefetch_depth=PREFETCH_DEPTH,
            cache_dir=PREFETCH_CACHE_DIR,
            reserve_task=PREFETCH_RESERVE_TASK,
        )

    def _schedule_prefetch(self, *, current_task_type: str) -> None:
        self._prefetch_manager.schedule_prefetch(
            current_task_type=current_task_type,
            prefetch_enabled=PREFETCH_ENABLED,
            prefetch_depth=PREFETCH_DEPTH,
            cache_dir=PREFETCH_CACHE_DIR,
            reserve_task=PREFETCH_RESERVE_TASK,
        )

    async def report_heartbeat(self):
        await self._reporting_client.report_heartbeat(
            agent_id=AGENT_ID,
            supported_task_types=SUPPORTED_TASK_TYPES,
            status=self._worker_status(),
            health_payload=self._heartbeat_health_payload(),
            pool_payload=self._heartbeat_pool_payload(),
            executions=self._heartbeat_executions(),
        )

    async def _heartbeat_reserved_prefetch_task(self) -> None:
        task = self._reserved_prefetch_task
        task_id = str((task or {}).get("task_id", ""))
        if not task_id:
            return
        await self.report_status(
            task_id,
            "running",
            execution_phase="prefetching",
            cancel_locked=CANCEL_LOCK_ON_POP,
            set_current=False,
        )

    async def heartbeat_loop(self):
        logger.info(f"Agent {AGENT_ID} started heartbeat loop...")
        while getattr(self, "running", True):
            await self.report_heartbeat()
            await self._heartbeat_reserved_prefetch_task()
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
        await self._reporting_client.report_status(
            task_id=task_id,
            agent_id=AGENT_ID,
            status=status,
            progress=progress,
            error=error,
            execution_phase=execution_phase,
            cancel_locked=cancel_locked,
            set_current=set_current,
            attempts=max(1, STATUS_REPORT_MAX_ATTEMPTS),
            retry_base_seconds=STATUS_REPORT_RETRY_BASE_SECONDS,
            retry_max_seconds=STATUS_REPORT_RETRY_MAX_SECONDS,
            sleep_func=asyncio.sleep,
        )

    async def report_complete(
        self,
        task_id: str,
        result_path: str,
        *,
        extra_outputs: dict[str, Any] | None = None,
    ):
        await self._reporting_client.report_complete(
            task_id=task_id,
            agent_id=AGENT_ID,
            result_path=result_path,
            extra_outputs=extra_outputs,
            attempts=max(1, COMPLETE_REPORT_MAX_ATTEMPTS),
            retry_base_seconds=COMPLETE_REPORT_RETRY_BASE_SECONDS,
            retry_max_seconds=COMPLETE_REPORT_RETRY_MAX_SECONDS,
            sleep_func=asyncio.sleep,
        )

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

    def _download_input_from_s3(
        self,
        *,
        bucket_name: str,
        object_name: str,
        local_path: str,
    ) -> None:
        if not self.s3_download_client:
            raise RuntimeError("S3 download client not initialized")

        extra_args = None
        if self.s3_transfer_config is not None:
            self.s3_download_client.download_file(
                bucket_name,
                object_name,
                local_path,
                Config=self.s3_transfer_config,
                ExtraArgs=extra_args,
            )
            return

        self.s3_download_client.download_file(
            bucket_name,
            object_name,
            local_path,
            ExtraArgs=extra_args,
        )

    def download_input_from_minio(self, object_name: str, local_path: str):
        if not self.minio_client and not self.s3_download_client:
            raise Exception("Object storage client not initialized")

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
        if self.s3_download_client is not None:
            self._download_input_from_s3(
                bucket_name=bucket_name,
                object_name=real_object_name,
                local_path=local_path,
            )
            return

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
            response = await self._master_get(f"/api/agent/task/check/{task_id}")
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "cancelled" or data.get("cancel_requested"):
                    return True
        except Exception as e:
            logger.debug(f"Failed to check task status: {e}")
        return False

    def _pipeline_enabled_for_task_type(self, task_type: str) -> bool:
        return self._pipeline_coordinator.pipeline_enabled_for_task_type(
            task_type,
            pipeline_enabled=PIPELINE_ENABLED,
            pipeline_max_running_tasks=PIPELINE_MAX_RUNNING_TASKS,
            pipeline_task_types=self._pipeline_task_types,
        )

    def _pipeline_pop_types(self) -> str:
        return self._pipeline_coordinator.pipeline_pop_types(
            supported_task_types=SUPPORTED_TASK_TYPES,
            pipeline_task_types=self._pipeline_task_types,
        )

    def _build_pop_params(self, *, pipeline: bool = False) -> dict[str, str]:
        return self._pipeline_coordinator.build_pop_params(
            agent_id=AGENT_ID,
            supported_task_types=SUPPORTED_TASK_TYPES,
            pipeline_task_types=self._pipeline_task_types,
            cancel_lock_on_pop=CANCEL_LOCK_ON_POP,
            pipeline=pipeline,
        )

    async def _pop_next_task(self, *, pipeline: bool = False) -> dict[str, Any] | None:
        if self._reserved_prefetch_task is not None:
            task = self._reserved_prefetch_task
            self._reserved_prefetch_task = None
            logger.info("Using locally reserved prefetched task %s", task.get("task_id"))
            return task
        return await self._pipeline_coordinator.pop_next_task(
            agent_id=AGENT_ID,
            supported_task_types=SUPPORTED_TASK_TYPES,
            pipeline_task_types=self._pipeline_task_types,
            cancel_lock_on_pop=CANCEL_LOCK_ON_POP,
            pipeline=pipeline,
        )

    async def _prepare_and_submit_task(
        self,
        task: Dict[str, Any],
        *,
        allow_cancel_check: bool = True,
    ) -> TaskExecutionContext | None:
        return await self._pipeline_coordinator.prepare_and_submit_task(
            task,
            allow_cancel_check=allow_cancel_check,
            cancel_lock_on_pop=CANCEL_LOCK_ON_POP,
            agent_id=AGENT_ID,
            submit_task_workflow_func=submit_task_workflow,
        )

    def _reset_execution_for_retry(
        self,
        execution: TaskExecutionContext,
        *,
        seed: int,
    ) -> dict[str, Any]:
        return self._finalizer.reset_execution_for_retry(execution, seed=seed)

    async def _retry_execution_after_quality_issue(
        self,
        execution: TaskExecutionContext,
        *,
        issue_reason: str,
        retry_number: int,
    ) -> bool:
        return await self._finalizer.retry_execution_after_quality_issue(
            execution,
            issue_reason=issue_reason,
            retry_number=retry_number,
            quality_retry_attempts=I2I_PRO_QUALITY_RETRY_ATTEMPTS,
            agent_id=AGENT_ID,
            submit_task_workflow_func=submit_task_workflow,
            wait_for_task_completion_func=wait_for_task_completion,
        )

    async def _materialize_outputs_with_quality_retry(
        self,
        *,
        execution: TaskExecutionContext,
        task_type: str,
    ):
        return await self._finalizer.materialize_outputs_with_quality_retry(
            execution=execution,
            task_type=task_type,
            quality_retry_attempts=I2I_PRO_QUALITY_RETRY_ATTEMPTS,
            agent_id=AGENT_ID,
            submit_task_workflow_func=submit_task_workflow,
            wait_for_task_completion_func=wait_for_task_completion,
            resolve_execution_result_from_history_func=(
                resolve_execution_result_from_history
            ),
            materialize_task_outputs_func=materialize_task_outputs,
            assess_materialized_output_quality_func=(
                assess_materialized_output_quality
            ),
        )

    async def _finalize_execution(self, execution: TaskExecutionContext) -> None:
        await self._finalizer.finalize_execution(
            execution,
            cancel_lock_on_pop=CANCEL_LOCK_ON_POP,
            upload_sidecar_url=UPLOAD_SIDECAR_URL,
            result_spool_dir=RESULT_SPOOL_DIR,
            result_bucket=MINIO_RESULT_BUCKET,
            wan22_timeout_exit_code=WAN22_VIDEO_V2_TIMEOUT_EXIT_CODE,
            quality_retry_attempts=I2I_PRO_QUALITY_RETRY_ATTEMPTS,
            agent_id=AGENT_ID,
            submit_task_workflow_func=submit_task_workflow,
            wait_for_task_completion_func=wait_for_task_completion,
            resolve_execution_result_from_history_func=(
                resolve_execution_result_from_history
            ),
            materialize_task_outputs_func=materialize_task_outputs,
            assess_materialized_output_quality_func=(
                assess_materialized_output_quality
            ),
            spool_materialized_outputs_func=spool_materialized_outputs,
            upload_spooled_outputs_via_sidecar_func=upload_spooled_outputs_via_sidecar,
            upload_materialized_outputs_func=upload_materialized_outputs,
            report_materialized_outputs_func=report_materialized_outputs,
        )

    def _track_execution_task(self, task: asyncio.Task) -> None:
        self._execution_tasks.add(task)
        task.add_done_callback(self._execution_tasks.discard)

    async def _launch_pipeline_task(self, task: Dict[str, Any]) -> None:
        await self._pipeline_coordinator.launch_pipeline_task(
            task,
            cancel_lock_on_pop=CANCEL_LOCK_ON_POP,
        )

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

    async def shutdown(self, *, report_interrupted_tasks: bool = True):
        logger.info("Initiating graceful shutdown...")
        self.running = False

        # Return unfinished local tasks to Central as failed/interrupted.
        if report_interrupted_tasks:
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
    except ControlPlaneRecoveryExit:
        loop.run_until_complete(agent.shutdown(report_interrupted_tasks=False))
        sys.exit(CONTROL_PLANE_RECOVERY_EXIT_CODE)
    except asyncio.CancelledError:
        pass
    except KeyboardInterrupt:
        # 捕获 Ctrl+C，触发优雅退出逻辑，防止 Master 端任务卡死
        loop.run_until_complete(agent.shutdown())
    finally:
        loop.close()
