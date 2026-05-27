"""
Telegram Bot task entrypoints and minimal compatibility facade.

Prefer importing the module-level async functions from this module directly.
`TaskService` is kept only as a thin compatibility boundary for legacy callers.
"""

from typing import Any, Optional, Tuple

from telegram import InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.constants import (
    MODE_BLOWJOB,
    MODE_CLOSEUP_BLOWJOB,
    MODE_DOGGY_STYLE,
    MODE_IMAGE_TO_VIDEO,
    MODE_PERFECT_VIDEO_INSERT,
    MODE_UNDRESS_TONGUE,
)
from src.services.task_service_cleanup import cleanup_task_files
from src.services.task_service_entrypoints_generation import (
    process_generation_task as process_generation_task_impl,
    process_i2i_pro_task as process_i2i_pro_task_impl,
    process_image_to_video_task as process_image_to_video_task_impl,
)
from src.services.task_service_entrypoints_specialized import (
    process_face_video_task as process_face_video_task_impl,
    process_ltx_video_task as process_ltx_video_task_impl,
)
from src.services.task_service_entrypoints_video import (
    process_custom_video_task as process_custom_video_task_impl,
    process_video_task_template as process_video_task_template_impl,
)
from src.services.task_service_message_support import with_submitted_status


async def process_ltx_video_task(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    prompt: str,
    image_path: str,
    lora_name: str | None = None,
    lora_strength: float | None = None,
    lora_items: list[dict[str, Any]] | None = None,
    cleanup: bool = True,
    allow_contribute: bool = True,
    source_post_id: Optional[int] = None,
):
    return await process_ltx_video_task_impl(
        update=update,
        context=context,
        prompt=prompt,
        image_path=image_path,
        lora_name=lora_name,
        lora_strength=lora_strength,
        lora_items=lora_items,
        cleanup=cleanup,
        allow_contribute=allow_contribute,
        source_post_id=source_post_id,
    )


async def process_face_video_task(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_id: int,
    username: str,
    face_image_path: str,
    video_path: str,
    resolution: int,
    duration: int,
    cost: int,
    message_id: int = None,
    cleanup: bool = True,
    source_post_id: Optional[int] = None,
):
    return await process_face_video_task_impl(
        context=context,
        chat_id=chat_id,
        user_id=user_id,
        username=username,
        face_image_path=face_image_path,
        video_path=video_path,
        resolution=resolution,
        duration=duration,
        cost=cost,
        message_id=message_id,
        cleanup=cleanup,
        source_post_id=source_post_id,
    )

async def process_generation_task(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_id: int,
    username: str,
    prompt: str,
    images: list[str],
    is_video: bool = False,
    status_msg_id: int = None,
    delete_status: bool = True,
    task_type: str = None,
    cleanup: bool = True,
    send_result: bool = True,
    deduct_quota: bool = True,
    reply_markup: InlineKeyboardMarkup = None,
    lora_name: str = None,
    lora_strength: float = 1.0,
    allow_contribute: bool = True,
    source_post_id: Optional[int] = None,
    resolution=None,
    duration=None,
) -> Tuple[Optional[bytes], Optional[str]]:
    return await process_generation_task_impl(
        context=context,
        chat_id=chat_id,
        user_id=user_id,
        username=username,
        prompt=prompt,
        images=images,
        is_video=is_video,
        status_msg_id=status_msg_id,
        delete_status=delete_status,
        task_type=task_type,
        cleanup=cleanup,
        send_result=send_result,
        deduct_quota=deduct_quota,
        reply_markup=reply_markup,
        lora_name=lora_name,
        lora_strength=lora_strength,
        allow_contribute=allow_contribute,
        source_post_id=source_post_id,
        resolution=resolution,
        duration=duration,
    )

async def process_image_to_video_task(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_id: int,
    username: str,
    prompt: str,
    images: list[str],
    resolution=None,
    duration=None,
    status_msg_id: int = None,
    delete_status: bool = True,
    task_type: str = MODE_IMAGE_TO_VIDEO,
    cleanup: bool = True,
    send_result: bool = True,
    deduct_quota: bool = True,
    reply_markup: InlineKeyboardMarkup = None,
    lora_name: str = None,
    lora_strength: float = 1.0,
    allow_contribute: bool = True,
    source_post_id: Optional[int] = None,
) -> Tuple[Optional[bytes], Optional[str]]:
    return await process_image_to_video_task_impl(
        context=context,
        chat_id=chat_id,
        user_id=user_id,
        username=username,
        prompt=prompt,
        images=images,
        resolution=resolution,
        duration=duration,
        status_msg_id=status_msg_id,
        delete_status=delete_status,
        task_type=task_type,
        cleanup=cleanup,
        send_result=send_result,
        deduct_quota=deduct_quota,
        reply_markup=reply_markup,
        lora_name=lora_name,
        lora_strength=lora_strength,
        allow_contribute=allow_contribute,
        source_post_id=source_post_id,
    )

async def process_blowjob_task(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    image_path: str,
    cleanup: bool = True,
    allow_contribute: bool = True,
):
    return await process_video_task_template_impl(
        update=update,
        context=context,
        image_path=image_path,
        mode=MODE_BLOWJOB,
        default_prompt_key="blowjob",
        default_prompt_text="undress blowjob",
        cleanup=cleanup,
        allow_contribute=allow_contribute,
    )

async def process_undress_tongue_task(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    image_path: str,
    cleanup: bool = True,
    allow_contribute: bool = True,
):
    return await process_video_task_template_impl(
        update=update,
        context=context,
        image_path=image_path,
        mode=MODE_UNDRESS_TONGUE,
        default_prompt_key="undress_tongue",
        default_prompt_text="undress and show tongue",
        cleanup=cleanup,
        allow_contribute=allow_contribute,
    )

async def process_doggy_style_task(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    image_path: str,
    cleanup: bool = True,
    allow_contribute: bool = True,
):
    return await process_video_task_template_impl(
        update=update,
        context=context,
        image_path=image_path,
        mode=MODE_DOGGY_STYLE,
        default_prompt_key="doggy_style",
        default_prompt_text="doggy style sex",
        cleanup=cleanup,
        allow_contribute=allow_contribute,
    )

async def process_closeup_blowjob_task(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    image_path: str,
    cleanup: bool = True,
    allow_contribute: bool = True,
):
    return await process_video_task_template_impl(
        update=update,
        context=context,
        image_path=image_path,
        mode=MODE_CLOSEUP_BLOWJOB,
        default_prompt_key="closeup_blowjob",
        default_prompt_text="closeup blowjob sex",
        cleanup=cleanup,
        allow_contribute=allow_contribute,
    )

async def process_perfect_video_insert_task(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    image_path: str,
    cleanup: bool = True,
    allow_contribute: bool = True,
):
    return await process_video_task_template_impl(
        update=update,
        context=context,
        image_path=image_path,
        mode=MODE_PERFECT_VIDEO_INSERT,
        default_prompt_key="perfect_video_insert",
        default_prompt_text="missionary sex",
        cleanup=cleanup,
        allow_contribute=allow_contribute,
    )

async def process_custom_video_task(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    prompt: str,
    image_path: str,
    cleanup: bool = True,
    source_post_id: Optional[int] = None,
):
    return await process_custom_video_task_impl(
        update=update,
        context=context,
        prompt=prompt,
        image_path=image_path,
        cleanup=cleanup,
        source_post_id=source_post_id,
    )

async def process_video_task_template(
    context: ContextTypes.DEFAULT_TYPE,
    mode: str,
    default_prompt_key: str,
    default_prompt_text: str,
    *,
    update: Update | None = None,
    image_path: str,
    cleanup: bool = True,
    allow_contribute: bool = True,
    source_post_id: Optional[int] = None,
    chat_id: Optional[int] = None,
    user_id: Optional[int] = None,
    username: Optional[str] = None,
    status_msg_id: Optional[int] = None,
):
    return await process_video_task_template_impl(
        context=context,
        mode=mode,
        default_prompt_key=default_prompt_key,
        default_prompt_text=default_prompt_text,
        update=update,
        image_path=image_path,
        cleanup=cleanup,
        allow_contribute=allow_contribute,
        source_post_id=source_post_id,
        chat_id=chat_id,
        user_id=user_id,
        username=username,
        status_msg_id=status_msg_id,
    )


async def process_i2i_pro_task(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_id: int,
    username: str,
    prompt: str,
    images: list[str],
    allow_contribute: bool = True,
    source_post_id: Optional[int] = None,
):
    return await process_i2i_pro_task_impl(
        context=context,
        chat_id=chat_id,
        user_id=user_id,
        username=username,
        prompt=prompt,
        images=images,
        allow_contribute=allow_contribute,
        source_post_id=source_post_id,
    )


class TaskService:
    _with_submitted_status = staticmethod(with_submitted_status)
    _cleanup_files = staticmethod(cleanup_task_files)

    process_ltx_video_task = staticmethod(process_ltx_video_task)
    process_face_video_task = staticmethod(process_face_video_task)
    process_generation_task = staticmethod(process_generation_task)
    process_image_to_video_task = staticmethod(process_image_to_video_task)
    process_blowjob_task = staticmethod(process_blowjob_task)
    process_undress_tongue_task = staticmethod(process_undress_tongue_task)
    process_doggy_style_task = staticmethod(process_doggy_style_task)
    process_closeup_blowjob_task = staticmethod(process_closeup_blowjob_task)
    process_perfect_video_insert_task = staticmethod(process_perfect_video_insert_task)
    process_custom_video_task = staticmethod(process_custom_video_task)
    process_video_task_template = staticmethod(process_video_task_template)
    process_i2i_pro_task = staticmethod(process_i2i_pro_task)


task_service = TaskService()

__all__ = [
    "TaskService",
    "cleanup_task_files",
    "process_blowjob_task",
    "process_closeup_blowjob_task",
    "process_custom_video_task",
    "process_doggy_style_task",
    "process_face_video_task",
    "process_generation_task",
    "process_i2i_pro_task",
    "process_image_to_video_task",
    "process_ltx_video_task",
    "process_perfect_video_insert_task",
    "process_video_task_template",
    "process_undress_tongue_task",
    "task_service",
]
