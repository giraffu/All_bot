from typing import Tuple, Optional, List
import logging

from src.services.image_service import image_service
from src.services.task_registry import TaskRegistry
from src.logger import UserLogger
from config import MINIO_BUCKET

logger = logging.getLogger(__name__)

async def _process_input_path(user_logger: UserLogger, path: str) -> str:
    if not path:
        return ""
    if path.startswith("template:"):
        return path
    if path.startswith(f"{MINIO_BUCKET}/"):
        return path.replace(f"{MINIO_BUCKET}/", "", 1)
    
    # Try to process as a local file to upload (use asyncio.to_thread to avoid blocking event loop)
    import asyncio
    processed = await asyncio.to_thread(user_logger.save_input_image, path)
    if processed:
        return processed
        
    # If it's not a local file (e.g., an existing MinIO object key from History), return it as is
    return path

async def core_submit_face_video(
    task_id: str,
    internal_user_id: int,
    username: str,
    face_image_path: str,
    video_path: str,
    resolution: int,
    duration: int,
    cost: int,
    mode: str,
    priority: int,
    chat_id: int = None,
    message_id: int = None,
    allow_contribute: bool = True
) -> Tuple[bool, str, Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    纯净的任务派发逻辑。不负责发送 Telegram 消息。
    返回: (是否成功, 错误/成功描述, backend_task_id, saved_face_image, saved_video, registry_task_id)
    """
    user_logger = UserLogger(internal_user_id, username)
    saved_face_image = await _process_input_path(user_logger, face_image_path)
    saved_video = await _process_input_path(user_logger, video_path)

    if not saved_face_image or not saved_video:
        return False, "Failed to process input media.", None, None, None, None

    registry_task_id = await TaskRegistry.add_task(
        task_id,
        internal_user_id,
        username,
        cost,
        mode,
        chat_id=chat_id,
        message_id=message_id,
        prompt="face video",
        saved_input_images=[saved_face_image, saved_video],
        is_video=True,
        priority=priority
    )

    try:
        backend_task_id = await image_service.submit_face_video(
            task_id,
            saved_face_image,
            saved_video,
            resolution=resolution,
            duration=duration,
            priority=priority
        )

        if registry_task_id and backend_task_id:
            await TaskRegistry.update_backend_task_id(registry_task_id, backend_task_id)
        
        if not backend_task_id:
            if registry_task_id:
                await TaskRegistry.mark_task_status(registry_task_id, "failed")
            return False, "Failed to submit task to backend API.", None, None, None, registry_task_id

        return True, "Task submitted successfully.", backend_task_id, saved_face_image, saved_video, registry_task_id

    except Exception as e:
        logger.error(f"Error submitting face video task for {internal_user_id}: {e}", exc_info=True)
        if registry_task_id:
            try:
                await TaskRegistry.mark_task_status(registry_task_id, "failed")
            except AttributeError:
                pass
        error_msg = str(e)
        if any(kw in error_msg for kw in ["Circuit is open", "All connection attempts failed", "Connection refused", "timeout", "ConnectError"]) or "CircuitBreaker" in str(type(e)):
            user_msg = "当前服务器繁忙，请稍后再试"
        else:
            user_msg = f"System error: {error_msg}"

        return False, user_msg, None, None, None, registry_task_id


async def core_submit_generation_task(
    task_id: str,
    internal_user_id: int,
    username: str,
    prompt: str,
    images: List[str],
    is_video: bool,
    task_type: str,
    cost: int,
    priority: int,
    negative_prompt: str,
    steps: int = 25,
    chat_id: int = None,
    message_id: int = None,
    lora_name: str = None,
    lora_strength: float = 1.0,
    resolution: int = 512,
    duration: int = 5,
    allow_contribute: bool = True
) -> Tuple[bool, str, Optional[str], List[str], Optional[str]]:
    """
    纯净的生成任务派发逻辑（包括图生图、文生图、动图等）。
    """
    user_logger = UserLogger(internal_user_id, username)
    saved_input_images = []
    if images:
        for img in images:
            processed_img = await _process_input_path(user_logger, img)
            if processed_img:
                saved_input_images.append(processed_img)

    registry_task_id = await TaskRegistry.add_task(
        task_id,
        internal_user_id,
        username,
        cost,
        task_type,
        chat_id=chat_id,
        message_id=message_id,
        prompt=prompt,
        saved_input_images=saved_input_images,
        is_video=is_video,
        priority=priority
    )

    try:
        if task_type == "face_swap" and len(saved_input_images) < 2:
            return False, "缺少人脸或身体图片", None, [], registry_task_id
        if is_video and len(saved_input_images) == 0:
            return False, "缺少图片", None, [], registry_task_id
            
        worker_inputs = {
            "saved_input_images": saved_input_images,
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "resolution": resolution,
            "duration": duration,
            "lora_name": lora_name,
            "lora_strength": lora_strength,
        }
        
        backend_task_id = await dispatch_to_worker(task_id, task_type, worker_inputs, priority)

        if registry_task_id and backend_task_id:
            await TaskRegistry.update_backend_task_id(registry_task_id, backend_task_id)
        
        if not backend_task_id:
            if registry_task_id:
                await TaskRegistry.mark_task_status(registry_task_id, "failed")
            return False, "Failed to submit generation task.", None, [], registry_task_id

        return True, "Generation task submitted.", backend_task_id, saved_input_images, registry_task_id

    except Exception as e:
        logger.error(f"Error submitting generation task for {internal_user_id}: {e}", exc_info=True)
        if registry_task_id:
            try:
                await TaskRegistry.mark_task_status(registry_task_id, "failed")
            except AttributeError:
                pass
        error_msg = str(e)
        if any(kw in error_msg for kw in ["Circuit is open", "All connection attempts failed", "Connection refused", "timeout", "ConnectError"]) or "CircuitBreaker" in str(type(e)):
            user_msg = "当前服务器繁忙，请稍后再试"
        else:
            user_msg = f"System error: {error_msg}"
        return False, user_msg, None, [], registry_task_id

from src.utils import load_prompts
from src.constants import TASK_COSTS, RESOLUTION_COST, DURATION_MULTIPLIER, MODE_I2I_PRO, MODE_FACESWAP_STEP1, LTX_RESOLUTION_COST, LTX_DURATION_MULTIPLIER
from src.core.billing_core import check_concurrency_lock, release_concurrency_lock, check_and_deduct_credits, refund_credits, get_user_priority_and_identity
from src.core.task_dispatcher import StrategyFactory, dispatch_to_worker

class CoreDomainError(Exception):
    pass
    
class InsufficientCreditsError(CoreDomainError):
    pass
    
class ConcurrencyLimitError(CoreDomainError):
    pass

async def monitor_task_and_release_lock(
    task_id: str, 
    internal_user_id: int, 
    username: str,
    registry_task_id: str, 
    is_video: bool = False,
    task_type: str = "",
    prompt: str = "",
    input_images: list = None,
    allow_contribute: bool = True
):
    """
    Background task to monitor progress and release concurrency lock.
    """
    import asyncio
    from src.database.core import AsyncSessionLocal
    from src.database.models import History
    
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
    except asyncio.CancelledError:
        logger.error(f"Task monitor {task_id} cancelled.")
    except Exception as e:
        logger.error(f"Background monitoring error for task {task_id}: {e}")
    finally:
        # Save to History if successful
        if final_status == "done" and result_path:
            try:
                user_logger = UserLogger(internal_user_id, username)
                media_bytes = await (image_service.download_video_result(task_id) if is_video else image_service.download_result(task_id))
                if media_bytes:
                    ext = "mp4" if is_video else "png"
                    saved_output_image = await asyncio.to_thread(user_logger.save_output_image, media_bytes, task_id, ext)
                    await user_logger.log_task(prompt, input_images, saved_output_image, task_id=task_id, type=task_type, allow_contribute=allow_contribute, source="web")
                else:
                    await user_logger.log_task(prompt, input_images, result_path, task_id=task_id, type=task_type, allow_contribute=allow_contribute, source="web")
            except Exception as log_err:
                logger.error(f"Failed to log task history for {task_id}: {log_err}")
                
        # Use asyncio.create_task for the release to avoid being cancelled
        try:
            await release_concurrency_lock(internal_user_id)
        except Exception as e:
            logger.error(f"Failed to release concurrency lock for {internal_user_id}: {e}")
            
        if registry_task_id:
            try:
                await TaskRegistry.remove_task(registry_task_id)
            except Exception as e:
                logger.error(f"Failed to remove registry task {registry_task_id}: {e}")

async def process_and_submit_task(
    user_id: int, 
    username: str,
    task_type: str, 
    inputs: dict,
    base_priority: int = 0,
    is_template: bool = False
) -> dict:
    import uuid
    import asyncio
    
    strategy = StrategyFactory.get_strategy(task_type)
    cost = strategy.get_cost(inputs)
    video_types = ["doggy_style", "perfect_video_insert", "blowjob", "undress_tongue", "closeup_blowjob", "custom_video", "face_video", "video_lora", "ltx_video"]
    is_video_task = task_type in video_types
    
    if is_video_task:
        resolution = inputs.get("resolution", 512)
        duration = inputs.get("duration", 5)
        if int(resolution) >= 1024 and int(duration) >= 10:
            raise CoreDomainError("Cannot select 1024p resolution and 10s duration simultaneously due to high resource usage.")
    
    can_run, err = await check_concurrency_lock(user_id)
    if not can_run:
        raise ConcurrencyLimitError(err)
        
    task_submitted_successfully = False
    credits_deducted = False
    
    try:
        task_id = str(uuid.uuid4())
        
        success, err = await check_and_deduct_credits(user_id, cost, task_type, username)
        if not success:
            raise InsufficientCreditsError(err)
            
        credits_deducted = True
        
        try:
            priority, _, _ = await get_user_priority_and_identity(user_id)
            final_priority = min(base_priority + priority, 100)
            
            prompts_config = load_prompts()
            prompt = inputs.get("prompt")
            # Only use default prompt if user didn't provide one
            if not prompt or prompt.strip() == "":
                prompt = prompts_config.get(task_type, task_type)
            negative_prompt = prompts_config.get("negative_prompt", "")
            
            allow_contribute = not is_template
            registry_task_id = None
            saved_inputs = []
            log_prompt = prompt
            
            if task_type == "face_swap":
                face_img = inputs.get("face_image")
                body_img = inputs.get("target_image")
                if not face_img or not body_img:
                    raise CoreDomainError("face_image and target_image are required for face_swap")
                    
                success, msg, backend_task_id, saved_inputs, registry_task_id = await core_submit_generation_task(
                    task_id=task_id,
                    internal_user_id=user_id,
                    username=username,
                    prompt=prompt,
                    images=[body_img, face_img],
                    is_video=False,
                    task_type="face_swap",
                    cost=cost,
                    priority=final_priority,
                    negative_prompt=negative_prompt,
                    allow_contribute=allow_contribute
                )
            elif task_type == "face_video":
                face_img = inputs.get("face_image")
                video_path = inputs.get("target_video")
                resolution = inputs.get("resolution", 512)
                duration_sec = inputs.get("duration", 5)
                duration_frames = 161 if duration_sec >= 10 else 121
                
                success, msg, backend_task_id, saved_face_img, saved_vid, registry_task_id = await core_submit_face_video(
                    task_id=task_id,
                    internal_user_id=user_id,
                    username=username,
                    face_image_path=face_img,
                    video_path=video_path,
                    resolution=resolution,
                    duration=duration_frames,
                    cost=cost,
                    mode="MODE_FACE_VIDEO_STEP2",
                    priority=final_priority,
                    allow_contribute=allow_contribute
                )
                if success:
                    saved_inputs = [saved_face_img, saved_vid]
            else:
                images = inputs.get("images", [])
                lora_name = inputs.get("lora_name")
                
                from src.handlers.fsm.edit_image_fsm import get_lora_default_strength
                default_strength = get_lora_default_strength(lora_name) if lora_name else 1.0
                lora_strength = inputs.get("lora_strength", default_strength)
                
                if lora_name == "qwen/adjust_pussy_anus.safetensors":
                    if "adjust her pussy and anus" not in (prompt or "").lower():
                        prompt = f"adjust her pussy and anus, {prompt or ''}".strip(", ")
                        
                if task_type in ["video_lora", "img2img_lora"] and lora_name:
                    log_prompt = f"[模型: {lora_name}] {prompt}"
                        
                resolution = inputs.get("resolution", 512)
                duration = inputs.get("duration", 5)
                
                success, msg, backend_task_id, saved_inputs, registry_task_id = await core_submit_generation_task(
                    task_id=task_id,
                    internal_user_id=user_id,
                    username=username,
                    prompt=prompt,
                    images=images,
                    is_video=is_video_task,
                    task_type=task_type,
                    cost=cost,
                    priority=final_priority,
                    negative_prompt=negative_prompt,
                    lora_name=lora_name,
                    lora_strength=lora_strength,
                    resolution=resolution,
                    duration=duration,
                    allow_contribute=allow_contribute
                )
                
            if not success or not backend_task_id:
                raise CoreDomainError(msg)
                
            try:
                asyncio.create_task(
                    monitor_task_and_release_lock(
                        task_id=backend_task_id, 
                        internal_user_id=user_id, 
                        username=username,
                        registry_task_id=registry_task_id, 
                        is_video=is_video_task,
                        task_type=task_type,
                        prompt=log_prompt,
                        input_images=saved_inputs,
                        allow_contribute=allow_contribute
                    )
                )
            except Exception as e:
                # 如果监控挂载失败，由外层的 Saga 补偿机制和 finally 统一处理退款和释放锁
                raise CoreDomainError(f"后台监控挂载失败: {e}")
                
            task_submitted_successfully = True
            
            return {
                "task_id": backend_task_id, 
                "registry_task_id": registry_task_id, 
                "cost": cost,
                "saved_inputs": saved_inputs
            }
            
        except Exception as e:
            # Saga 补偿机制触发
            logger.error(f"Saga Execute Failed: {e}")
            if credits_deducted:
                try:
                    await asyncio.shield(refund_credits(user_id, cost, reason=f"Task Failed: {str(e)}", operator=username))
                except Exception as refund_err:
                    logger.critical(f"REFUND FAILED! Log to Outbox. User: {user_id}, Amount: {cost}, Error: {refund_err}")
                    from src.services.redis_client import redis_client
                    await redis_client.add_pending_refund(user_id, cost, f"Task Failed: {str(e)}", username)
                    
            try:
                await asyncio.shield(TaskRegistry.remove_task(task_id))
            except Exception: 
                pass
                
            raise CoreDomainError(f"系统派发失败，灵石已全额退还。错误: {str(e)}")
            
    finally:
        # 兜底保障：确保并发锁释放
        if not task_submitted_successfully:
            await asyncio.shield(release_concurrency_lock(user_id))
