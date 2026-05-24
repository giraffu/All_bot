from typing import Optional

from src.logger import UserLogger
from src.services.task_service_finalize import finalize_failed_task_for_bot
from src.services.task_service_types import BotTaskMessageSpec
from src.services.tg_task_runtime import (
    cleanup_completion_status_message,
    monitor_task_progress,
    send_result_media,
)


async def monitor_submitted_bot_task(
    *,
    task_id,
    status_msg,
    is_video,
    internal_user_id,
    monitor_func,
    get_user_priority_and_identity_func=None,
    monitor_bot_task_progress_func=None,
    edit_status_text_func=None,
):
    from src.core.billing_core import get_user_priority_and_identity

    get_user_priority_and_identity_func = (
        get_user_priority_and_identity_func or get_user_priority_and_identity
    )
    monitor_bot_task_progress_func = (
        monitor_bot_task_progress_func or monitor_bot_task_progress
    )
    _priority, identity_str, user_group = await get_user_priority_and_identity_func(
        internal_user_id
    )
    return await monitor_bot_task_progress_func(
        task_id,
        status_msg,
        is_video=is_video,
        monitor_func=monitor_func,
        identity_str=identity_str,
        user_group=user_group,
        edit_status_text_func=edit_status_text_func,
    )


async def monitor_bot_task_progress(
    task_id,
    status_msg,
    is_video,
    monitor_func,
    identity_str=None,
    user_group=None,
    edit_status_text_func=None,
):
    from src.core.task_core import CoreDomainError

    def _raise_cancelled():
        raise CoreDomainError("cancelled")

    final_info = await monitor_task_progress(
        task_id=task_id,
        status_msg=status_msg,
        is_video=is_video,
        monitor_func=monitor_func,
        identity_str=identity_str,
        user_group=user_group,
        on_cancelled=_raise_cancelled,
        edit_status_text_func=edit_status_text_func,
    )
    if final_info is None:
        raise CoreDomainError("cancelled")
    return final_info


async def complete_monitored_bot_task(
    *,
    context,
    chat_id,
    status_msg,
    runtime_state,
    internal_user_id,
    username,
    user_logger=None,
    prompt,
    task_type,
    task_id,
    saved_input_images,
    final_info,
    is_video,
    send_result=True,
    reply_markup=None,
    delete_status=True,
    caption=None,
    allow_contribute=True,
    billing_resolution: Optional[str] = None,
    requested_duration: Optional[int] = None,
    message_spec: BotTaskMessageSpec,
    missing_output_should_refund: bool = True,
    send_result_media_func=None,
    cleanup_completion_status_message_func=None,
):
    send_result_media_func = send_result_media_func or send_result_media
    cleanup_completion_status_message_func = (
        cleanup_completion_status_message_func or cleanup_completion_status_message
    )
    user_logger = user_logger or UserLogger(internal_user_id, username)
    if final_info:
        return await handle_task_completion(
            context=context,
            chat_id=chat_id,
            internal_user_id=internal_user_id,
            prompt=prompt,
            task_type=task_type,
            task_id=task_id,
            saved_input_images=saved_input_images,
            user_logger=user_logger,
            is_video=is_video,
            send_result=send_result,
            reply_markup=reply_markup,
            status_msg=status_msg,
            delete_status=delete_status,
            caption=caption or message_spec.completion_caption,
            allow_contribute=allow_contribute,
            billing_resolution=billing_resolution,
            requested_duration=requested_duration,
        )

    await finalize_failed_task_for_bot(
        context=context,
        chat_id=chat_id,
        status_msg=None,
        internal_user_id=internal_user_id,
        username=username,
        cost=runtime_state.actual_cost,
        should_refund=missing_output_should_refund,
        registry_task_id=runtime_state.registry_task_id,
        release_lock=runtime_state.task_submitted,
        explicit_user_message=message_spec.missing_output_message,
    )
    runtime_state.terminal_state_finalized = True
    return None, None


async def download_and_log_task_output(
    *,
    internal_user_id,
    username,
    prompt,
    task_type,
    task_id,
    saved_input_images,
    is_video,
    allow_contribute,
    billing_resolution: Optional[str],
    requested_duration: Optional[int],
):
    from src.core.task_core import persist_successful_task_result

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
    return (
        persistence_result.media_bytes,
        persistence_result.output_file,
        persistence_result.width,
        persistence_result.height,
        persistence_result.duration,
    )


async def handle_task_completion(
    *,
    context,
    chat_id,
    internal_user_id,
    prompt,
    task_type,
    task_id,
    saved_input_images,
    user_logger,
    is_video,
    send_result,
    reply_markup,
    status_msg,
    delete_status,
    caption=None,
    allow_contribute=True,
    billing_resolution: Optional[str] = None,
    requested_duration: Optional[int] = None,
    send_result_media_func=None,
    cleanup_completion_status_message_func=None,
):
    send_result_media_func = send_result_media_func or send_result_media
    cleanup_completion_status_message_func = (
        cleanup_completion_status_message_func or cleanup_completion_status_message
    )
    media_bytes, full_output_path, _width, _height, _duration = (
        await download_and_log_task_output(
            internal_user_id=internal_user_id,
            username=user_logger.username,
            prompt=prompt,
            task_type=task_type,
            task_id=task_id,
            saved_input_images=saved_input_images,
            is_video=is_video,
            allow_contribute=allow_contribute,
            billing_resolution=billing_resolution,
            requested_duration=requested_duration,
        )
    )

    if send_result:
        await send_result_media_func(
            context=context,
            chat_id=chat_id,
            media_bytes=media_bytes,
            is_video=is_video,
            caption=caption,
            task_type=task_type,
            task_id=task_id,
            allow_contribute=allow_contribute,
            reply_markup=reply_markup,
            prompt=prompt,
        )

    await cleanup_completion_status_message_func(
        status_msg=status_msg,
        delete_status=delete_status,
        send_result=send_result,
    )

    return media_bytes, full_output_path
