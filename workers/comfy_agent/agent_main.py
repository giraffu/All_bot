import asyncio
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import httpx
import websockets  # type: ignore
from asgi_correlation_id import correlation_id
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

COMFY_API_URL = os.getenv("COMFY_API_URL", "http://127.0.0.1:8188")
COMFY_WS_URL = os.getenv("COMFY_WS_URL", "ws://127.0.0.1:8188/ws")
COMFY_INPUT_DIR = os.getenv("COMFY_INPUT_DIR", "/tmp/input")
COMFY_OUTPUT_DIR = os.getenv("COMFY_OUTPUT_DIR", "/tmp/output")

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "play.min.io:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "your_key")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "your_secret")
MINIO_INPUT_BUCKET = os.getenv("MINIO_INPUT_BUCKET", "comfyui-input")
MINIO_RESULT_BUCKET = os.getenv("MINIO_RESULT_BUCKET", "comfyui-output")
COMFY_READY_RETRY_ATTEMPTS = int(os.getenv("COMFY_READY_RETRY_ATTEMPTS", "5"))
COMFY_READY_RETRY_DELAY_SECONDS = float(
    os.getenv("COMFY_READY_RETRY_DELAY_SECONDS", "2")
)
COMFY_UPLOAD_RETRY_ATTEMPTS = int(os.getenv("COMFY_UPLOAD_RETRY_ATTEMPTS", "3"))

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


@dataclass
class TaskExecutionContext:
    task_id: str
    task_type: str
    prompt_id: Optional[str] = None
    task_result: Optional[str] = None
    task_result_priority: int = -1
    task_error: Optional[str] = None
    completed_event: asyncio.Event = field(default_factory=asyncio.Event)


RESULT_ASSET_KEYS = ("images", "gifs", "videos")


def _coerce_first_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                return item
    return {}


def _extract_ws_data_content(data: dict[str, Any]) -> dict[str, Any]:
    return _coerce_first_mapping(data.get("data", {}))


def _result_asset_keys_for_task(task_type: str | None) -> tuple[str, ...]:
    if task_type == "wan22_video_v2":
        # `wan22_video_v2` must always materialize a video as the primary result.
        # Tail-frame images are auxiliary outputs and must not be used as fallback.
        return ("videos", "gifs")
    return RESULT_ASSET_KEYS


def _pick_first_output_asset(
    outputs: Any,
    *,
    task_type: str | None = None,
) -> dict[str, Any] | None:
    if not isinstance(outputs, dict):
        return None
    asset_keys = _result_asset_keys_for_task(task_type)
    for asset_key in asset_keys:
        for node_output in outputs.values():
            if not isinstance(node_output, dict):
                continue
            assets = node_output.get(asset_key, [])
            if assets:
                asset = assets[0]
                if isinstance(asset, dict):
                    return {**asset, "_asset_key": asset_key}
                return asset
    return None


def _result_asset_priority(asset: dict[str, Any] | None, *, task_type: str | None) -> int:
    if not isinstance(asset, dict):
        return -1
    asset_key = str(asset.get("_asset_key") or "").strip().lower()
    if task_type == "wan22_video_v2":
        return {"videos": 3, "gifs": 2}.get(asset_key, 0)
    return 0


def _build_safe_result_object_name(task_id: str, asset: dict[str, Any]) -> str:
    return (
        f"{task_id}_{asset.get('subfolder', '')}_{asset.get('filename')}"
        .replace("/", "_")
        .lstrip("_")
    )


def _iter_output_assets(outputs: Any) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    if not isinstance(outputs, dict):
        return collected
    for node_output in outputs.values():
        if not isinstance(node_output, dict):
            continue
        for asset_key in RESULT_ASSET_KEYS:
            assets = node_output.get(asset_key, [])
            if not isinstance(assets, list):
                continue
            for asset in assets:
                if isinstance(asset, dict):
                    collected.append(asset)
    return collected


def _resolve_history_result_asset(
    history: dict[str, Any] | None,
    *,
    prompt_id: str | None,
    task_id: str | None,
    task_type: str | None = None,
) -> dict[str, str] | None:
    if not history or not prompt_id or not task_id or prompt_id not in history:
        return None

    outputs = history[prompt_id].get("outputs", {})
    asset = _pick_first_output_asset(outputs, task_type=task_type)
    if not asset:
        return None

    original_filename = asset.get("filename", "")
    if not original_filename:
        return None

    return {
        "safe_name": _build_safe_result_object_name(task_id, asset),
        "filename": original_filename,
        "subfolder": asset.get("subfolder", ""),
        "type": asset.get("type", ""),
        "asset_key": asset.get("_asset_key", ""),
    }


def _resolve_history_extra_output_assets(
    history: dict[str, Any] | None,
    *,
    prompt_id: str | None,
    task_id: str | None,
    task_type: str | None = None,
) -> dict[str, dict[str, Any]]:
    if task_type != "wan22_video_v2" or not history or not prompt_id or not task_id:
        return {}
    prompt_history = history.get(prompt_id)
    if not isinstance(prompt_history, dict):
        return {}
    outputs = prompt_history.get("outputs", {})
    if not isinstance(outputs, dict):
        return {}

    resolved: dict[str, dict[str, Any]] = {}
    for asset in _iter_output_assets(outputs):
        filename = str(asset.get("filename") or "")
        if "last_frame" not in filename.lower():
            continue
        resolved["last_frame"] = {
            "path": _build_safe_result_object_name(task_id, asset),
            "media_type": "image",
            "filename": filename,
            "subfolder": asset.get("subfolder", ""),
            "type": asset.get("type", "output"),
        }
        break
    return resolved


def _resolve_comfy_view_type(asset: dict[str, Any] | None) -> str:
    if not asset:
        return "output"

    asset_type = str(asset.get("type", "") or "").strip().lower()
    if asset_type in {"temp", "output", "input"}:
        return asset_type

    subfolder = str(asset.get("subfolder", "") or "").strip().lower()
    if subfolder == "temp" or subfolder.startswith("temp/") or "/temp/" in f"/{subfolder}/":
        return "temp"

    filename = str(asset.get("filename", "") or "").strip().lower()
    if "/temp/" in filename or filename.startswith("temp/"):
        return "temp"

    return "output"


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
                secure=False,  # Set to True if using HTTPS
            )
            logger.info("MinIO client initialized")
        except Exception as e:
            logger.error(f"Failed to init MinIO: {e}")
            self.minio_client = None

        self.tasks = []
        self._idle_completed_event = asyncio.Event()
        self._active_execution: Optional[TaskExecutionContext] = None
        self.running = False
        self._comfy_poll_paused = False

    @property
    def current_task_id(self) -> Optional[str]:
        return self._active_execution.task_id if self._active_execution else None

    @property
    def current_task_type(self) -> Optional[str]:
        return self._active_execution.task_type if self._active_execution else None

    @property
    def current_prompt_id(self) -> Optional[str]:
        return self._active_execution.prompt_id if self._active_execution else None

    @property
    def task_result(self) -> Optional[str]:
        return self._active_execution.task_result if self._active_execution else None

    @property
    def task_result_priority(self) -> int:
        return self._active_execution.task_result_priority if self._active_execution else -1

    @property
    def task_error(self) -> Optional[str]:
        return self._active_execution.task_error if self._active_execution else None

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
        return execution

    def _clear_task_execution(
        self, execution: TaskExecutionContext | None = None
    ) -> None:
        if execution is not None and self._active_execution is not execution:
            return
        self._active_execution = None
        self._idle_completed_event.clear()

    async def _probe_comfy_ready(self) -> bool:
        try:
            response = await self.comfy_client.client.get("/system_stats")
            return response.status_code == 200
        except Exception:
            return False

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
            raise RuntimeError(f"Downloaded file is not a valid image: {local_path}") from exc
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
        raise RuntimeError(f"Failed to upload prepared input '{source_name}' to ComfyUI") from last_error

    async def _process_single_input_asset(
        self,
        *,
        params: dict[str, Any],
        downloaded_input_paths: list[str],
        img_filename: str,
        param_key: str,
    ) -> None:
        local_safe_filename = img_filename.replace("/", "_").replace("template:", "")
        local_img_path = os.path.join(COMFY_INPUT_DIR, local_safe_filename)
        try:
            await asyncio.to_thread(
                self.download_input_from_minio, img_filename, local_img_path
            )
            logger.info(f"Downloaded {param_key} to {local_img_path}")
            if local_img_path not in downloaded_input_paths:
                downloaded_input_paths.append(local_img_path)
            upload_path = local_img_path
            upload_name = local_safe_filename
            if self._should_normalize_image_input(param_key, img_filename):
                upload_path = await asyncio.to_thread(
                    self._normalize_input_image_for_comfy, local_img_path
                )
                upload_name = os.path.basename(upload_path)
                if upload_path not in downloaded_input_paths:
                    downloaded_input_paths.append(upload_path)
                logger.info(
                    "Normalized %s input for ComfyUI: %s -> %s",
                    param_key,
                    local_img_path,
                    upload_path,
                )
            await self._upload_prepared_input(
                upload_path=upload_path,
                upload_name=upload_name,
                source_name=img_filename,
            )
            params[param_key] = upload_name
        except Exception as e:
            logger.error(f"Failed to process {param_key} {img_filename}: {e}")
            raise RuntimeError(
                f"Failed to prepare {param_key} input '{img_filename}'"
            ) from e

    async def _prepare_task_inputs(
        self,
        *,
        params: dict[str, Any],
        downloaded_input_paths: list[str],
    ) -> None:
        if (
            "images" in params
            and isinstance(params["images"], list)
            and len(params["images"]) > 0
        ):
            images_list = params["images"]
            tasks = []
            keys = ["image", "image2", "image3"]
            for i, img_filename in enumerate(images_list[:3]):
                tasks.append(
                    self._process_single_input_asset(
                        params=params,
                        downloaded_input_paths=downloaded_input_paths,
                        img_filename=img_filename,
                        param_key=keys[i],
                    )
                )
            if tasks:
                await asyncio.gather(*tasks)
        else:
            legacy_tasks = []
            if "image" in params and params["image"]:
                legacy_tasks.append(
                    self._process_single_input_asset(
                        params=params,
                        downloaded_input_paths=downloaded_input_paths,
                        img_filename=params["image"],
                        param_key="image",
                    )
                )
            if "image2" in params and params["image2"]:
                legacy_tasks.append(
                    self._process_single_input_asset(
                        params=params,
                        downloaded_input_paths=downloaded_input_paths,
                        img_filename=params["image2"],
                        param_key="image2",
                    )
                )
            if legacy_tasks:
                await asyncio.gather(*legacy_tasks)

        other_tasks = []
        for key in ["face_image", "body_image", "video", "end_image"]:
            if key in params and params[key]:
                other_tasks.append(
                    self._process_single_input_asset(
                        params=params,
                        downloaded_input_paths=downloaded_input_paths,
                        img_filename=params[key],
                        param_key=key,
                    )
                )
        if other_tasks:
            await asyncio.gather(*other_tasks)

    async def report_heartbeat(self):
        try:
            active_execution = self._active_execution
            status = "running" if active_execution else "idle"
            await self.master_client.post(
                "/api/agent/task/heartbeat",
                json={
                    "agent_id": AGENT_ID,
                    "types": SUPPORTED_TASK_TYPES,
                    "status": status,
                },
            )
            if active_execution:
                # Add task heartbeat specifically
                await self.master_client.post(
                    "/api/agent/task/task_heartbeat",
                    json={"task_id": active_execution.task_id},
                )
        except Exception as e:
            logger.debug(f"Failed to report heartbeat: {e}")

    async def heartbeat_loop(self):
        logger.info(f"Agent {AGENT_ID} started heartbeat loop...")
        while getattr(self, "running", True):
            await self.report_heartbeat()
            await asyncio.sleep(15)  # Send heartbeat every 15 seconds

    async def report_status(
        self, task_id: str, status: str, progress: float = 0.0, error: str = ""
    ):
        try:
            await self.master_client.post(
                "/api/agent/task/status",
                json={
                    "task_id": task_id,
                    "agent_id": AGENT_ID,
                    "status": status,
                    "progress": progress,
                    "error": error,
                },
            )
        except Exception as e:
            logger.error(f"Failed to report status for task {task_id}: {e}")

    async def report_complete(
        self,
        task_id: str,
        result_path: str,
        *,
        extra_outputs: dict[str, Any] | None = None,
    ):
        try:
            await self.master_client.post(
                "/api/agent/task/complete",
                json={
                    "task_id": task_id,
                    "agent_id": AGENT_ID,
                    "result": result_path,
                    "extra_outputs": extra_outputs or {},
                },
            )
        except Exception as e:
            logger.error(f"Failed to report completion for task {task_id}: {e}")

    async def report_cancelled(self, task_id: str):
        await self.report_status(task_id, "cancelled")

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
                            # Use timeout to periodically check connection state
                            message = await asyncio.wait_for(
                                websocket.recv(), timeout=60.0
                            )
                        except asyncio.TimeoutError:
                            if websocket.state == websockets.protocol.State.CLOSED:
                                logger.error("WebSocket closed unexpectedly")
                                break
                            try:
                                await websocket.ping()
                            except Exception as e:
                                logger.error(f"WebSocket ping failed: {e}")
                                break
                            continue

                        if isinstance(message, bytes):
                            continue

                        try:
                            data = json.loads(message)
                        except json.JSONDecodeError:
                            continue

                        if not isinstance(data, dict):
                            continue
                        try:
                            msg_type = data.get("type")
                            data_content = _extract_ws_data_content(data)
                            prompt_id = data_content.get("prompt_id")
                            execution = self._active_execution

                            if (
                                not execution
                                or not prompt_id
                                or prompt_id != execution.prompt_id
                            ):
                                continue

                            if msg_type == "execution_start":
                                logger.info(f"Execution started for prompt {prompt_id}")
                                if execution.task_id:
                                    await self.report_status(
                                        execution.task_id, "running"
                                    )

                            elif msg_type == "progress":
                                value = data_content.get("value", 0)
                                max_val = data_content.get("max", 1)
                                if max_val > 0 and execution.task_id:
                                    progress = value / max_val
                                    await self.report_status(
                                        execution.task_id,
                                        "running",
                                        progress=progress,
                                    )

                            elif msg_type == "executing":
                                node = data_content.get("node")
                                if node is None:
                                    logger.info(
                                        f"Execution fully completed for prompt {prompt_id}"
                                    )
                                    execution.completed_event.set()

                            elif msg_type == "execution_success":
                                logger.info(
                                    f"Execution success received for prompt {prompt_id}"
                                )
                                execution.completed_event.set()

                            elif msg_type == "executed":
                                logger.info(f"Node executed for prompt {prompt_id}")
                                output = data_content.get("output") or {}
                                asset = _pick_first_output_asset(
                                    output,
                                    task_type=execution.task_type,
                                )
                                if asset and execution.task_id:
                                    asset_priority = _result_asset_priority(
                                        asset,
                                        task_type=execution.task_type,
                                    )
                                    if asset_priority >= execution.task_result_priority:
                                        execution.task_result = _build_safe_result_object_name(
                                            execution.task_id, asset
                                        )
                                        execution.task_result_priority = asset_priority
                                    # Wait for execution completion to finalize upload/report.

                            elif msg_type == "execution_error":
                                error_msg = str(
                                    data_content.get(
                                        "exception_message", "Unknown error"
                                    )
                                )
                                logger.error(
                                    f"Execution error for prompt {prompt_id}: {error_msg}"
                                )
                                execution.task_error = error_msg
                                execution.completed_event.set()
                        except Exception as message_error:
                            logger.warning(
                                "Failed to parse WS message type=%s: %s",
                                data.get("type"),
                                message_error,
                            )
                            continue

            except Exception as e:
                logger.error(f"WebSocket connection error: {e}")
                await asyncio.sleep(5)

    def download_input_from_minio(self, object_name: str, local_path: str):
        if not self.minio_client:
            raise Exception("MinIO client not initialized")

        bucket_name = MINIO_INPUT_BUCKET
        real_object_name = object_name

        if object_name.startswith("template:"):
            bucket_name = "bot-template"
            real_object_name = object_name.replace("template:", "")

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

    async def process_task(self, task: Dict[str, Any]):
        trace_id = task.get("trace_id", "")
        if trace_id:
            correlation_id.set(trace_id)

        task_id = str(task.get("task_id", ""))
        if not task_id:
            logger.error("Received task without task_id")
            return

        task_type = str(task.get("type", ""))
        params_str = task.get("params", "{}")

        if isinstance(params_str, str):
            params = json.loads(params_str)
        else:
            params = params_str

        logger.info(f"Processing task {task_id} of type {task_type}")
        execution = self._start_task_execution(task_id=task_id, task_type=task_type)
        extra_outputs: dict[str, dict[str, Any]] = {}

        downloaded_input_paths = []

        try:
            if await self.check_task_cancelled(task_id):
                logger.info(f"Task {task_id} was cancelled before processing.")
                await self.report_cancelled(task_id)
                return

            await self._prepare_task_inputs(
                params=params,
                downloaded_input_paths=downloaded_input_paths,
            )

            # 2. Load and patch workflow
            workflow = self.patcher.load_workflow(task_type)
            if not workflow:
                raise ValueError(f"Workflow for {task_type} not found")

            patched_workflow = self.patcher.patch_workflow(task_type, workflow, params)

            # 3. Submit to ComfyUI
            client_id = f"agent_{AGENT_ID}"
            await self._wait_for_comfy_ready(operation=f"submitting task {task_id}")
            execution.prompt_id = await self.comfy_client.queue_prompt(
                patched_workflow, client_id
            )
            logger.info(
                f"Submitted task {task_id} to ComfyUI, prompt_id: {execution.prompt_id}"
            )

            await self.report_status(task_id, "running")

            # 4. Wait for completion (via WS listener)
            # Timeout after 10 minutes to avoid hanging forever.
            # While waiting, periodically poll the master so cancellation
            # requests can be finalized instead of lingering at running=1%.
            loop = asyncio.get_running_loop()
            deadline = loop.time() + 600.0
            while not execution.completed_event.is_set():
                if await self.check_task_cancelled(task_id):
                    logger.info(
                        f"Task {task_id} was cancelled during execution wait."
                    )
                    await self.report_cancelled(task_id)
                    return

                remaining = deadline - loop.time()
                if remaining <= 0:
                    logger.warning(
                        f"Task execution timed out for {task_id}, will attempt to fetch result from history."
                    )
                    break

                try:
                    await asyncio.wait_for(
                        execution.completed_event.wait(),
                        timeout=min(2.0, remaining),
                    )
                except asyncio.TimeoutError:
                    continue

            if execution.task_error:
                raise Exception(execution.task_error)

            if not execution.task_result:
                logger.info(
                    f"Task result not set via WS, checking history for prompt {execution.prompt_id}"
                )
                try:
                    history = await self.comfy_client.get_history(execution.prompt_id)
                    history_result = _resolve_history_result_asset(
                        history,
                        prompt_id=execution.prompt_id,
                        task_id=execution.task_id,
                        task_type=task_type,
                    )
                    if history_result:
                        execution.task_result = history_result["safe_name"]
                        execution.task_result_priority = _result_asset_priority(
                            history_result,
                            task_type=task_type,
                        )
                    extra_outputs = _resolve_history_extra_output_assets(
                        history,
                        prompt_id=execution.prompt_id,
                        task_id=execution.task_id,
                        task_type=task_type,
                    )
                except Exception as e:
                    logger.warning(f"Failed to fetch history: {e}")

            if not execution.task_result:
                raise Exception("Task completed but no result path found")

            if await self.check_task_cancelled(task_id):
                logger.info(
                    f"Task {task_id} was cancelled during execution, skipping upload."
                )
                await self.report_cancelled(task_id)
                return

            # 5. Fetch result from ComfyUI API and Upload to MinIO
            # We must fetch the file via the ComfyUI /view API since Agent might not have direct local disk access
            # or the file might be in temp/output directories on the ComfyUI server.
            try:
                # 现在的 task_result 格式如: task_id_subfolder_filename.png
                # 我们需要提取出原始的 filename 来从 ComfyUI API 获取文件
                # 由于 task_result 已经被替换过下划线，这里不能简单地 split('/')
                # 我们假设原始文件名在最后一个 '_' 之后（这是一种简化的假设，更严谨的做法是在上报前保留原始文件名）
                # 这里我们修改逻辑：在上报前，先提取 ComfyUI 原始返回的 filename 和 subfolder
                # 由于前面我们将 result 加上了 task_id 前缀，我们需要回溯原始数据

                # 为了不改变 ComfyUI 的请求逻辑，我们需要从 ComfyUI 的历史记录中重新提取原始 filename 和 subfolder
                history = await self.comfy_client.get_history(execution.prompt_id)
                history_result = _resolve_history_result_asset(
                    history,
                    prompt_id=execution.prompt_id,
                    task_id=execution.task_id,
                    task_type=task_type,
                )
                extra_outputs = _resolve_history_extra_output_assets(
                    history,
                    prompt_id=execution.prompt_id,
                    task_id=execution.task_id,
                    task_type=task_type,
                )
                if not history_result:
                    raise Exception(
                        "Could not retrieve original filename from ComfyUI history"
                    )
                if task_type == "wan22_video_v2":
                    execution.task_result = history_result["safe_name"]
                    execution.task_result_priority = _result_asset_priority(
                        history_result,
                        task_type=task_type,
                    )
                original_filename = history_result["filename"]
                original_subfolder = history_result["subfolder"]

                view_type = _resolve_comfy_view_type(history_result)

                logger.info(
                    f"Fetching result {original_filename} from ComfyUI API (subfolder: '{original_subfolder}', type: '{view_type}')"
                )

                file_data = await self.comfy_client.get_view(
                    original_filename, original_subfolder, type=view_type
                )

                # Upload the fetched bytes directly to MinIO using the safe prefixed task_result name
                import io

                content_type = "image/png"
                if original_filename.endswith(".mp4"):
                    content_type = "video/mp4"
                elif original_filename.endswith(".gif"):
                    content_type = "image/gif"
                elif original_filename.endswith(".jpg") or original_filename.endswith(
                    ".jpeg"
                ):
                    content_type = "image/jpeg"

                logger.info(
                    f"Uploading result {execution.task_result} to MinIO bucket {MINIO_RESULT_BUCKET}"
                )
                await asyncio.to_thread(
                    self.minio_client.put_object,
                    MINIO_RESULT_BUCKET,
                    execution.task_result,
                    io.BytesIO(file_data),
                    len(file_data),
                    content_type=content_type,
                )

                for name, extra_output in list(extra_outputs.items()):
                    extra_filename = extra_output.get("filename")
                    extra_subfolder = extra_output.get("subfolder")
                    if not extra_filename or extra_subfolder is None:
                        continue
                    extra_view_type = extra_output.get("type", "output")
                    extra_file_data = await self.comfy_client.get_view(
                        extra_filename,
                        extra_subfolder,
                        type=extra_view_type,
                    )
                    await asyncio.to_thread(
                        self.minio_client.put_object,
                        MINIO_RESULT_BUCKET,
                        extra_output["path"],
                        io.BytesIO(extra_file_data),
                        len(extra_file_data),
                        content_type="image/png",
                    )
                    extra_outputs[name] = {
                        "path": extra_output["path"],
                        "media_type": extra_output.get("media_type", "image"),
                    }

            except Exception as e:
                logger.error(f"Failed to fetch from ComfyUI or upload to MinIO: {e}")
                raise Exception(f"Result processing failed: {e}")

            # 6. Report completion
            await self.report_complete(
                task_id,
                execution.task_result,
                extra_outputs=extra_outputs,
            )
            logger.info(f"Task {task_id} completed successfully")

        except Exception as e:
            logger.error(f"Task {task_id} failed: {e}")
            await self.report_status(task_id, "failed", error=str(e))
        finally:
            self._clear_task_execution(execution)
            for path in downloaded_input_paths:
                try:
                    if os.path.exists(path):
                        os.remove(path)
                        logger.info(f"Cleaned up input file: {path}")
                except Exception as e:
                    logger.warning(f"Failed to clean up input file {path}: {e}")

    async def poll_loop(self):
        logger.info(
            f"Agent {AGENT_ID} started polling {MASTER_API_URL} for tasks (types: {SUPPORTED_TASK_TYPES or 'all'})..."
        )
        while getattr(self, "running", True):
            try:
                if not await self._probe_comfy_ready():
                    if not self._comfy_poll_paused:
                        logger.warning(
                            "ComfyUI is unavailable; pausing task polling until it recovers"
                        )
                        self._comfy_poll_paused = True
                    await asyncio.sleep(COMFY_READY_RETRY_DELAY_SECONDS)
                    continue
                if self._comfy_poll_paused:
                    logger.info("ComfyUI is reachable again; resuming task polling")
                    self._comfy_poll_paused = False

                # Poll for tasks with optional type filtering
                params = {}
                if SUPPORTED_TASK_TYPES:
                    params["types"] = SUPPORTED_TASK_TYPES

                response = await self.master_client.get(
                    "/api/agent/task/pop", params=params
                )
                if response.status_code == 200:
                    data = response.json()
                    task = data.get("task")
                    if task:
                        await self.process_task(task)
                        continue  # Immediately poll again after finishing
                elif response.status_code != 404:  # 404 means no tasks, which is fine
                    logger.warning(
                        f"Unexpected response from master: {response.status_code}"
                    )

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

        # If there is a task currently running, report it as failed/interrupted back to master
        active_execution = self._active_execution
        if active_execution:
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
