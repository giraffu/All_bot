import logging

from src.core.task_core import persist_successful_task_result
from src.services.image_service import image_service
from src.services.permission_service import permission_service
from src.services.tg_task_runtime import (
    TelegramBotContextAdapter,
    TelegramMessageAdapter,
    cleanup_completion_status_message,
    monitor_task_progress,
    send_result_media,
)

logger = logging.getLogger(__name__)


async def _monitor_recovered_task_progress(
    *,
    task_id,
    status_msg,
    is_video,
    identity_str=None,
    user_group=None,
):
    return await monitor_task_progress(
        task_id=task_id,
        status_msg=status_msg,
        is_video=is_video,
        monitor_func=image_service.monitor_progress,
        identity_str=identity_str,
        user_group=user_group,
    )


async def _handle_recovered_task_completion(
    *,
    context,
    chat_id,
    internal_user_id,
    username,
    prompt,
    task_type,
    task_id,
    saved_input_images,
    is_video,
    send_result,
    reply_markup,
    status_msg,
    delete_status,
    allow_contribute,
    billing_resolution,
    requested_duration,
    caption=None,
):
    persistence_result = await persist_successful_task_result(
        backend_task_id=task_id,
        registry_task_id=task_id,
        internal_user_id=internal_user_id,
        username=username,
        prompt=prompt,
        task_type=task_type,
        input_images=saved_input_images,
        allow_contribute=allow_contribute,
        is_video=is_video,
        billing_resolution=billing_resolution,
        requested_duration=requested_duration,
        source="bot",
        refresh_user_group_after_log=True,
    )

    if send_result and persistence_result.media_bytes:
        await send_result_media(
            context=context,
            chat_id=chat_id,
            media_bytes=persistence_result.media_bytes,
            is_video=is_video,
            caption=caption,
            task_type=task_type,
            task_id=task_id,
            allow_contribute=allow_contribute,
            reply_markup=reply_markup,
            prompt=prompt,
        )

    await cleanup_completion_status_message(
        status_msg=status_msg,
        delete_status=delete_status,
        send_result=send_result,
    )
    return persistence_result


async def run_recovered_task(task_data: dict, application) -> bool:
    bot = application.bot
    user_id = task_data.get("user_id")
    username = task_data.get("username")
    backend_task_id = task_data.get("backend_task_id")
    chat_id = task_data.get("chat_id")
    message_id = task_data.get("message_id")
    task_type = task_data.get("task_type")
    prompt = task_data.get("prompt", "")
    saved_input_images = task_data.get("saved_input_images", [])
    is_video = task_data.get("is_video", False)
    allow_contribute = task_data.get("allow_contribute", True)
    metadata = task_data.get("metadata") or {}
    billing_resolution = task_data.get("billing_resolution") or metadata.get(
        "billing_resolution"
    )
    requested_duration = task_data.get("requested_duration") or metadata.get(
        "requested_duration"
    )

    if not backend_task_id:
        return False

    runtime_context = TelegramBotContextAdapter(application)
    status_msg = (
        TelegramMessageAdapter(bot, chat_id, message_id)
        if chat_id and message_id
        else None
    )

    identity_str = await permission_service.get_user_identity(user_id)
    user_group = await permission_service.get_user_group(user_id)

    final_info = await _monitor_recovered_task_progress(
        task_id=backend_task_id,
        status_msg=status_msg,
        is_video=is_video,
        identity_str=identity_str,
        user_group=user_group,
    )
    if not final_info:
        return False

    await _handle_recovered_task_completion(
        context=runtime_context,
        chat_id=chat_id,
        internal_user_id=user_id,
        username=username,
        prompt=prompt,
        task_type=task_type,
        task_id=backend_task_id,
        saved_input_images=saved_input_images,
        is_video=is_video,
        send_result=bool(chat_id),
        reply_markup=None,
        status_msg=status_msg,
        delete_status=bool(status_msg),
        allow_contribute=allow_contribute,
        billing_resolution=billing_resolution,
        requested_duration=requested_duration,
    )
    return True
