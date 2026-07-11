from typing import Optional

from src.logger import UserLogger
from src.services.task_service_finalize import finalize_failed_task_for_bot
from src.services.task_service_message_support import resolve_context_lang
from src.services.task_service_types import (
    BotTaskCancelled,
    BotTaskCompletionContext,
    BotTaskFailureContext,
)
from src.services.tg_task_runtime import (
    cleanup_completion_status_message,
    monitor_task_progress,
    send_result_media,
)
from src.services.ltx_video_extension_service import (
    merge_ltx_history_context_into_extra_outputs,
)
from src.services.wan22_video_v2_extension_service import (
    merge_wan22_history_context_into_extra_outputs,
)
from src.services.qqcc_regenerate_metadata import (
    merge_qqcc_regenerate_context_into_extra_outputs,
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
    lang: str = "zh",
    allow_cancel: bool = True,
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
        lang=lang,
        allow_cancel=allow_cancel,
    )


async def monitor_bot_task_progress(
    task_id,
    status_msg,
    is_video,
    monitor_func,
    identity_str=None,
    user_group=None,
    edit_status_text_func=None,
    lang: str = "zh",
    allow_cancel: bool = True,
):
    def _raise_cancelled():
        raise BotTaskCancelled()

    final_info = await monitor_task_progress(
        task_id=task_id,
        status_msg=status_msg,
        is_video=is_video,
        monitor_func=monitor_func,
        identity_str=identity_str,
        user_group=user_group,
        lang=lang,
        on_cancelled=_raise_cancelled,
        edit_status_text_func=edit_status_text_func,
        allow_cancel=allow_cancel,
    )
    if final_info is None:
        raise BotTaskCancelled()
    return final_info


async def complete_monitored_bot_task(
    *,
    completion: BotTaskCompletionContext,
):
    user_logger = completion.user_logger or UserLogger(
        completion.internal_user_id, completion.username
    )
    if completion.final_info:
        return await handle_task_completion(
            context=completion.context,
            chat_id=completion.chat_id,
            internal_user_id=completion.internal_user_id,
            prompt=completion.prompt,
            task_type=completion.task_type,
            registry_task_id=completion.registry_task_id,
            backend_task_id=completion.backend_task_id,
            saved_input_images=completion.saved_input_images,
            user_logger=user_logger,
            is_video=completion.is_video,
            send_result=completion.send_result,
            reply_markup=completion.reply_markup,
            status_msg=completion.status_msg,
            delete_status=completion.delete_status,
            caption=completion.caption or completion.message_spec.completion_caption,
            allow_contribute=completion.allow_contribute,
            result_meta=completion.result_meta,
            extra_outputs=completion.final_info.get("extra_outputs")
            if isinstance(completion.final_info, dict)
            else None,
            billing_resolution=completion.billing_resolution,
            requested_duration=completion.requested_duration,
            lang=resolve_context_lang(completion.context),
        )

    await finalize_failed_task_for_bot(
        context=completion.context,
        chat_id=completion.chat_id,
        status_msg=None,
        failure=BotTaskFailureContext(
            internal_user_id=completion.internal_user_id,
            username=completion.username,
            cost=completion.runtime_state.actual_cost,
            should_refund=completion.missing_output_should_refund,
            registry_task_id=completion.runtime_state.registry_task_id,
            release_lock=completion.runtime_state.task_submitted,
            explicit_user_message=completion.message_spec.missing_output_message,
        ),
    )
    completion.runtime_state.terminal_state_finalized = True
    return None, None


async def download_and_log_task_output(
    *,
    internal_user_id,
    username,
    prompt,
    task_type,
    registry_task_id,
    backend_task_id,
    saved_input_images,
    is_video,
    allow_contribute,
    extra_outputs: Optional[dict] = None,
    billing_resolution: Optional[str],
    requested_duration: Optional[int],
):
    from src.core.task_core import TaskPersistencePostprocessPlan
    from src.core.task_core_persistence import persist_successful_task_result

    return await persist_successful_task_result(
        backend_task_id=backend_task_id,
        registry_task_id=registry_task_id,
        internal_user_id=internal_user_id,
        username=username,
        prompt=prompt,
        task_type=task_type,
        input_images=saved_input_images,
        allow_contribute=allow_contribute,
        is_video=is_video,
        extra_outputs=extra_outputs,
        billing_resolution=billing_resolution,
        requested_duration=requested_duration,
        postprocess_plan=TaskPersistencePostprocessPlan(
            source="bot",
            refresh_user_group_after_log=True,
        ),
    )


async def present_completed_task_result(
    *,
    context,
    chat_id,
    persistence_result,
    prompt,
    task_type,
    task_id,
    is_video,
    send_result,
    reply_markup,
    status_msg,
    delete_status,
    caption=None,
    allow_contribute=True,
    result_meta: dict | None = None,
    lang: str = "zh",
):
    if send_result:
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
            result_meta=result_meta,
            lang=lang,
        )

    await cleanup_completion_status_message(
        status_msg=status_msg,
        delete_status=delete_status,
        send_result=send_result,
    )

    return persistence_result.media_bytes, persistence_result.output_file


async def handle_task_completion(
    *,
    context,
    chat_id,
    internal_user_id,
    prompt,
    task_type,
    registry_task_id,
    backend_task_id,
    saved_input_images,
    user_logger,
    is_video,
    send_result,
    reply_markup,
    status_msg,
    delete_status,
    caption=None,
    allow_contribute=True,
    result_meta: dict | None = None,
    extra_outputs: dict | None = None,
    billing_resolution: Optional[str] = None,
    requested_duration: Optional[int] = None,
    lang: str = "zh",
):
    persisted_extra_outputs = merge_wan22_history_context_into_extra_outputs(
        task_type=task_type,
        extra_outputs=extra_outputs,
        metadata=result_meta,
    )
    persisted_extra_outputs = merge_ltx_history_context_into_extra_outputs(
        task_type=task_type,
        extra_outputs=persisted_extra_outputs,
        metadata=result_meta,
    )
    persisted_extra_outputs = merge_qqcc_regenerate_context_into_extra_outputs(
        extra_outputs=persisted_extra_outputs,
        metadata=result_meta,
    )
    persistence_result = await download_and_log_task_output(
        internal_user_id=internal_user_id,
        username=user_logger.username,
        prompt=prompt,
        task_type=task_type,
        registry_task_id=registry_task_id,
        backend_task_id=backend_task_id,
        saved_input_images=saved_input_images,
        is_video=is_video,
        allow_contribute=allow_contribute,
        extra_outputs=persisted_extra_outputs,
        billing_resolution=billing_resolution,
        requested_duration=requested_duration,
    )
    return await present_completed_task_result(
        context=context,
        chat_id=chat_id,
        persistence_result=persistence_result,
        prompt=prompt,
        task_type=task_type,
        task_id=registry_task_id,
        is_video=is_video,
        send_result=send_result,
        reply_markup=reply_markup,
        status_msg=status_msg,
        delete_status=delete_status,
        caption=caption,
        allow_contribute=allow_contribute,
        result_meta=result_meta,
        lang=lang,
    )
