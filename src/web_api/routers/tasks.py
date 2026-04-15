import json
import logging
import asyncio
import httpx
from typing import AsyncGenerator
from fastapi import APIRouter, Depends, HTTPException, status, Request, BackgroundTasks
from sse_starlette.sse import EventSourceResponse

from src.database.models import User
from src.web_api.dependencies import get_current_user
from src.web_api.schemas.task_schema import TaskGenerateRequest, TaskGenerateResponse
from src.core.task_core import core_submit_generation_task, core_submit_face_video
from src.core.billing_core import check_concurrency_lock, release_concurrency_lock, check_and_deduct_credits, refund_credits, get_user_priority_and_identity
from src.services.redis_client import redis_client
from src.services.storage import storage
from src.services.task_registry import TaskRegistry
from src.services.image_service import image_service
from src.quota import QuotaManager

router = APIRouter()
logger = logging.getLogger(__name__)
quota_manager = QuotaManager()

from src.utils import load_prompts
from src.constants import TASK_COSTS

COST_MAP = {
    "face_swap": 3,
    "face_video": 20,
    "txt2img": 2,
    "i2i_pro": 5
}

from src.logger import UserLogger

async def monitor_task_and_release_lock(
    task_id: str, 
    internal_user_id: int, 
    username: str,
    registry_task_id: str, 
    is_video: bool = False,
    task_type: str = "",
    prompt: str = "",
    input_images: list = None
):
    """
    Background task to monitor progress and release concurrency lock.
    """
    if input_images is None:
        input_images = []
        
    final_status = None
    result_path = None
    try:
        async for progress in image_service.monitor_progress(task_id, is_video):
            if progress.get("status") in ["done", "error", "cancelled", "success", "failed"]:
                final_status = progress.get("status")
                result_path = progress.get("result_path")
                break
    except Exception as e:
        logger.error(f"Background monitoring error for task {task_id}: {e}")
    finally:
        # Save to History if successful
        if final_status == "done" and result_path:
            try:
                user_logger = UserLogger(internal_user_id, username)
                await user_logger.log_task(prompt, input_images, result_path, task_id=task_id, type=task_type)
            except Exception as log_err:
                logger.error(f"Failed to log task history for {task_id}: {log_err}")
                
        await release_concurrency_lock(internal_user_id)
        if registry_task_id:
            await TaskRegistry.remove_task(registry_task_id)

@router.post("/generate", response_model=TaskGenerateResponse)
async def create_generation_task(
    req: TaskGenerateRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user)
):
    """
    Submit a generation task (image/video).
    """
    video_types = ["doggy_style", "perfect_video_insert", "blowjob", "undress_tongue", "closeup_blowjob", "custom_video", "face_video", "video_lora"]
    is_video_task = req.task_type in video_types
    cost = TASK_COSTS.get(req.task_type, COST_MAP.get(req.task_type, 6 if is_video_task else 2))
    
    # 1. Check concurrency
    can_run, lock_err = await check_concurrency_lock(current_user.id)
    if not can_run:
        raise HTTPException(status_code=429, detail=lock_err)
        
    try:
        # 2. Deduct credits
        success, billing_err = await check_and_deduct_credits(current_user.id, cost, req.task_type, current_user.username)
        if not success:
            await release_concurrency_lock(current_user.id)
            raise HTTPException(status_code=402, detail=billing_err)
            
        # 3. Get Priority
        priority, _, _ = await get_user_priority_and_identity(current_user.id)
        # Allow client to override priority if it's lower (for testing), but bound by max calculated priority
        final_priority = min(req.priority + priority, 100) 
        
        task_id = None
        
        # 3. Load prompts if not provided
        prompts_config = load_prompts()
        
        # If client provided prompt in inputs, use it
        if "prompt" in req.inputs and req.inputs["prompt"]:
            req.prompt = req.inputs["prompt"]
            
        if not req.prompt:
            req.prompt = prompts_config.get(req.task_type, req.task_type)
        if not req.negative_prompt:
            req.negative_prompt = prompts_config.get("negative_prompt", "")

        # 4. Dispatch based on task_type
        saved_inputs = []
        if req.task_type == "face_swap":
            face_img = req.inputs.get("face_image")
            body_img = req.inputs.get("target_image")
            if not face_img or not body_img:
                raise ValueError("face_image and target_image are required for face_swap")
                
            success, msg, task_id, saved_inputs, registry_task_id = await core_submit_generation_task(
                internal_user_id=current_user.id,
                username=current_user.username,
                prompt=req.prompt,
                images=[body_img, face_img], # FSM order: body first, face second
                is_video=False,
                task_type="face_swap",
                cost=cost,
                priority=final_priority,
                negative_prompt=req.negative_prompt
            )
        elif req.task_type == "face_video":
            face_img = req.inputs.get("face_image")
            video_path = req.inputs.get("target_video")
            resolution = req.inputs.get("resolution", 512)
            duration = req.inputs.get("duration", 5)
            
            success, msg, task_id, saved_face_img, saved_vid, registry_task_id = await core_submit_face_video(
                internal_user_id=current_user.id,
                username=current_user.username,
                face_image_path=face_img,
                video_path=video_path,
                resolution=resolution,
                duration=duration,
                cost=cost,
                mode="MODE_FACE_VIDEO_STEP2",
                priority=final_priority
            )
            if success:
                saved_inputs = [saved_face_img, saved_vid]
        else:
            # Generic t2i / i2i / video
            images = req.inputs.get("images", [])
            lora_name = req.inputs.get("lora_name")
            resolution = req.inputs.get("resolution", 512)
            duration = req.inputs.get("duration", 5)
            
            success, msg, task_id, saved_inputs, registry_task_id = await core_submit_generation_task(
                internal_user_id=current_user.id,
                username=current_user.username,
                prompt=req.prompt,
                images=images,
                is_video=is_video_task,
                task_type=req.task_type,
                cost=cost,
                priority=final_priority,
                negative_prompt=req.negative_prompt,
                lora_name=lora_name,
                resolution=resolution,
                duration=duration
            )
            
        if not success or not task_id:
            # Refund
            await refund_credits(current_user.id, cost, f"refund_{req.task_type}", current_user.username)
            raise ValueError(msg)
            
        # Success
        log_prompt = req.prompt
        if req.task_type == "video_lora" and req.inputs.get("lora_name"):
            log_prompt = f"[模型: {req.inputs.get('lora_name')}] {req.prompt}"

        background_tasks.add_task(
            monitor_task_and_release_lock, 
            task_id, 
            current_user.id, 
            current_user.username,
            registry_task_id, 
            is_video_task,
            req.task_type,
            log_prompt,
            saved_inputs
        )
        
        balance = await quota_manager.get_credits(current_user.id)
        return TaskGenerateResponse(
            task_id=task_id,
            status="pending",
            message="Task submitted successfully",
            cost=cost,
            balance_remaining=balance
        )
        
    except ValueError as ve:
        await release_concurrency_lock(current_user.id)
        logger.error(f"Task value error: {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        await release_concurrency_lock(current_user.id)
        logger.error(f"Task submission error: {e}", exc_info=True)
        # Refund on hard failure
        await refund_credits(current_user.id, cost, f"refund_error_{req.task_type}", current_user.username)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/{task_id}/stream")
async def task_status_stream(task_id: str, current_user: User = Depends(get_current_user)):
    """
    SSE Endpoint for real-time task progress tracking.
    Listens to Redis Pub/Sub channel: comfy:task_events:{task_id}
    Also periodically sends queue position while pending.
    """
    import httpx
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
                        result_path = initial_status.get("result_path")
                        if result_path:
                            presigned_url = storage.get_presigned_url(result_path, expires_hours=24, bucket="comfyui-temp")
                            initial_status["result"] = presigned_url if presigned_url else result_path
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
                        status = parsed.get("status")
                        
                        # Map backend status to frontend expected status
                        if status == "done":
                            parsed["status"] = "success"
                            result_path = parsed.get("result_path")
                            if result_path:
                                presigned_url = storage.get_presigned_url(result_path, expires_hours=24, bucket="comfyui-temp")
                                parsed["result"] = presigned_url if presigned_url else result_path
                        elif status == "error":
                            parsed["status"] = "failed"
                            parsed["error"] = parsed.get("error_msg")
                            
                        # Yield the mapped data
                        yield {
                            "event": "progress",
                            "data": json.dumps(parsed)
                        }
                        
                        if status == "running":
                            is_running = True
                        elif status in ["done", "error", "cancelled"]:
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
                                    result_path = status_data.get("result_path")
                                    if result_path:
                                        presigned_url = storage.get_presigned_url(result_path, expires_hours=24, bucket="comfyui-temp")
                                        status_data["result"] = presigned_url if presigned_url else result_path
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
