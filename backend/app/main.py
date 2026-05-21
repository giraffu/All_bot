import asyncio
import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from typing import Annotated, Optional

from app.config import settings
from app.models import (
    FaceSwapRequest,
    FaceVideoRequest,
    I2IProRequest,
    I2IDrawRequest,
    Img2ImgLoraRequest,
    Img2ImgRequest,
    LtxVideoRequest,
    SystemStatusResponse,
    SystemWorkersResponse,
    T2ITaskResponse,
    TaskResponse,
    TaskStatusResponse,
    TaskType,
    VideoEditRequest,
    VideoInsertRequest,
    VideoLoraRequest,
)
from app.queue_manager import QueueManager
from app.routers import agent
from asgi_correlation_id import CorrelationIdMiddleware
from fastapi import (
    BackgroundTasks,
    Body,
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Request,
)
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from minio import Minio
from redis.asyncio import Redis

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(fastapi_app: FastAPI):
    asyncio.create_task(check_zombie_tasks_loop())

    # Init MinIO
    try:
        minio_client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        fastapi_app.state.minio_client = minio_client
        logger.info(f"MinIO client initialized: {settings.minio_endpoint}")
    except Exception as e:
        logger.error(f"Failed to init MinIO: {e}")
        fastapi_app.state.minio_client = None

    yield


app = FastAPI(title="ComfyUI Middleware", lifespan=lifespan)
app.add_middleware(CorrelationIdMiddleware, header_name="X-Trace-ID")
app.include_router(agent.router)
security = HTTPBearer()


def get_minio_client(request: Request) -> Optional[Minio]:
    return getattr(request.app.state, "minio_client", None)


# Dependency for Redis
async def get_redis():
    redis = Redis.from_url(settings.redis_url)
    try:
        yield redis
    finally:
        await redis.close()


# Dependency for QueueManager
async def get_queue_manager(redis: Redis = Depends(get_redis)):
    return QueueManager(redis)


async def check_zombie_tasks_loop():
    while True:
        try:
            # Re-use the settings from app.config
            redis = Redis.from_url(settings.redis_url)
            queue_manager = QueueManager(redis)
            await queue_manager.check_zombie_tasks()
            await redis.close()
        except Exception as e:
            logger.error(f"Error in check_zombie_tasks_loop: {e}")
        await asyncio.sleep(60)


async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if credentials.credentials != settings.auth_token:
        raise HTTPException(status_code=401, detail="Invalid token")
    return credentials.credentials


QueueManagerDep = Annotated[QueueManager, Depends(get_queue_manager)]
AuthTokenDep = Annotated[str, Depends(verify_token)]
MinioClientDep = Annotated[Optional[Minio], Depends(get_minio_client)]

SIMPLE_TASK_TYPE_MAP = {
    "img2img": TaskType.IMG2IMG,
    "img2img_lora": TaskType.IMG2IMG_LORA,
    "face_swap": TaskType.FACE_SWAP,
    "video_insert": TaskType.VIDEO_INSERT,
    "video_edit": TaskType.VIDEO_EDIT,
    "video_lora": TaskType.VIDEO_EDIT,
    "face_video": TaskType.FACE_VIDEO,
    "i2i_pro": TaskType.I2I_PRO,
    "i2i_draw": TaskType.I2I_DRAW,
    "ltx_video": TaskType.LTX_VIDEO,
}

SIMPLE_TASK_ROUTE_SPECS = (
    ("/comfy_img2img", Img2ImgRequest, "img2img", "create_img2img_task"),
    (
        "/comfy_img2img_lora",
        Img2ImgLoraRequest,
        "img2img_lora",
        "create_img2img_lora_task",
    ),
    ("/face_swap", FaceSwapRequest, "face_swap", "create_face_swap_task"),
    (
        "/perfect_video_insert",
        VideoInsertRequest,
        "video_insert",
        "create_video_insert_task",
    ),
    (
        "/perfect_video_edit",
        VideoEditRequest,
        "video_edit",
        "create_video_edit_task",
    ),
    (
        "/perfect_video_lora",
        VideoLoraRequest,
        "video_lora",
        "create_video_lora_task",
    ),
    ("/face_video", FaceVideoRequest, "face_video", "create_face_video_task"),
    ("/i2i_pro", I2IProRequest, "i2i_pro", "create_i2i_pro_task"),
    ("/i2i_draw", I2IDrawRequest, "i2i_draw", "create_i2i_draw_task"),
    ("/api/v1/ltx_video", LtxVideoRequest, "ltx_video", "create_ltx_video_task"),
)

TASK_STATUS_ROUTE_SPECS = (
    ("/api/v1/tasks/{task_id}", True, False, "get_task_status_v1"),
    ("/status/{task_id}", False, True, "get_task_status"),
)

TASK_RESULT_ROUTE_SPECS = (
    ("/image/{task_id}", "Image not ready", "get_task_image"),
    ("/video/{task_id}", "Video not ready", "get_task_video"),
)


def _split_task_request(request_model):
    params = request_model.dict()
    task_id = params.pop("task_id")
    priority = params.pop("priority", 0)
    return task_id, priority, params


async def _enqueue_task_from_request(
    *,
    request_model,
    task_type: TaskType,
    queue_manager: QueueManager,
) -> TaskResponse:
    task_id, priority, params = _split_task_request(request_model)
    await queue_manager.enqueue_task(task_type, params, priority, task_id)
    return TaskResponse(task_id=task_id)


async def _enqueue_configured_task(
    *,
    request_model,
    task_key: str,
    queue_manager: QueueManager,
) -> TaskResponse:
    return await _enqueue_task_from_request(
        request_model=request_model,
        task_type=SIMPLE_TASK_TYPE_MAP[task_key],
        queue_manager=queue_manager,
    )


def _register_simple_task_route(
    *,
    path: str,
    request_model_cls,
    task_key: str,
    handler_name: str,
) -> None:
    async def endpoint(
        request: request_model_cls,
        queue_manager: QueueManagerDep,
        _token: AuthTokenDep,
    ):
        return await _enqueue_configured_task(
            request_model=request,
            task_key=task_key,
            queue_manager=queue_manager,
        )

    endpoint.__name__ = handler_name
    app.post(path, response_model=TaskResponse)(endpoint)
    globals()[handler_name] = endpoint


def _register_task_status_route(
    *,
    path: str,
    include_image_url: bool,
    include_task_type: bool,
    handler_name: str,
) -> None:
    async def endpoint(task_id: str, queue_manager: QueueManagerDep):
        return await _build_task_status_response(
            task_id=task_id,
            queue_manager=queue_manager,
            include_image_url=include_image_url,
            include_task_type=include_task_type,
        )

    endpoint.__name__ = handler_name
    app.get(path, response_model=TaskStatusResponse)(endpoint)
    globals()[handler_name] = endpoint


def _register_task_result_route(
    *,
    path: str,
    ready_error_detail: str,
    handler_name: str,
) -> None:
    async def endpoint(
        task_id: str,
        queue_manager: QueueManagerDep,
        minio_client: MinioClientDep,
    ):
        return await _serve_task_result_file(
            task_id=task_id,
            ready_error_detail=ready_error_detail,
            queue_manager=queue_manager,
            minio_client=minio_client,
        )

    endpoint.__name__ = handler_name
    app.get(path)(endpoint)
    globals()[handler_name] = endpoint


def _build_result_url(result_path: str) -> str:
    protocol = "https" if settings.minio_secure else "http"
    return (
        f"{protocol}://{settings.minio_endpoint}/"
        f"{settings.minio_result_bucket}/{result_path}"
    )


def _build_task_event_channel(task_id: str) -> str:
    return f"comfy:task_events:{task_id}"


def _validate_t2i_prompt(prompt: object) -> str:
    if not prompt or not isinstance(prompt, str) or len(prompt) < 1 or len(prompt) > 512:
        raise HTTPException(
            status_code=400, detail="prompt is required and length must be 1-512"
        )
    return prompt


def _resolve_t2i_priority(request_body: dict, default_priority: int) -> int:
    return request_body.get("priority", default_priority)


def _prepare_t2i_request_payload(
    request_body: dict,
    *,
    default_priority: int,
) -> tuple[str, int, dict[str, str]]:
    prompt = _validate_t2i_prompt(request_body.get("prompt"))
    task_priority = _resolve_t2i_priority(request_body, default_priority)
    task_id = str(uuid.uuid4())
    return task_id, task_priority, {"prompt": prompt}


def _build_t2i_success_response(*, task_id: str, result_path: str) -> T2ITaskResponse:
    return T2ITaskResponse(task_id=task_id, image_url=_build_result_url(result_path))


def _build_t2i_terminal_response(
    *,
    task_id: str,
    status: str | None,
    result_path: str | None,
    error_msg: str | None,
    request_id: str,
) -> T2ITaskResponse | None:
    if status == "done":
        image_url = _build_result_url(result_path)
        logger.info(f"[{request_id}] Task {task_id} completed: {image_url}")
        return _build_t2i_success_response(task_id=task_id, result_path=result_path)
    if status == "error":
        message = error_msg or "Unknown error"
        logger.error(f"[{request_id}] Task {task_id} failed: {message}")
        raise HTTPException(status_code=500, detail=f"Task failed: {message}")
    return None


def _decode_t2i_pubsub_message(data: str | bytes) -> dict | None:
    if isinstance(data, bytes):
        data = data.decode("utf-8")
    try:
        return json.loads(data)
    except json.JSONDecodeError:
        return None


async def _wait_for_t2i_terminal_response(
    *,
    pubsub,
    task_id: str,
    request_id: str,
    timeout: int,
) -> T2ITaskResponse:
    async def listen_for_result():
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            parsed = _decode_t2i_pubsub_message(message["data"])
            if not parsed:
                continue
            response = _build_t2i_terminal_response(
                task_id=task_id,
                status=parsed.get("status"),
                result_path=parsed.get("result_path"),
                error_msg=parsed.get("error_msg"),
                request_id=request_id,
            )
            if response:
                return response

    return await asyncio.wait_for(listen_for_result(), timeout=timeout)


async def _subscribe_task_events(queue_manager: QueueManager, task_id: str):
    pubsub = queue_manager.redis.pubsub()
    channel = _build_task_event_channel(task_id)
    await pubsub.subscribe(channel)
    return pubsub, channel


async def _close_task_event_subscription(*, pubsub, channel: str) -> None:
    await pubsub.unsubscribe(channel)
    await pubsub.close()


@asynccontextmanager
async def _optional_t2i_task_subscription(
    *,
    async_mode: bool,
    queue_manager: QueueManager,
    task_id: str,
):
    if async_mode:
        yield None, None
        return

    pubsub, channel = await _subscribe_task_events(queue_manager, task_id)
    try:
        yield pubsub, channel
    finally:
        await _close_task_event_subscription(pubsub=pubsub, channel=channel)


async def _enqueue_t2i_task(
    *,
    queue_manager: QueueManager,
    task_id: str,
    params: dict,
    priority: int,
    request_id: str,
) -> None:
    try:
        await queue_manager.enqueue_task(
            TaskType.T2I_PORNMASTER_TURBO, params, priority, task_id
        )
        logger.info(f"[{request_id}] Task enqueued: {task_id} with priority {priority}")
    except Exception as e:
        logger.error(f"[{request_id}] Failed to enqueue task: {e}")
        raise HTTPException(status_code=500, detail="Internal server error") from e


async def _get_immediate_t2i_terminal_response(
    *,
    queue_manager: QueueManager,
    task_id: str,
    request_id: str,
) -> T2ITaskResponse | None:
    task_status = await queue_manager.get_task_status(task_id)
    if not task_status:
        return None
    return _build_t2i_terminal_response(
        task_id=task_id,
        status=task_status.get("status"),
        result_path=task_status.get("result_path"),
        error_msg=task_status.get("error_msg"),
        request_id=request_id,
    )


async def _wait_for_t2i_sync_result(
    *,
    pubsub,
    task_id: str,
    request_id: str,
    queue_manager: QueueManager,
    timeout: int = 60,
) -> T2ITaskResponse:
    immediate_response = await _get_immediate_t2i_terminal_response(
        queue_manager=queue_manager,
        task_id=task_id,
        request_id=request_id,
    )
    if immediate_response:
        return immediate_response

    try:
        return await _wait_for_t2i_terminal_response(
            pubsub=pubsub,
            task_id=task_id,
            request_id=request_id,
            timeout=timeout,
        )
    except asyncio.TimeoutError as e:
        logger.error(f"[{request_id}] Task {task_id} timed out")
        raise HTTPException(status_code=504, detail="Task execution timed out") from e


async def _build_task_status_response(
    *,
    task_id: str,
    queue_manager: QueueManager,
    include_image_url: bool = False,
    include_task_type: bool = False,
) -> TaskStatusResponse:
    task = await queue_manager.get_task_status(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    status = task.get("status")
    queue_pos = None
    queue_remaining = None
    if status == "pending":
        queue_pos = await queue_manager.get_queue_position(task_id)
        queue_remaining = queue_pos if queue_pos is not None else 0

    result_path = task.get("result_path")
    response_kwargs = {
        "status": status,
        "queue_pos": queue_pos,
        "queue_remaining": queue_remaining,
        "progress": float(task.get("progress", 0.0)),
        "error": task.get("error_msg"),
        "result_path": result_path,
        "cancel_requested": queue_manager._as_bool(task.get("cancel_requested")),
        "cancel_requested_at": (
            float(task["cancel_requested_at"])
            if task.get("cancel_requested_at")
            else None
        ),
    }
    if include_image_url and status == "done" and result_path:
        response_kwargs["image_url"] = _build_result_url(result_path)
    if include_task_type:
        response_kwargs["task_type"] = task.get("type")
    return TaskStatusResponse(**response_kwargs)


async def _serve_task_result_file(
    *,
    task_id: str,
    ready_error_detail: str,
    queue_manager: QueueManager,
    minio_client: Optional[Minio],
) -> FileResponse:
    task = await queue_manager.get_task_status(task_id)
    if not task or task.get("status") != "done":
        raise HTTPException(status_code=404, detail=ready_error_detail)

    result_path = task.get("result_path")
    if not result_path:
        raise HTTPException(status_code=404, detail="Result path missing")
    if not minio_client:
        raise HTTPException(status_code=500, detail="MinIO client not initialized")

    import tempfile

    try:
        logger.info(
            "Fetching %s from MinIO bucket %s",
            result_path,
            settings.minio_result_bucket,
        )
        fd, temp_path = tempfile.mkstemp()
        os.close(fd)
        minio_client.fget_object(settings.minio_result_bucket, result_path, temp_path)
        background_tasks = BackgroundTasks()
        background_tasks.add_task(os.remove, temp_path)
        return FileResponse(temp_path, background=background_tasks)
    except Exception as e:
        logger.error(f"MinIO download failed: {e}")
        raise HTTPException(status_code=404, detail="File not found in storage")


async def _build_system_workers_response(queue_manager: QueueManager) -> SystemWorkersResponse:
    workers = await queue_manager.get_all_workers()
    return SystemWorkersResponse(workers=workers, count=len(workers))


async def _build_system_status_response(queue_manager: QueueManager) -> SystemStatusResponse:
    queue_size = await queue_manager.get_queue_size()
    active_workers = await queue_manager.get_active_workers_count()

    # We now use Redis heartbeats to accurately track active workers
    comfy_online = active_workers > 0
    queue_by_type = await queue_manager.get_queue_metrics_by_type()

    return SystemStatusResponse(
        queue_size=queue_size,
        queue_by_type=queue_by_type,
        active_workers=active_workers,
        comfy_online=comfy_online,
    )


async def _cancel_task_or_404(queue_manager: QueueManager, task_id: str):
    result = await queue_manager.cancel_task(task_id)
    if not result:
        raise HTTPException(status_code=404, detail="Task not found")
    return result


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "central-api"}


for _path, _request_model_cls, _task_key, _handler_name in SIMPLE_TASK_ROUTE_SPECS:
    _register_simple_task_route(
        path=_path,
        request_model_cls=_request_model_cls,
        task_key=_task_key,
        handler_name=_handler_name,
    )


@app.post("/api/v1/workflows/t2i-pornmaster-turbo", response_model=T2ITaskResponse)
async def create_t2i_pornmaster_turbo_task(
    request: Annotated[dict, Body()],
    queue_manager: QueueManagerDep,
    _token: AuthTokenDep,
    async_mode: Annotated[bool, Query(alias="async")] = True,
    priority: Annotated[int, Query()] = 0,
):
    request_id = str(uuid.uuid4())
    logger.info(f"[{request_id}] Received T2I task request: {request}")

    try:
        task_id, task_priority, params = _prepare_t2i_request_payload(
            request,
            default_priority=priority,
        )
    except HTTPException:
        logger.error(f"[{request_id}] Invalid prompt: {request.get('prompt')}")
        raise

    async with _optional_t2i_task_subscription(
        async_mode=async_mode,
        queue_manager=queue_manager,
        task_id=task_id,
    ) as (pubsub, _channel):
        await _enqueue_t2i_task(
            queue_manager=queue_manager,
            task_id=task_id,
            params=params,
            priority=task_priority,
            request_id=request_id,
        )

        if not async_mode:
            logger.info(f"[{request_id}] Sync mode: waiting for task {task_id}")
            return await _wait_for_t2i_sync_result(
                pubsub=pubsub,
                task_id=task_id,
                request_id=request_id,
                queue_manager=queue_manager,
            )

    return T2ITaskResponse(task_id=task_id)


@app.delete("/api/tasks/{task_id}")
async def cancel_task(
    task_id: str,
    queue_manager: QueueManagerDep,
    _token: AuthTokenDep,
):
    return await _cancel_task_or_404(queue_manager, task_id)


for _path, _include_image_url, _include_task_type, _handler_name in TASK_STATUS_ROUTE_SPECS:
    _register_task_status_route(
        path=_path,
        include_image_url=_include_image_url,
        include_task_type=_include_task_type,
        handler_name=_handler_name,
    )


for _path, _ready_error_detail, _handler_name in TASK_RESULT_ROUTE_SPECS:
    _register_task_result_route(
        path=_path,
        ready_error_detail=_ready_error_detail,
        handler_name=_handler_name,
    )


@app.get("/system/workers", response_model=SystemWorkersResponse)
async def get_system_workers(queue_manager: QueueManagerDep):
    return await _build_system_workers_response(queue_manager)


@app.get("/system/status", response_model=SystemStatusResponse)
async def get_system_status(queue_manager: QueueManagerDep):
    return await _build_system_status_response(queue_manager)
