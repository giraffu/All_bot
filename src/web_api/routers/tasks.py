import json
import logging
import asyncio
import httpx
from typing import AsyncGenerator
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sse_starlette.sse import EventSourceResponse

from src.database.models import User
from src.web_api.dependencies import get_current_user
from src.web_api.schemas.task_schema import TaskGenerateRequest, TaskGenerateResponse
from src.core.task_core import process_and_submit_task, CoreDomainError, InsufficientCreditsError, ConcurrencyLimitError
from src.services.redis_client import redis_client
from src.services.storage import storage
from src.quota import QuotaManager

router = APIRouter()
logger = logging.getLogger(__name__)
quota_manager = QuotaManager()

@router.post("/generate", response_model=TaskGenerateResponse)
async def create_generation_task(
    req: TaskGenerateRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Submit a generation task (image/video).
    """
    try:
        is_template = getattr(req, 'is_template', False)
        
        # Merge prompt from request into inputs if it exists, so core layer can use it
        if req.prompt:
            req.inputs["prompt"] = req.prompt
            
        import uuid
        task_id = str(uuid.uuid4())
        
        from asgi_correlation_id import correlation_id
        correlation_id.set(task_id)
        
        result = await process_and_submit_task(
            user_id=current_user.id,
            username=current_user.username,
            task_type=req.task_type,
            inputs=req.inputs,
            task_id=task_id,
            base_priority=req.priority,
            is_template=is_template
        )
        
        balance = await quota_manager.get_credits(current_user.id)
        return TaskGenerateResponse(
            task_id=result["task_id"],
            status="pending",
            message="Task submitted successfully",
            cost=result["cost"],
            balance_remaining=balance
        )
    except ConcurrencyLimitError as e:
        raise HTTPException(status_code=429, detail=str(e))
    except InsufficientCreditsError as e:
        raise HTTPException(status_code=402, detail=str(e))
    except CoreDomainError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Task submission error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/{task_id}/stream")
async def task_status_stream(task_id: str, current_user: User = Depends(get_current_user)):
    """
    SSE Endpoint for real-time task progress tracking.
    Listens to Redis Pub/Sub channel: comfy:task_events:{task_id}
    Also periodically sends queue position while pending.
    """
    from config import API_BASE

    async def get_task_status_full():
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{API_BASE}/status/{task_id}", timeout=2.0)
                if resp.status_code == 200:
                    return resp.json()
        except Exception as e:
            logger.error(f"Error getting status for {task_id}: {e}")
        return None

    async def event_generator():
        pubsub = redis_client.redis.pubsub()
        channel = f"comfy:task_events:{task_id}"
        await pubsub.subscribe(channel)
        
        try:
            # Initial connection message
            yield {
                "event": "connected",
                "data": json.dumps({"status": "listening", "task_id": task_id})
            }
            
            # Fetch initial status to avoid missing early completion/error events
            initial_status = await get_task_status_full()
            is_running = False
            
            if initial_status:
                status_val = initial_status.get("status")
                if status_val == "running":
                    is_running = True
                elif status_val in ["done", "error", "cancelled"]:
                    # Map backend status to frontend expected status
                    if status_val == "done":
                        initial_status["status"] = "success"
                        task_type = initial_status.get("task_type", "edit")
                        is_video = task_type in ["face_video", "txt2video", "video_lora", "custom_video", "perfect_video_insert", "doggy_style", "blowjob", "undress_tongue", "closeup_blowjob", "ltx_video"]
                        ext = "mp4" if is_video else "png"
                        
                        from src.database.core import AsyncSessionLocal
                        from src.database.models import History
                        from sqlalchemy import select
                        
                        final_result_path = f"{current_user.id}/output_images/{task_id}.{ext}"
                        for _ in range(10):
                            async with AsyncSessionLocal() as db:
                                hist = (await db.execute(select(History).where(History.task_id == task_id))).scalars().first()
                                if hist and hist.output_file and hist.output_file.startswith(str(current_user.id)):
                                    final_result_path = hist.output_file
                                    break
                            await asyncio.sleep(0.5)
                            
                        presigned_url = storage.get_presigned_url(final_result_path, expires_hours=24, bucket="bot-data")
                        initial_status["result"] = presigned_url if presigned_url else final_result_path
                    elif status_val == "error":
                        initial_status["status"] = "failed"
                        initial_status["error"] = initial_status.get("error_msg")
                        
                    yield {
                        "event": "progress",
                        "data": json.dumps(initial_status)
                    }
                    return  # End stream immediately
                    
            last_queue_check = 0
            
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message:
                    data = message["data"]
                    if isinstance(data, bytes):
                        data = data.decode("utf-8")
                        
                    # Parse to see if finished or running
                    try:
                        parsed = json.loads(data)
                        task_status = parsed.get("status")
                        
                        # Map backend status to frontend expected status
                        if task_status == "done":
                            parsed["status"] = "success"
                            task_type = parsed.get("task_type", "edit")
                            is_video = task_type in ["face_video", "txt2video", "video_lora", "custom_video", "perfect_video_insert", "doggy_style", "blowjob", "undress_tongue", "closeup_blowjob", "ltx_video"]
                            ext = "mp4" if is_video else "png"
                            
                            # Give task_service.py time to move the file from comfyui-temp to bot-data
                            from src.database.core import AsyncSessionLocal
                            from src.database.models import History
                            from sqlalchemy import select
                            
                            final_result_path = f"{current_user.id}/output_images/{task_id}.{ext}"
                            for _ in range(10):
                                async with AsyncSessionLocal() as db:
                                    hist = (await db.execute(select(History).where(History.task_id == task_id))).scalars().first()
                                    if hist and hist.output_file and hist.output_file.startswith(str(current_user.id)):
                                        final_result_path = hist.output_file
                                        break
                                await asyncio.sleep(0.5)
                                
                            presigned_url = storage.get_presigned_url(final_result_path, expires_hours=24, bucket="bot-data")
                            parsed["result"] = presigned_url if presigned_url else final_result_path
                        elif task_status == "error":
                            parsed["status"] = "failed"
                            parsed["error"] = parsed.get("error_msg")
                            
                        # Yield the mapped data
                        yield {
                            "event": "progress",
                            "data": json.dumps(parsed)
                        }
                        
                        if task_status == "running":
                            is_running = True
                        elif task_status in ["done", "error", "cancelled"]:
                            # End stream gracefully
                            break
                    except json.JSONDecodeError:
                        yield {
                            "event": "progress",
                            "data": data
                        }
                
                # Periodically send queue position if not running yet
                if not is_running:
                    current_time = asyncio.get_event_loop().time()
                    if current_time - last_queue_check > 5.0:  # Check every 5 seconds
                        status_data = await get_task_status_full()
                        if status_data:
                            status_val = status_data.get("status")
                            # If the task actually started or finished but we missed the pubsub message
                            if status_val == "running":
                                is_running = True
                            elif status_val in ["done", "error", "cancelled"]:
                                if status_val == "done":
                                    status_data["status"] = "success"
                                    task_type = status_data.get("task_type", "edit")
                                    is_video = task_type in ["face_video", "txt2video", "video_lora", "custom_video", "perfect_video_insert", "doggy_style", "blowjob", "undress_tongue", "closeup_blowjob", "ltx_video"]
                                    ext = "mp4" if is_video else "png"
                                    
                                    from src.database.core import AsyncSessionLocal
                                    from src.database.models import History
                                    from sqlalchemy import select
                                    
                                    final_result_path = f"{current_user.id}/output_images/{task_id}.{ext}"
                                    for _ in range(10):
                                        async with AsyncSessionLocal() as db:
                                            hist = (await db.execute(select(History).where(History.task_id == task_id))).scalars().first()
                                            if hist and hist.output_file and hist.output_file.startswith(str(current_user.id)):
                                                final_result_path = hist.output_file
                                                break
                                        await asyncio.sleep(0.5)
                                        
                                    presigned_url = storage.get_presigned_url(final_result_path, expires_hours=24, bucket="bot-data")
                                    status_data["result"] = presigned_url if presigned_url else final_result_path
                                elif status_val == "error":
                                    status_data["status"] = "failed"
                                    status_data["error"] = status_data.get("error_msg")
                                yield {
                                    "event": "progress",
                                    "data": json.dumps(status_data)
                                }
                                break
                                
                            queue_pos = status_data.get("queue_pos")
                            if queue_pos is not None:
                                yield {
                                    "event": "progress",
                                    "data": json.dumps({
                                        "status": "pending",
                                        "queue_pos": queue_pos
                                    })
                                }
                        last_queue_check = current_time
                
                # Check if client disconnected
                await asyncio.sleep(0.5)
                
        except asyncio.CancelledError:
            logger.info(f"SSE client disconnected for task {task_id}")
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()

    return EventSourceResponse(event_generator())
