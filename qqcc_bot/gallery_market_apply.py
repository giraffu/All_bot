from __future__ import annotations

import logging
import time

from telegram import Update
from telegram.ext import ContextTypes

from src.constants import (
    MODE_CUSTOM_VIDEO,
    MODE_EDIT,
    MODE_I2I_PRO,
    MODE_IMAGE_TO_VIDEO,
    MODE_IMG2IMG_LORA,
    MODE_LTX_VIDEO,
    MODE_PORNMASTER_FLUX2_SINGLE_EDIT,
    MODE_WAN22_VIDEO_V2,
)
from src.services.fsm_temp_file_service import (
    cleanup_fsm_temp_files,
    download_telegram_file_to_fsm_temp,
)
from src.services.task_service_entrypoints_generation import process_i2i_pro_task
from src.services.task_service_entrypoints_specialized import process_ltx_video_task
from src.services.task_service_generation_image import process_standard_generation_task
from src.services.task_service_generation_video import (
    process_image_to_video_generation_task,
)
from src.services.task_service_generation_wan22 import (
    process_wan22_video_v2_generation_task,
)
from src.utils import robust_reply_text

logger = logging.getLogger("qqcc_bot.gallery_market.apply")

QQCC_GALLERY_APPLY_SESSION_KEY = "qqcc_gallery_apply"
QQCC_GALLERY_APPLY_SESSION_TTL_SECONDS = 30 * 60

NATIVE_IMAGE_TASK_TYPES = {
    MODE_I2I_PRO,
    MODE_EDIT,
    MODE_IMG2IMG_LORA,
    MODE_PORNMASTER_FLUX2_SINGLE_EDIT,
}
NATIVE_VIDEO_TASK_TYPES = {
    MODE_CUSTOM_VIDEO,
    MODE_IMAGE_TO_VIDEO,
    MODE_WAN22_VIDEO_V2,
    MODE_LTX_VIDEO,
}


def is_qqcc_gallery_apply_session_expired(
    session: dict,
    *,
    now: float | None = None,
) -> bool:
    created_at = float(session.get("created_at") or 0)
    return (now or time.time()) - created_at > QQCC_GALLERY_APPLY_SESSION_TTL_SECONDS


def resolve_image_file_id(message) -> str | None:
    if getattr(message, "photo", None):
        return message.photo[-1].file_id
    document = getattr(message, "document", None)
    if document and str(getattr(document, "mime_type", "") or "").startswith("image/"):
        return document.file_id
    return None


def _t(context, key: str, **kwargs) -> str:
    translator = getattr(context, "t", None)
    if callable(translator):
        return translator(key, **kwargs)
    return key.format(**kwargs) if kwargs else key


async def download_market_apply_image(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> str | None:
    message = update.effective_message
    file_id = resolve_image_file_id(message)
    if not file_id:
        await robust_reply_text(message, _t(context, "qqcc.market.invalid_image"))
        return None
    try:
        telegram_file = await context.bot.get_file(file_id)
        return await download_telegram_file_to_fsm_temp(
            telegram_file=telegram_file,
            suffix=".png",
            name_hint="qqcc_gallery_apply",
        )
    except Exception:
        logger.exception("Failed to download QQCC market apply image.")
        await robust_reply_text(message, _t(context, "fsm.common.download_image_failed"))
        return None


async def submit_qqcc_gallery_apply_session(
    *,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    image_path: str,
    session: dict,
    process_i2i_pro_task_func=process_i2i_pro_task,
    process_standard_generation_task_func=process_standard_generation_task,
    process_image_to_video_generation_task_func=process_image_to_video_generation_task,
    process_wan22_video_v2_generation_task_func=process_wan22_video_v2_generation_task,
    process_ltx_video_task_func=process_ltx_video_task,
):
    user = update.effective_user
    chat_id = update.effective_chat.id
    task_type = str(session.get("task_type") or "")
    prompt = str(session.get("prompt") or "")
    negative_prompt = str(session.get("negative_prompt") or "")
    source_post_id = session.get("source_post_id") or session.get("post_id")
    lora_name = session.get("lora_name")
    lora_strength = session.get("lora_strength") or 1.0
    requested_duration = session.get("requested_duration") or session.get("duration")
    billing_resolution = session.get("billing_resolution")

    if task_type == MODE_I2I_PRO:
        return await process_i2i_pro_task_func(
            context=context,
            chat_id=chat_id,
            user_id=user.id,
            username=user.username,
            prompt=prompt,
            images=[image_path],
            allow_contribute=False,
            source_post_id=source_post_id,
        )
    if task_type in NATIVE_IMAGE_TASK_TYPES:
        return await process_standard_generation_task_func(
            context=context,
            chat_id=chat_id,
            user_id=user.id,
            username=user.username,
            prompt=prompt,
            images=[image_path],
            is_video=False,
            task_type=task_type,
            lora_name=lora_name,
            lora_strength=lora_strength,
            allow_contribute=False,
            source_post_id=source_post_id,
        )
    if task_type in {MODE_CUSTOM_VIDEO, MODE_IMAGE_TO_VIDEO}:
        return await process_image_to_video_generation_task_func(
            context=context,
            chat_id=chat_id,
            user_id=user.id,
            username=user.username,
            prompt=prompt,
            negative_prompt=negative_prompt,
            images=[image_path],
            resolution=billing_resolution,
            duration=requested_duration,
            task_type=task_type,
            lora_name=lora_name,
            lora_strength=lora_strength,
            allow_contribute=False,
            source_post_id=source_post_id,
        )
    if task_type == MODE_WAN22_VIDEO_V2:
        return await process_wan22_video_v2_generation_task_func(
            context=context,
            chat_id=chat_id,
            user_id=user.id,
            username=user.username,
            prompt=prompt,
            negative_prompt=negative_prompt,
            images=[image_path],
            use_end_frame=False,
            resolution_preset=billing_resolution,
            duration=requested_duration,
            allow_contribute=False,
            source_post_id=source_post_id,
        )
    if task_type == MODE_LTX_VIDEO:
        sentinel = object()
        previous_resolution = context.user_data.get("ltx_video_resolution", sentinel)
        previous_duration = context.user_data.get("ltx_video_duration", sentinel)
        try:
            if session.get("width") and session.get("height"):
                context.user_data["ltx_video_resolution"] = (
                    f"{session['width']}x{session['height']}"
                )
            if requested_duration:
                context.user_data["ltx_video_duration"] = f"{requested_duration}s"
            return await process_ltx_video_task_func(
                update=update,
                context=context,
                prompt=prompt,
                image_path=image_path,
                ltx_mode="i2v",
                lora_items=session.get("lora_items"),
                allow_contribute=False,
                source_post_id=source_post_id,
            )
        finally:
            if previous_resolution is sentinel:
                context.user_data.pop("ltx_video_resolution", None)
            else:
                context.user_data["ltx_video_resolution"] = previous_resolution
            if previous_duration is sentinel:
                context.user_data.pop("ltx_video_duration", None)
            else:
                context.user_data["ltx_video_duration"] = previous_duration
    raise ValueError(f"Unsupported QQCC gallery apply task type: {task_type}")


async def handle_qqcc_gallery_apply_media(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    download_image_func=download_market_apply_image,
    submit_session_func=submit_qqcc_gallery_apply_session,
    cleanup_temp_files_func=cleanup_fsm_temp_files,
    reply_text_func=robust_reply_text,
    is_session_expired_func=is_qqcc_gallery_apply_session_expired,
):
    session = context.user_data.get(QQCC_GALLERY_APPLY_SESSION_KEY)
    message = update.effective_message
    if not session:
        return None
    if is_session_expired_func(session):
        context.user_data.pop(QQCC_GALLERY_APPLY_SESSION_KEY, None)
        await reply_text_func(message, _t(context, "qqcc.market.apply_expired"))
        return None

    image_path = await download_image_func(update, context)
    if not image_path:
        return None

    try:
        context.user_data.pop(QQCC_GALLERY_APPLY_SESSION_KEY, None)
        await submit_session_func(
            update=update,
            context=context,
            image_path=image_path,
            session=session,
        )
    except Exception:
        logger.exception("Failed to submit QQCC market apply task.")
        cleanup_temp_files_func([image_path])
        await reply_text_func(message, _t(context, "qqcc.market.apply_submit_failed"))
    return None
