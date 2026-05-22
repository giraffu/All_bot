from src.services.task_service_completion import (
    complete_monitored_bot_task,
    download_and_log_task_output,
    handle_task_completion,
    monitor_submitted_bot_task,
    monitor_bot_task_progress,
)
from src.services.task_service_finalize import (
    cleanup_runtime_state_if_needed,
    finalize_cancelled_task_for_bot,
    finalize_failed_task_for_bot,
    send_bot_domain_error,
    send_bot_warning,
)
from src.services.task_service_flow import (
    prepare_and_submit_bot_task,
    run_bot_task_flow,
    send_initial_task_status,
    submit_bot_task,
    update_submitted_task_status,
)
from src.services.tg_task_runtime import (
    cleanup_completion_status_message,
    send_result_media,
)


async def send_result_media_seam(
    *,
    context,
    chat_id,
    media_bytes,
    is_video,
    caption,
    task_type,
    task_id,
    allow_contribute,
    reply_markup,
    prompt,
):
    return await send_result_media(
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


async def cleanup_completion_status_message_seam(
    *,
    status_msg,
    delete_status,
    send_result,
):
    await cleanup_completion_status_message(
        status_msg=status_msg,
        delete_status=delete_status,
        send_result=send_result,
    )


async def finalize_cancelled_task_for_bot_seam(
    *,
    status_msg,
    internal_user_id,
    username,
    cost,
    task_submitted,
    registry_task_id,
    explicit_user_message,
    edit_text_func,
):
    from src.core.task_core import finalize_task_cancellation

    return await finalize_cancelled_task_for_bot(
        status_msg=status_msg,
        internal_user_id=internal_user_id,
        username=username,
        cost=cost,
        task_submitted=task_submitted,
        registry_task_id=registry_task_id,
        explicit_user_message=explicit_user_message,
        finalize_task_cancellation_func=finalize_task_cancellation,
        edit_text_func=edit_text_func,
    )


async def finalize_failed_task_for_bot_seam(
    *,
    context,
    chat_id,
    status_msg,
    internal_user_id,
    username,
    cost,
    should_refund,
    registry_task_id,
    release_lock,
    message_prefix="❌",
    prefer_edit_status=False,
    fallback_to_send_message=True,
    explicit_user_message=None,
    error=None,
    generic_error_prefix=None,
    refund_suffix_mode="if_refunded",
    edit_text_func,
    send_message_func,
):
    from src.core.task_core import finalize_task_failure

    return await finalize_failed_task_for_bot(
        context=context,
        chat_id=chat_id,
        status_msg=status_msg,
        internal_user_id=internal_user_id,
        username=username,
        cost=cost,
        should_refund=should_refund,
        registry_task_id=registry_task_id,
        release_lock=release_lock,
        message_prefix=message_prefix,
        prefer_edit_status=prefer_edit_status,
        fallback_to_send_message=fallback_to_send_message,
        explicit_user_message=explicit_user_message,
        error=error,
        generic_error_prefix=generic_error_prefix,
        refund_suffix_mode=refund_suffix_mode,
        finalize_task_failure_func=finalize_task_failure,
        edit_text_func=edit_text_func,
        send_message_func=send_message_func,
    )


async def send_bot_warning_seam(context, chat_id, error, *, send_message_func):
    await send_bot_warning(
        context,
        chat_id,
        error,
        send_message_func=send_message_func,
    )


async def send_bot_domain_error_seam(context, chat_id, error, *, send_message_func):
    await send_bot_domain_error(
        context,
        chat_id,
        error,
        send_message_func=send_message_func,
    )


async def cleanup_runtime_state_if_needed_seam(
    *,
    internal_user_id,
    registry_task_id,
    release_lock,
    terminal_state_finalized,
):
    from src.core.task_core import cleanup_task_runtime_state

    await cleanup_runtime_state_if_needed(
        internal_user_id=internal_user_id,
        registry_task_id=registry_task_id,
        release_lock=release_lock,
        terminal_state_finalized=terminal_state_finalized,
        cleanup_task_runtime_state_func=cleanup_task_runtime_state,
    )


async def send_initial_task_status_seam(
    *,
    context,
    update,
    chat_id,
    status_msg_id,
    message_spec,
    get_or_send_status_msg_func,
    reply_text_func,
):
    return await send_initial_task_status(
        context=context,
        update=update,
        chat_id=chat_id,
        status_msg_id=status_msg_id,
        message_spec=message_spec,
        get_or_send_status_msg_func=get_or_send_status_msg_func,
        reply_text_func=reply_text_func,
    )


async def submit_bot_task_seam(
    *,
    runtime_state,
    internal_user_id,
    username,
    task_type,
    inputs,
    source_post_id=None,
    deduct_quota=True,
):
    from src.core.task_core import process_and_submit_task

    return await submit_bot_task(
        runtime_state=runtime_state,
        internal_user_id=internal_user_id,
        username=username,
        task_type=task_type,
        inputs=inputs,
        source_post_id=source_post_id,
        deduct_quota=deduct_quota,
        process_and_submit_task_func=process_and_submit_task,
    )


async def update_submitted_task_status_seam(
    *,
    status_msg,
    message_spec,
    edit_text_func,
):
    await update_submitted_task_status(
        status_msg=status_msg,
        message_spec=message_spec,
        edit_text_func=edit_text_func,
    )


async def prepare_and_submit_bot_task_seam(
    *,
    context,
    update,
    chat_id,
    status_msg_id=None,
    message_spec=None,
    submitted_status_builder=None,
    runtime_state,
    internal_user_id,
    username,
    task_type,
    inputs,
    source_post_id=None,
    deduct_quota=True,
    with_submitted_status_func,
    get_or_send_status_msg_func,
    send_initial_task_status_func,
    submit_bot_task_func,
    update_submitted_task_status_func,
):
    return await prepare_and_submit_bot_task(
        context=context,
        update=update,
        chat_id=chat_id,
        status_msg_id=status_msg_id,
        message_spec=message_spec,
        submitted_status_builder=submitted_status_builder,
        runtime_state=runtime_state,
        internal_user_id=internal_user_id,
        username=username,
        task_type=task_type,
        inputs=inputs,
        source_post_id=source_post_id,
        deduct_quota=deduct_quota,
        with_submitted_status_func=with_submitted_status_func,
        get_or_send_status_msg_func=get_or_send_status_msg_func,
        send_initial_task_status_func=send_initial_task_status_func,
        submit_bot_task_func=submit_bot_task_func,
        update_submitted_task_status_func=update_submitted_task_status_func,
    )


async def run_bot_task_flow_seam(
    *,
    context,
    chat_id,
    runtime_state,
    internal_user_id,
    username,
    task_type,
    inputs,
    prompt,
    is_video,
    message_spec,
    update=None,
    status_msg_id=None,
    submitted_status_builder=None,
    source_post_id=None,
    deduct_quota=True,
    send_result=True,
    reply_markup=None,
    delete_status=True,
    allow_contribute=True,
    billing_resolution=None,
    requested_duration=None,
    missing_output_should_refund=True,
    prefer_edit_status=False,
    refund_suffix_mode="if_refunded",
    unexpected_should_refund=None,
    unexpected_error_log_message="",
    unexpected_error_prefix="",
    cleanup_paths=None,
    cleanup_enabled=True,
    with_submitted_status_func=None,
    get_or_send_status_msg_func=None,
    send_result_media_func=None,
    cleanup_completion_status_message_func=None,
    cleanup_files_func=None,
    prepare_and_submit_bot_task_func=None,
    monitor_submitted_bot_task_func=None,
    complete_monitored_bot_task_func=None,
    send_bot_warning_func=None,
    send_bot_domain_error_func=None,
    handle_bot_cancelled_exception_func=None,
    handle_bot_unexpected_exception_func=None,
    cleanup_runtime_state_if_needed_func=None,
):
    return await run_bot_task_flow(
        context=context,
        chat_id=chat_id,
        runtime_state=runtime_state,
        internal_user_id=internal_user_id,
        username=username,
        task_type=task_type,
        inputs=inputs,
        prompt=prompt,
        is_video=is_video,
        message_spec=message_spec,
        update=update,
        status_msg_id=status_msg_id,
        submitted_status_builder=submitted_status_builder,
        source_post_id=source_post_id,
        deduct_quota=deduct_quota,
        send_result=send_result,
        reply_markup=reply_markup,
        delete_status=delete_status,
        allow_contribute=allow_contribute,
        billing_resolution=billing_resolution,
        requested_duration=requested_duration,
        missing_output_should_refund=missing_output_should_refund,
        prefer_edit_status=prefer_edit_status,
        refund_suffix_mode=refund_suffix_mode,
        unexpected_should_refund=unexpected_should_refund,
        unexpected_error_log_message=unexpected_error_log_message,
        unexpected_error_prefix=unexpected_error_prefix,
        cleanup_paths=cleanup_paths,
        cleanup_enabled=cleanup_enabled,
        with_submitted_status_func=with_submitted_status_func,
        get_or_send_status_msg_func=get_or_send_status_msg_func,
        send_result_media_func=send_result_media_func,
        cleanup_completion_status_message_func=cleanup_completion_status_message_func,
        cleanup_files_func=cleanup_files_func,
        prepare_and_submit_bot_task_func=prepare_and_submit_bot_task_func,
        monitor_submitted_bot_task_func=monitor_submitted_bot_task_func,
        complete_monitored_bot_task_func=complete_monitored_bot_task_func,
        send_bot_warning_func=send_bot_warning_func,
        send_bot_domain_error_func=send_bot_domain_error_func,
        handle_bot_cancelled_exception_func=handle_bot_cancelled_exception_func,
        handle_bot_unexpected_exception_func=handle_bot_unexpected_exception_func,
        cleanup_runtime_state_if_needed_func=cleanup_runtime_state_if_needed_func,
    )


async def monitor_submitted_bot_task_seam(
    *,
    task_id,
    status_msg,
    is_video,
    internal_user_id,
    monitor_func,
    monitor_bot_task_progress_func,
):
    from src.core.billing_core import get_user_priority_and_identity

    return await monitor_submitted_bot_task(
        task_id=task_id,
        status_msg=status_msg,
        is_video=is_video,
        internal_user_id=internal_user_id,
        monitor_func=monitor_func,
        get_user_priority_and_identity_func=get_user_priority_and_identity,
        monitor_bot_task_progress_func=monitor_bot_task_progress_func,
    )


async def monitor_task_progress_seam(
    task_id,
    status_msg,
    *,
    is_video,
    monitor_func,
    identity_str=None,
    user_group=None,
    edit_status_text_func,
):
    return await monitor_bot_task_progress(
        task_id,
        status_msg,
        is_video=is_video,
        monitor_func=monitor_func,
        identity_str=identity_str,
        user_group=user_group,
        edit_status_text_func=edit_status_text_func,
    )


async def complete_monitored_bot_task_seam(
    *,
    context,
    chat_id,
    status_msg,
    runtime_state,
    internal_user_id,
    username,
    prompt,
    task_type,
    task_id,
    saved_input_images,
    user_logger,
    final_info,
    is_video,
    send_result=True,
    reply_markup=None,
    delete_status=True,
    caption=None,
    allow_contribute=True,
    billing_resolution=None,
    requested_duration=None,
    message_spec=None,
    missing_output_should_refund=True,
    send_result_media_func,
    cleanup_completion_status_message_func,
    handle_task_completion_func,
    finalize_failed_task_for_bot_func,
):
    return await complete_monitored_bot_task(
        context=context,
        chat_id=chat_id,
        status_msg=status_msg,
        runtime_state=runtime_state,
        internal_user_id=internal_user_id,
        username=username,
        user_logger=user_logger,
        prompt=prompt,
        task_type=task_type,
        task_id=task_id,
        saved_input_images=saved_input_images,
        final_info=final_info,
        is_video=is_video,
        send_result=send_result,
        reply_markup=reply_markup,
        delete_status=delete_status,
        caption=caption,
        allow_contribute=allow_contribute,
        billing_resolution=billing_resolution,
        requested_duration=requested_duration,
        message_spec=message_spec,
        missing_output_should_refund=missing_output_should_refund,
        send_result_media_func=send_result_media_func,
        cleanup_completion_status_message_func=cleanup_completion_status_message_func,
        handle_task_completion_func=handle_task_completion_func,
        finalize_failed_task_for_bot_func=finalize_failed_task_for_bot_func,
    )


async def handle_task_completion_seam(
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
    billing_resolution=None,
    requested_duration=None,
    send_result_media_func,
    cleanup_completion_status_message_func,
    download_and_log_task_output_func,
):
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
        caption=caption,
        allow_contribute=allow_contribute,
        billing_resolution=billing_resolution,
        requested_duration=requested_duration,
        send_result_media_func=send_result_media_func,
        cleanup_completion_status_message_func=cleanup_completion_status_message_func,
        download_and_log_task_output_func=download_and_log_task_output_func,
    )


async def download_and_log_task_output_seam(
    *,
    internal_user_id,
    username,
    prompt,
    task_type,
    task_id,
    saved_input_images,
    is_video,
    allow_contribute,
    billing_resolution,
    requested_duration,
):
    return await download_and_log_task_output(
        internal_user_id=internal_user_id,
        username=username,
        prompt=prompt,
        task_type=task_type,
        task_id=task_id,
        saved_input_images=saved_input_images,
        is_video=is_video,
        allow_contribute=allow_contribute,
        billing_resolution=billing_resolution,
        requested_duration=requested_duration,
    )
