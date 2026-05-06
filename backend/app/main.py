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
            secure=settings.minio_secure
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

@app.post("/comfy_img2img", response_model=TaskResponse)
async def create_img2img_task(  # vulture: ignore
    request: Img2ImgRequest,
    queue_manager: QueueManager = Depends(get_queue_manager),
    token: str = Depends(verify_token)
):
    params = request.dict()
    task_id = params.pop("task_id")
    priority = params.pop("priority", 0)
    await queue_manager.enqueue_task(TaskType.IMG2IMG, params, priority, task_id)
    return TaskResponse(task_id=task_id)

@app.post("/comfy_img2img_lora", response_model=TaskResponse)
async def create_img2img_lora_task(  # vulture: ignore
    request: Img2ImgLoraRequest,
    queue_manager: QueueManager = Depends(get_queue_manager),
    token: str = Depends(verify_token)
):
    params = request.dict()
    task_id = params.pop("task_id")
    priority = params.pop("priority", 0)
    await queue_manager.enqueue_task(TaskType.IMG2IMG_LORA, params, priority, task_id)
    return TaskResponse(task_id=task_id)

@app.post("/face_swap", response_model=TaskResponse)
async def create_face_swap_task(  # vulture: ignore
    request: FaceSwapRequest,
    queue_manager: QueueManager = Depends(get_queue_manager),
    token: str = Depends(verify_token)
):
    params = request.dict()
    task_id = params.pop("task_id")
    priority = params.pop("priority", 0)
    await queue_manager.enqueue_task(TaskType.FACE_SWAP, params, priority, task_id)
    return TaskResponse(task_id=task_id)

@app.post("/perfect_video_insert", response_model=TaskResponse)
async def create_video_insert_task(  # vulture: ignore
    request: VideoInsertRequest,
    queue_manager: QueueManager = Depends(get_queue_manager),
    token: str = Depends(verify_token)
):
    params = request.dict()
    task_id = params.pop("task_id")
    priority = params.pop("priority", 0)
    await queue_manager.enqueue_task(TaskType.VIDEO_INSERT, params, priority, task_id)
    return TaskResponse(task_id=task_id)

@app.post("/perfect_video_edit", response_model=TaskResponse)
async def create_video_edit_task(  # vulture: ignore
    request: VideoEditRequest,
    queue_manager: QueueManager = Depends(get_queue_manager),
    token: str = Depends(verify_token)
):
    params = request.dict()
    task_id = params.pop("task_id")
    priority = params.pop("priority", 0)
    await queue_manager.enqueue_task(TaskType.VIDEO_EDIT, params, priority, task_id)
    return TaskResponse(task_id=task_id)

@app.post("/perfect_video_lora", response_model=TaskResponse)
async def create_video_lora_task(  # vulture: ignore
    request: VideoLoraRequest,
    queue_manager: QueueManager = Depends(get_queue_manager),
    token: str = Depends(verify_token)
):
    params = request.dict()
    task_id = params.pop("task_id")
    priority = params.pop("priority", 0)
    # Reusing VIDEO_EDIT task type so existing workers can pick it up. 
    # The lora_name param will be dynamically injected by the worker's patch_workflow.
    await queue_manager.enqueue_task(TaskType.VIDEO_EDIT, params, priority, task_id)
    return TaskResponse(task_id=task_id)

@app.post("/face_video", response_model=TaskResponse)
async def create_face_video_task(  # vulture: ignore
    request: FaceVideoRequest,
    queue_manager: QueueManager = Depends(get_queue_manager),
    token: str = Depends(verify_token)
):
    params = request.dict()
    task_id = params.pop("task_id")
    priority = params.pop("priority", 0)
    await queue_manager.enqueue_task(TaskType.FACE_VIDEO, params, priority, task_id)
    return TaskResponse(task_id=task_id)

@app.post("/i2i_pro", response_model=TaskResponse)
async def create_i2i_pro_task(
    request: I2IProRequest,
    queue_manager: QueueManager = Depends(get_queue_manager),
    token: str = Depends(verify_token)
):
    params = request.dict()
    task_id = params.pop("task_id")
    priority = params.pop("priority", 0)
    await queue_manager.enqueue_task(TaskType.I2I_PRO, params, priority, task_id)
    return TaskResponse(task_id=task_id)

@app.post("/api/v1/ltx_video", response_model=TaskResponse)
async def create_ltx_video_task(
    request: LtxVideoRequest,
    queue_manager: QueueManager = Depends(get_queue_manager),
    token: str = Depends(verify_token)
):
    params = request.dict()
    task_id = params.pop("task_id")
    priority = params.pop("priority", 0)
    await queue_manager.enqueue_task(TaskType.LTX_VIDEO, params, priority, task_id)
    return TaskResponse(task_id=task_id)

@app.post("/api/v1/workflows/t2i-pornmaster-turbo", response_model=T2ITaskResponse)
async def create_t2i_pornmaster_turbo_task(
    request: dict = Body(...),
    async_mode: bool = Query(True, alias="async"),
    priority: int = Query(0),
    queue_manager: QueueManager = Depends(get_queue_manager),
    token: str = Depends(verify_token)
):
    request_id = str(uuid.uuid4())
    logger.info(f"[{request_id}] Received T2I task request: {request}")
    
    # 1. Parameter validation
    prompt = request.get("prompt")
    if not prompt or not isinstance(prompt, str) or len(prompt) < 1 or len(prompt) > 512:
        logger.error(f"[{request_id}] Invalid prompt: {prompt}")
        raise HTTPException(status_code=400, detail="prompt is required and length must be 1-512")
    
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
        await queue_manager.enqueue_task(TaskType.T2I_PORNMASTER_TURBO, params, task_priority, task_id)
        logger.info(f"[{request_id}] Task enqueued: {task_id} with priority {task_priority}")
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
                    raise HTTPException(status_code=500, detail=f"Task failed: {error_msg}")
            
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
                                return T2ITaskResponse(task_id=task_id, image_url=image_url)
                            elif status == "error":
                                error_msg = parsed.get("error_msg", "Unknown error")
                                raise HTTPException(status_code=500, detail=f"Task failed: {error_msg}")
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
    token: str = Depends(verify_token)
):
    success = await queue_manager.cancel_task(task_id)
    if not success:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"message": "Task cancelled successfully", "task_id": task_id}

@app.get("/api/v1/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task_status_v1(
    task_id: str,
    queue_manager: QueueManager = Depends(get_queue_manager)
):
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
    image_url = None
    if status == "done" and result_path:
        protocol = "https" if settings.minio_secure else "http"
        image_url = f"{protocol}://{settings.minio_endpoint}/{settings.minio_result_bucket}/{result_path}"
        
    return TaskStatusResponse(
        status=status,
        queue_pos=queue_pos,
        queue_remaining=queue_remaining,
        progress=float(task.get("progress", 0.0)),
        error=task.get("error_msg"),
        result_path=result_path,
        image_url=image_url
    )

@app.get("/status/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(
    task_id: str,
    queue_manager: QueueManager = Depends(get_queue_manager)
):
    task = await queue_manager.get_task_status(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    status = task.get("status")
    queue_pos = None
    queue_remaining = None
    
    if status == "pending":
        queue_pos = await queue_manager.get_queue_position(task_id)
        # Usually rank 0 is the head.
        queue_remaining = queue_pos if queue_pos is not None else 0
        
    return TaskStatusResponse(
        status=status,
        queue_pos=queue_pos,
        queue_remaining=queue_remaining,
        progress=float(task.get("progress", 0.0)),
        error=task.get("error_msg"),
        result_path=task.get("result_path"),
        task_type=task.get("type")
    )

@app.get("/image/{task_id}")
async def get_task_image(
    task_id: str,
    queue_manager: QueueManager = Depends(get_queue_manager),
    minio_client: Optional[Minio] = Depends(get_minio_client)
):
    task = await queue_manager.get_task_status(task_id)
    if not task or task.get("status") != "done":
        raise HTTPException(status_code=404, detail="Image not ready")
        
    result_path = task.get("result_path")
    if not result_path:
        raise HTTPException(status_code=404, detail="Result path missing")
        
    # We no longer read from local disk, everything is served directly via MinIO URL or frontend handles MinIO URLs.
    # However, to preserve API compatibility, we will fetch from MinIO and return.
    import tempfile
    
    if not minio_client:
        raise HTTPException(status_code=500, detail="MinIO client not initialized")
        
    try:
        logger.info(f"Fetching {result_path} from MinIO bucket {settings.minio_result_bucket}")
        # Create a temporary file to send back
        fd, temp_path = tempfile.mkstemp()
        os.close(fd)
        
        minio_client.fget_object(
            settings.minio_result_bucket,
            result_path,
            temp_path
        )
        return FileResponse(temp_path, background=BackgroundTasks().add_task(os.remove, temp_path))
    except Exception as e:
        logger.error(f"MinIO download failed: {e}")
        raise HTTPException(status_code=404, detail="File not found in storage")

@app.get("/video/{task_id}")
async def get_task_video(
    task_id: str,
    queue_manager: QueueManager = Depends(get_queue_manager),
    minio_client: Optional[Minio] = Depends(get_minio_client)
):
    task = await queue_manager.get_task_status(task_id)
    if not task or task.get("status") != "done":
        raise HTTPException(status_code=404, detail="Video not ready")
        
    result_path = task.get("result_path")
    if not result_path:
        raise HTTPException(status_code=404, detail="Result path missing")
        
    import tempfile
    
    if not minio_client:
        raise HTTPException(status_code=500, detail="MinIO client not initialized")
        
    try:
        logger.info(f"Fetching {result_path} from MinIO bucket {settings.minio_result_bucket}")
        # Create a temporary file to send back
        fd, temp_path = tempfile.mkstemp()
        os.close(fd)
        
        minio_client.fget_object(
            settings.minio_result_bucket,
            result_path,
            temp_path
        )
        return FileResponse(temp_path, background=BackgroundTasks().add_task(os.remove, temp_path))
    except Exception as e:
        logger.error(f"MinIO download failed: {e}")
        raise HTTPException(status_code=404, detail="File not found in storage")

@app.get("/system/workers", response_model=SystemWorkersResponse)
async def get_system_workers(
    queue_manager: QueueManager = Depends(get_queue_manager)
):
    workers = await queue_manager.get_all_workers()
    return SystemWorkersResponse(
        workers=workers,
        count=len(workers)
    )

@app.get("/system/status", response_model=SystemStatusResponse)
async def get_system_status(
    queue_manager: QueueManager = Depends(get_queue_manager)
):
    queue_size = await queue_manager.get_queue_size()
    active_workers = await queue_manager.get_active_workers_count()
    
    # We now use Redis heartbeats to accurately track active workers
    comfy_online = active_workers > 0
    
    queue_by_type = await queue_manager.get_queue_metrics_by_type()
    
    return SystemStatusResponse(
        queue_size=queue_size,
        queue_by_type=queue_by_type,
        active_workers=active_workers,
        comfy_online=comfy_online
    )
