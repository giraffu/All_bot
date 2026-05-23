import uuid
import inspect
from typing import Callable, Optional

from asgi_correlation_id import correlation_id

from src.core.task_core import (
    ConcurrencyLimitError,
    CoreDomainError,
    InsufficientCreditsError,
    process_and_submit_task,
)
from src.logger import UserLogger
from src.services.image_service import image_service
from src.services.task_service_completion import (
    complete_monitored_bot_task,
    monitor_submitted_bot_task,
)
from src.services.task_service_finalize import (
    cleanup_runtime_state_if_needed,
    handle_bot_cancelled_exception,
    handle_bot_unexpected_exception,
    send_bot_domain_error,
    send_bot_warning,
)
from src.services.task_service_types import BotTaskMessageSpec
from src.utils import robust_edit_text, robust_reply_text


async def _call_async_with_supported_kwargs(func, **kwargs):
    signature = inspect.signature(func)
    if any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    ):
        return await func(**kwargs)

    supported_kwargs = {
        key: value
        for key, value in kwargs.items()
        if key in signature.parameters
    }
    return await func(**supported_kwargs)


def mark_task_submission_succeeded(runtime_state, result: dict) -> list[str]:
    runtime_state.task_submitted = True
    runtime_state.actual_cost = result["cost"]
    runtime_state.registry_task_id = result["registry_task_id"]
    return result["saved_inputs"]


async def submit_bot_task(
    *,
    runtime_state,
    internal_user_id,
    username,
    task_type,
    inputs,
    source_post_id=None,
    deduct_quota=True,
    process_and_submit_task_func=None,
) -> tuple[str, list[str]]:
    task_id = str(uuid.uuid4())
    correlation_id.set(task_id)
    process_and_submit_task_func = process_and_submit_task_func or process_and_submit_task

    result = await process_and_submit_task_func(
        user_id=internal_user_id,
        username=username,
        task_type=task_type,
        inputs=inputs,
        task_id=task_id,
        client_type="bot",
        source_post_id=source_post_id,
        deduct_quota=deduct_quota,
    )
    saved_inputs = mark_task_submission_succeeded(runtime_state, result)
    return task_id, saved_inputs


async def send_initial_task_status(
    *,
    context,
    update,
    chat_id,
    status_msg_id,
    message_spec: BotTaskMessageSpec,
    get_or_send_status_msg_func,
    reply_text_func=None,
):
    reply_text_func = reply_text_func or robust_reply_text
    if update is not None:
        return await reply_text_func(update.effective_message, message_spec.initial_status_text)
    return await get_or_send_status_msg_func(
        context, chat_id, status_msg_id, message_spec.initial_status_text
    )


async def update_submitted_task_status(
    *,
    status_msg,
    message_spec: BotTaskMessageSpec,
    edit_text_func=None,
):
    edit_text_func = edit_text_func or robust_edit_text
    if message_spec.submitted_status_text:
        await edit_text_func(status_msg, message_spec.submitted_status_text)
    elif message_spec.progress_wait_text:
        await edit_text_func(status_msg, message_spec.progress_wait_text)


async def prepare_and_submit_bot_task(
    *,
    context,
    update,
    chat_id,
    status_msg_id=None,
    message_spec: BotTaskMessageSpec,
    submitted_status_builder: Optional[Callable[[int], str]] = None,
    runtime_state=None,
    internal_user_id=None,
    username=None,
    task_type=None,
    inputs=None,
    source_post_id=None,
    deduct_quota=True,
    with_submitted_status_func=None,
    get_or_send_status_msg_func=None,
    send_initial_task_status_func=None,
    submit_bot_task_func=None,
    update_submitted_task_status_func=None,
    reply_text_func=None,
    edit_text_func=None,
):
    send_initial_task_status_func = (
        send_initial_task_status_func or send_initial_task_status
    )
    submit_bot_task_func = submit_bot_task_func or submit_bot_task
    update_submitted_task_status_func = (
        update_submitted_task_status_func or update_submitted_task_status
    )
    with_submitted_status_func = with_submitted_status_func or (lambda spec, text: spec)

    status_msg = await _call_async_with_supported_kwargs(
        send_initial_task_status_func,
        context=context,
        update=update,
        chat_id=chat_id,
        status_msg_id=status_msg_id,
        message_spec=message_spec,
        get_or_send_status_msg_func=get_or_send_status_msg_func,
        reply_text_func=reply_text_func,
    )
    task_id, saved_inputs = await _call_async_with_supported_kwargs(
        submit_bot_task_func,
        runtime_state=runtime_state,
        internal_user_id=internal_user_id,
        username=username,
        task_type=task_type,
        inputs=inputs,
        source_post_id=source_post_id,
        deduct_quota=deduct_quota,
    )
    if submitted_status_builder is not None:
        message_spec = with_submitted_status_func(
            message_spec,
            submitted_status_builder(runtime_state.actual_cost),
        )
    await _call_async_with_supported_kwargs(
        update_submitted_task_status_func,
        status_msg=status_msg,
        message_spec=message_spec,
        edit_text_func=edit_text_func,
    )
    return status_msg, task_id, saved_inputs, message_spec


async def run_bot_task_flow(
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
    message_spec: BotTaskMessageSpec,
    update=None,
    status_msg_id=None,
    submitted_status_builder: Optional[Callable[[int], str]] = None,
    source_post_id=None,
    deduct_quota=True,
    send_result=True,
    reply_markup=None,
    delete_status=True,
    allow_contribute=True,
    billing_resolution: Optional[str] = None,
    requested_duration: Optional[int] = None,
    missing_output_should_refund: bool = True,
    prefer_edit_status=False,
    refund_suffix_mode="if_refunded",
    unexpected_should_refund: Optional[Callable] = None,
    unexpected_error_log_message: str = "",
    unexpected_error_prefix: str = "出错了",
    cleanup_paths: Optional[list[str]] = None,
    cleanup_enabled: bool = True,
    with_submitted_status_func=None,
    get_or_send_status_msg_func=None,
    send_result_media_func=None,
    cleanup_completion_status_message_func=None,
    cleanup_files_func=None,
    prepare_and_submit_bot_task_func=None,
    send_initial_task_status_func=None,
    submit_bot_task_func=None,
    update_submitted_task_status_func=None,
    reply_text_func=None,
    edit_text_func=None,
    monitor_submitted_bot_task_func=None,
    get_user_priority_and_identity_func=None,
    monitor_bot_task_progress_func=None,
    edit_status_text_func=None,
    complete_monitored_bot_task_func=None,
    send_bot_warning_func=None,
    send_bot_domain_error_func=None,
    handle_bot_cancelled_exception_func=None,
    handle_bot_unexpected_exception_func=None,
    cleanup_runtime_state_if_needed_func=None,
) -> tuple[bytes | None, str | None]:
    media_bytes = None
    full_output_path = None
    prepare_and_submit_bot_task_func = (
        prepare_and_submit_bot_task_func or prepare_and_submit_bot_task
    )
    monitor_submitted_bot_task_func = (
        monitor_submitted_bot_task_func or monitor_submitted_bot_task
    )
    complete_monitored_bot_task_func = (
        complete_monitored_bot_task_func or complete_monitored_bot_task
    )
    send_bot_warning_func = send_bot_warning_func or send_bot_warning
    send_bot_domain_error_func = send_bot_domain_error_func or send_bot_domain_error
    handle_bot_cancelled_exception_func = (
        handle_bot_cancelled_exception_func or handle_bot_cancelled_exception
    )
    handle_bot_unexpected_exception_func = (
        handle_bot_unexpected_exception_func or handle_bot_unexpected_exception
    )
    cleanup_runtime_state_if_needed_func = (
        cleanup_runtime_state_if_needed_func or cleanup_runtime_state_if_needed
    )

    try:
        status_msg, task_id, saved_inputs, message_spec = (
            await _call_async_with_supported_kwargs(
                prepare_and_submit_bot_task_func,
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
                reply_text_func=reply_text_func,
                edit_text_func=edit_text_func,
            )
        )

        final_info = await _call_async_with_supported_kwargs(
            monitor_submitted_bot_task_func,
            task_id=task_id,
            status_msg=status_msg,
            is_video=is_video,
            internal_user_id=internal_user_id,
            monitor_func=image_service.monitor_progress,
            get_user_priority_and_identity_func=get_user_priority_and_identity_func,
            monitor_bot_task_progress_func=monitor_bot_task_progress_func,
            edit_status_text_func=edit_status_text_func,
        )

        media_bytes, full_output_path = await _call_async_with_supported_kwargs(
            complete_monitored_bot_task_func,
            context=context,
            chat_id=chat_id,
            status_msg=status_msg,
            runtime_state=runtime_state,
            internal_user_id=internal_user_id,
            username=username,
            user_logger=UserLogger(internal_user_id, username),
            prompt=prompt,
            task_type=task_type,
            task_id=task_id,
            saved_input_images=saved_inputs,
            final_info=final_info,
            is_video=is_video,
            send_result=send_result,
            reply_markup=reply_markup,
            delete_status=delete_status,
            allow_contribute=allow_contribute,
            billing_resolution=billing_resolution,
            requested_duration=requested_duration,
            message_spec=message_spec,
            missing_output_should_refund=missing_output_should_refund,
            send_result_media_func=send_result_media_func,
            cleanup_completion_status_message_func=cleanup_completion_status_message_func,
        )

    except ConcurrencyLimitError as e:
        await send_bot_warning_func(context, chat_id, e)
        return None, None
    except InsufficientCreditsError as e:
        await send_bot_warning_func(context, chat_id, e)
        return None, None
    except CoreDomainError as e:
        if str(e) == "cancelled":
            return await handle_bot_cancelled_exception_func(
                status_msg=locals().get("status_msg"),
                runtime_state=runtime_state,
                internal_user_id=internal_user_id,
                username=username,
                message_spec=locals().get("message_spec", message_spec),
                deduct_quota=deduct_quota,
            )
        await send_bot_domain_error_func(context, chat_id, e)
        return None, None
    except Exception as e:
        return await handle_bot_unexpected_exception_func(
            context=context,
            chat_id=chat_id,
            status_msg=locals().get("status_msg") if prefer_edit_status else None,
            runtime_state=runtime_state,
            internal_user_id=internal_user_id,
            username=username,
            error=e,
            log_message=unexpected_error_log_message.format(
                internal_user_id=internal_user_id,
                error=e,
            ),
            should_refund=(
                unexpected_should_refund(runtime_state)
                if unexpected_should_refund is not None
                else deduct_quota and runtime_state.task_submitted
            ),
            generic_error_prefix=unexpected_error_prefix,
            prefer_edit_status=prefer_edit_status,
            refund_suffix_mode=refund_suffix_mode,
        )
    finally:
        await cleanup_runtime_state_if_needed_func(
            internal_user_id=internal_user_id,
            registry_task_id=runtime_state.registry_task_id,
            release_lock=runtime_state.task_submitted,
            terminal_state_finalized=runtime_state.terminal_state_finalized,
        )
        if cleanup_enabled and cleanup_paths:
            cleanup_files_func(cleanup_paths)

    return media_bytes, full_output_path
