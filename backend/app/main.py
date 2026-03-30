import asyncio
import logging
import os
import shutil
import uuid
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException, BackgroundTasks, Query, Body
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.config import settings
from app.models import TaskResponse, TaskStatusResponse, SystemStatusResponse, TaskType, T2ITaskResponse
from app.queue_manager import QueueManager
from app.routers import agent
from redis.asyncio import Redis
from minio import Minio

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="ComfyUI Middleware")
app.include_router(agent.router)
security = HTTPBearer()

# MinIO Client
minio_client: Optional[Minio] = None

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

@app.on_event("startup")
async def startup_event():
    global minio_client
    
    # Init MinIO
    try:
        minio_client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure
        )
        logger.info(f"MinIO client initialized: {settings.minio_endpoint}")
    except Exception as e:
        logger.error(f"Failed to init MinIO: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    pass

async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if credentials.credentials != settings.auth_token:
        raise HTTPException(status_code=401, detail="Invalid token")
    return credentials.credentials

async def save_upload_file(upload_file: UploadFile) -> str:
    filename = f"{uuid.uuid4()}_{upload_file.filename}"
    
    # Read into memory
    content = await upload_file.read()
        
    # Upload to MinIO (for new Agent architecture)
    if minio_client:
        try:
            import io
            # Make sure bucket exists or just put object
            minio_client.put_object(
                settings.minio_input_bucket,
                filename,
                io.BytesIO(content),
                len(content)
            )
            logger.info(f"Uploaded {filename} to MinIO input bucket")
        except Exception as e:
            logger.error(f"Failed to upload {filename} to MinIO: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to save uploaded file to storage: {e}")
    else:
        logger.error("MinIO client is not initialized. Cannot save upload file.")
        raise HTTPException(status_code=500, detail="Storage service is unavailable.")
            
    # Reset file pointer if someone else needs it (though not used after this)
    await upload_file.seek(0)
    
    return filename

@app.post("/comfy_img2img", response_model=TaskResponse)
async def create_img2img_task(
    image: UploadFile = File(...),
    prompt: str = Form(...),
    priority: int = Form(0),
    queue_manager: QueueManager = Depends(get_queue_manager),
    token: str = Depends(verify_token)
):
    filename = await save_upload_file(image)
    
    params = {
        "image": filename,
        "prompt": prompt
    }
    
    task_id = await queue_manager.enqueue_task(TaskType.IMG2IMG, params, priority)
    return TaskResponse(task_id=task_id)

@app.post("/face_swap", response_model=TaskResponse)
async def create_face_swap_task(
    face_image: UploadFile = File(...),
    body_image: UploadFile = File(...),
    priority: int = Form(0),
    queue_manager: QueueManager = Depends(get_queue_manager),
    token: str = Depends(verify_token)
):
    face_filename = await save_upload_file(face_image)
    body_filename = await save_upload_file(body_image)
    
    params = {
        "face_image": face_filename,
        "body_image": body_filename
    }
    
    task_id = await queue_manager.enqueue_task(TaskType.FACE_SWAP, params, priority)
    return TaskResponse(task_id=task_id)

@app.post("/perfect_video_insert", response_model=TaskResponse)
async def create_video_insert_task(
    image: UploadFile = File(...),
    prompt: str = Form(...),
    width: int = Form(512),
    height: int = Form(512),
    length: int = Form(81),
    priority: int = Form(0),
    queue_manager: QueueManager = Depends(get_queue_manager),
    token: str = Depends(verify_token)
):
    image_filename = await save_upload_file(image)
    
    params = {
        "image": image_filename,
        "prompt": prompt,
        "width": width,
        "height": height,
        "length": length
    }
    
    task_id = await queue_manager.enqueue_task(TaskType.VIDEO_INSERT, params, priority)
    return TaskResponse(task_id=task_id)

@app.post("/perfect_video_edit", response_model=TaskResponse)
async def create_video_edit_task(
    image: UploadFile = File(...),
    prompt: str = Form(...),
    width: int = Form(512),
    height: int = Form(512),
    length: int = Form(81),
    priority: int = Form(0),
    queue_manager: QueueManager = Depends(get_queue_manager),
    token: str = Depends(verify_token)
):
    image_filename = await save_upload_file(image)
    
    params = {
        "image": image_filename,
        "prompt": prompt,
        "width": width,
        "height": height,
        "length": length
    }
    
    task_id = await queue_manager.enqueue_task(TaskType.VIDEO_EDIT, params, priority)
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
    
    # 3. Enqueue task
    params = {"prompt": prompt}
    try:
        task_id = await queue_manager.enqueue_task(TaskType.T2I_PORNMASTER_TURBO, params, task_priority)
        logger.info(f"[{request_id}] Task enqueued: {task_id} with priority {task_priority}")
    except Exception as e:
        logger.error(f"[{request_id}] Failed to enqueue task: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    
    # 3. Handle sync mode
    if not async_mode:
        logger.info(f"[{request_id}] Sync mode: waiting for task {task_id}")
        timeout = 60
        start_time = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start_time < timeout:
            task_status = await queue_manager.get_task_status(task_id)
            if not task_status:
                logger.error(f"[{request_id}] Task {task_id} status not found")
                raise HTTPException(status_code=500, detail="Task status not found")
            
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
            
            await asyncio.sleep(1)
        
        logger.error(f"[{request_id}] Task {task_id} timed out")
        raise HTTPException(status_code=504, detail="Task execution timed out")
    
    return T2ITaskResponse(task_id=task_id)

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
        result_path=result_path
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
        result_path=task.get("result_path")
    )

@app.get("/image/{task_id}")
async def get_task_image(
    task_id: str,
    queue_manager: QueueManager = Depends(get_queue_manager)
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
    queue_manager: QueueManager = Depends(get_queue_manager)
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
