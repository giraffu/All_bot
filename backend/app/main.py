import asyncio
import logging
import os
import uuid
from contextlib import asynccontextmanager
from typing import Optional

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


def _build_result_url(result_path: str) -> str:
    protocol = "https" if settings.minio_secure else "http"
    return (
        f"{protocol}://{settings.minio_endpoint}/"
        f"{settings.minio_result_bucket}/{result_path}"
    )


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


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "central-api"}


@app.post("/comfy_img2img", response_model=TaskResponse)
async def create_img2img_task(  # vulture: ignore
    request: Img2ImgRequest,
    queue_manager: QueueManager = Depends(get_queue_manager),
    token: str = Depends(verify_token),
):
    return await _enqueue_task_from_request(
        request_model=request,
        task_type=TaskType.IMG2IMG,
        queue_manager=queue_manager,
    )


@app.post("/comfy_img2img_lora", response_model=TaskResponse)
async def create_img2img_lora_task(  # vulture: ignore
    request: Img2ImgLoraRequest,
    queue_manager: QueueManager = Depends(get_queue_manager),
    token: str = Depends(verify_token),
):
    return await _enqueue_task_from_request(
        request_model=request,
        task_type=TaskType.IMG2IMG_LORA,
        queue_manager=queue_manager,
    )


@app.post("/face_swap", response_model=TaskResponse)
async def create_face_swap_task(  # vulture: ignore
    request: FaceSwapRequest,
    queue_manager: QueueManager = Depends(get_queue_manager),
    token: str = Depends(verify_token),
):
    return await _enqueue_task_from_request(
        request_model=request,
        task_type=TaskType.FACE_SWAP,
        queue_manager=queue_manager,
    )


@app.post("/perfect_video_insert", response_model=TaskResponse)
async def create_video_insert_task(  # vulture: ignore
    request: VideoInsertRequest,
    queue_manager: QueueManager = Depends(get_queue_manager),
    token: str = Depends(verify_token),
):
    return await _enqueue_task_from_request(
        request_model=request,
        task_type=TaskType.VIDEO_INSERT,
        queue_manager=queue_manager,
    )


@app.post("/perfect_video_edit", response_model=TaskResponse)
async def create_video_edit_task(  # vulture: ignore
    request: VideoEditRequest,
    queue_manager: QueueManager = Depends(get_queue_manager),
    token: str = Depends(verify_token),
):
    return await _enqueue_task_from_request(
        request_model=request,
        task_type=TaskType.VIDEO_EDIT,
        queue_manager=queue_manager,
    )


@app.post("/perfect_video_lora", response_model=TaskResponse)
async def create_video_lora_task(  # vulture: ignore
    request: VideoLoraRequest,
    queue_manager: QueueManager = Depends(get_queue_manager),
    token: str = Depends(verify_token),
):
    # Reusing VIDEO_EDIT task type so existing workers can pick it up.
    # The lora_name param will be dynamically injected by the worker's patch_workflow.
    return await _enqueue_task_from_request(
        request_model=request,
        task_type=TaskType.VIDEO_EDIT,
        queue_manager=queue_manager,
    )


@app.post("/face_video", response_model=TaskResponse)
async def create_face_video_task(  # vulture: ignore
    request: FaceVideoRequest,
    queue_manager: QueueManager = Depends(get_queue_manager),
    token: str = Depends(verify_token),
):
    return await _enqueue_task_from_request(
        request_model=request,
        task_type=TaskType.FACE_VIDEO,
        queue_manager=queue_manager,
    )


@app.post("/i2i_pro", response_model=TaskResponse)
async def create_i2i_pro_task(
    request: I2IProRequest,
    queue_manager: QueueManager = Depends(get_queue_manager),
    token: str = Depends(verify_token),
):
    return await _enqueue_task_from_request(
        request_model=request,
        task_type=TaskType.I2I_PRO,
        queue_manager=queue_manager,
    )


@app.post("/i2i_draw", response_model=TaskResponse)
async def create_i2i_draw_task(
    request: I2IDrawRequest,
    queue_manager: QueueManager = Depends(get_queue_manager),
    token: str = Depends(verify_token),
):
    return await _enqueue_task_from_request(
        request_model=request,
        task_type=TaskType.I2I_DRAW,
        queue_manager=queue_manager,
    )


@app.post("/api/v1/ltx_video", response_model=TaskResponse)
async def create_ltx_video_task(
    request: LtxVideoRequest,
    queue_manager: QueueManager = Depends(get_queue_manager),
    token: str = Depends(verify_token),
):
    return await _enqueue_task_from_request(
        request_model=request,
        task_type=TaskType.LTX_VIDEO,
        queue_manager=queue_manager,
    )


@app.post("/api/v1/workflows/t2i-pornmaster-turbo", response_model=T2ITaskResponse)
async def create_t2i_pornmaster_turbo_task(
    request: dict = Body(...),
    async_mode: bool = Query(True, alias="async"),
    priority: int = Query(0),
    queue_manager: QueueManager = Depends(get_queue_manager),
    token: str = Depends(verify_token),
):
    request_id = str(uuid.uuid4())
    logger.info(f"[{request_id}] Received T2I task request: {request}")

    # 1. Parameter validation
    prompt = request.get("prompt")
    if (
        not prompt
        or not isinstance(prompt, str)
        or len(prompt) < 1
        or len(prompt) > 512
    ):
        logger.error(f"[{request_id}] Invalid prompt: {prompt}")
        raise HTTPException(
            status_code=400, detail="prompt is required and length must be 1-512"
        )

    # 2. Extract priority from body if present, otherwise use query param
    task_priority = request.get("priority", priority)

    # 3. Enqueue task with pre-generated ID and Pub/Sub for sync mode
    params = {"prompt": prompt}
    task_id = str(uuid.uuid4())

    if not async_mode:
        pubsub = queue_manager.redis.pubsub()
        channel = f"comfy:task_events:{task_id}"
        await pubsub.subscribe(channel)

    try:
        await queue_manager.enqueue_task(
            TaskType.T2I_PORNMASTER_TURBO, params, task_priority, task_id
        )
        logger.info(
            f"[{request_id}] Task enqueued: {task_id} with priority {task_priority}"
        )
    except Exception as e:
        logger.error(f"[{request_id}] Failed to enqueue task: {e}")
        if not async_mode:
            await pubsub.unsubscribe(channel)
            await pubsub.close()
        raise HTTPException(status_code=500, detail="Internal server error")

    # 4. Handle sync mode
    if not async_mode:
        logger.info(f"[{request_id}] Sync mode: waiting for task {task_id}")
        timeout = 60

        try:
            # Active check once to prevent race conditions
            task_status = await queue_manager.get_task_status(task_id)
            if task_status:
                status = task_status.get("status")
                if status == "done":
                    result_path = task_status.get("result_path")
                    protocol = "https" if settings.minio_secure else "http"
                    image_url = f"{protocol}://{settings.minio_endpoint}/{settings.minio_result_bucket}/{result_path}"
                    logger.info(f"[{request_id}] Task {task_id} completed: {image_url}")
                    return T2ITaskResponse(task_id=task_id, image_url=image_url)
                elif status == "error":
                    error_msg = task_status.get("error_msg", "Unknown error")
                    logger.error(f"[{request_id}] Task {task_id} failed: {error_msg}")
                    raise HTTPException(
                        status_code=500, detail=f"Task failed: {error_msg}"
                    )

            async def listen_for_result():
                async for message in pubsub.listen():
                    if message["type"] == "message":
                        data = message["data"]
                        import json

                        if isinstance(data, bytes):
                            data = data.decode("utf-8")
                        try:
                            parsed = json.loads(data)
                            status = parsed.get("status")
                            if status == "done":
                                result_path = parsed.get("result_path")
                                protocol = "https" if settings.minio_secure else "http"
                                image_url = f"{protocol}://{settings.minio_endpoint}/{settings.minio_result_bucket}/{result_path}"
                                return T2ITaskResponse(
                                    task_id=task_id, image_url=image_url
                                )
                            elif status == "error":
                                error_msg = parsed.get("error_msg", "Unknown error")
                                raise HTTPException(
                                    status_code=500, detail=f"Task failed: {error_msg}"
                                )
                        except json.JSONDecodeError:
                            pass

            result = await asyncio.wait_for(listen_for_result(), timeout=timeout)
            return result
        except asyncio.TimeoutError:
            logger.error(f"[{request_id}] Task {task_id} timed out")
            raise HTTPException(status_code=504, detail="Task execution timed out")
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()

    return T2ITaskResponse(task_id=task_id)


@app.delete("/api/tasks/{task_id}")
async def cancel_task(
    task_id: str,
    queue_manager: QueueManager = Depends(get_queue_manager),
    token: str = Depends(verify_token),
):
    result = await queue_manager.cancel_task(task_id)
    if not result:
        raise HTTPException(status_code=404, detail="Task not found")
    return result


@app.get("/api/v1/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task_status_v1(
    task_id: str, queue_manager: QueueManager = Depends(get_queue_manager)
):
    return await _build_task_status_response(
        task_id=task_id,
        queue_manager=queue_manager,
        include_image_url=True,
    )


@app.get("/status/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(
    task_id: str, queue_manager: QueueManager = Depends(get_queue_manager)
):
    return await _build_task_status_response(
        task_id=task_id,
        queue_manager=queue_manager,
        include_task_type=True,
    )


@app.get("/image/{task_id}")
async def get_task_image(
    task_id: str,
    queue_manager: QueueManager = Depends(get_queue_manager),
    minio_client: Optional[Minio] = Depends(get_minio_client),
):
    return await _serve_task_result_file(
        task_id=task_id,
        ready_error_detail="Image not ready",
        queue_manager=queue_manager,
        minio_client=minio_client,
    )


@app.get("/video/{task_id}")
async def get_task_video(
    task_id: str,
    queue_manager: QueueManager = Depends(get_queue_manager),
    minio_client: Optional[Minio] = Depends(get_minio_client),
):
    return await _serve_task_result_file(
        task_id=task_id,
        ready_error_detail="Video not ready",
        queue_manager=queue_manager,
        minio_client=minio_client,
    )


@app.get("/system/workers", response_model=SystemWorkersResponse)
async def get_system_workers(queue_manager: QueueManager = Depends(get_queue_manager)):
    workers = await queue_manager.get_all_workers()
    return SystemWorkersResponse(workers=workers, count=len(workers))


@app.get("/system/status", response_model=SystemStatusResponse)
async def get_system_status(queue_manager: QueueManager = Depends(get_queue_manager)):
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
