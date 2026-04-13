from typing import Tuple, Optional, List
import logging

from src.services.image_service import image_service
from src.services.task_registry import TaskRegistry
from src.logger import UserLogger
from config import MINIO_BUCKET

logger = logging.getLogger(__name__)

def _process_input_path(user_logger: UserLogger, path: str) -> str:
    if not path:
        return ""
    if path.startswith("template:"):
        return path
    if path.startswith(f"{MINIO_BUCKET}/"):
        return path.replace(f"{MINIO_BUCKET}/", "", 1)
    return user_logger.save_input_image(path)

async def core_submit_face_video(
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
) -> Tuple[bool, str, Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    纯净的任务派发逻辑。不负责发送 Telegram 消息。
    返回: (是否成功, 错误/成功描述, backend_task_id, saved_face_image, saved_video, registry_task_id)
    """
    user_logger = UserLogger(internal_user_id, username)
    saved_face_image = _process_input_path(user_logger, face_image_path)
    saved_video = _process_input_path(user_logger, video_path)

    if not saved_face_image or not saved_video:
        return False, "Failed to process input media.", None, None, None, None

    registry_task_id = await TaskRegistry.add_task(
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
        task_id = await image_service.submit_face_video(
            saved_face_image,
            saved_video,
            resolution=resolution,
            duration=duration,
            priority=priority
        )

        if registry_task_id and task_id:
            await TaskRegistry.update_backend_task_id(registry_task_id, task_id)
        
        if not task_id:
            if registry_task_id:
                await TaskRegistry.mark_task_status(registry_task_id, "failed")
            return False, "Failed to submit task to backend API.", None, None, None, registry_task_id

        return True, "Task submitted successfully.", task_id, saved_face_image, saved_video, registry_task_id

    except Exception as e:
        logger.error(f"Error submitting face video task for {internal_user_id}: {e}", exc_info=True)
        if registry_task_id:
            try:
                await TaskRegistry.mark_task_status(registry_task_id, "failed")
            except AttributeError:
                pass
        return False, f"System error: {str(e)}", None, None, None, registry_task_id


async def core_submit_generation_task(
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
) -> Tuple[bool, str, Optional[str], List[str], Optional[str]]:
    """
    纯净的生成任务派发逻辑（包括图生图、文生图、动图等）。
    """
    user_logger = UserLogger(internal_user_id, username)
    saved_input_images = []
    if images:
        for img in images:
            processed_img = _process_input_path(user_logger, img)
            if processed_img:
                saved_input_images.append(processed_img)

    registry_task_id = await TaskRegistry.add_task(
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
        # 检查 task_type，如果是 face_swap，应该调用 submit_face_swap_task
        if task_type == "face_swap":
            if len(saved_input_images) < 2:
                return False, "缺少人脸或身体图片", None, [], registry_task_id
            task_id = await image_service.submit_face_swap_task(
                face_image_path=saved_input_images[1], # face is at index 1
                body_image_path=saved_input_images[0], # body is at index 0 (body first, face second in FSM)
                priority=priority
            )
        elif is_video:
            if len(saved_input_images) == 0:
                return False, "缺少图片", None, [], registry_task_id
            if task_type == "doggy_style":
                task_id = await image_service.submit_perfect_video_insert_task(
                    prompt=prompt, image_path=saved_input_images[0], priority=priority
                )
            else:
                task_id = await image_service.submit_perfect_video_edit(
                    prompt=prompt, image_path=saved_input_images[0], priority=priority
                )
        else:
            task_id = await image_service.submit_task(
                prompt=prompt,
                image_paths=saved_input_images,
                negative_prompt=negative_prompt,
                priority=priority
            )

        if registry_task_id and task_id:
            await TaskRegistry.update_backend_task_id(registry_task_id, task_id)
        
        if not task_id:
            if registry_task_id:
                await TaskRegistry.mark_task_status(registry_task_id, "failed")
            return False, "Failed to submit generation task.", None, [], registry_task_id

        return True, "Generation task submitted.", task_id, saved_input_images, registry_task_id

    except Exception as e:
        logger.error(f"Error submitting generation task for {internal_user_id}: {e}", exc_info=True)
        if registry_task_id:
            try:
                await TaskRegistry.mark_task_status(registry_task_id, "failed")
            except AttributeError:
                pass
        return False, f"System error: {str(e)}", None, [], registry_task_id
