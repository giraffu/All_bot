import uuid
from typing import Callable, Optional

from asgi_correlation_id import correlation_id

from src.core.billing_core import get_user_priority_and_identity
from src.core.task_core import (
    ConcurrencyLimitError,
    CoreDomainError,
    InsufficientCreditsError,
    process_and_submit_task,
)
from src.logger import UserLogger
from src.services.image_service import image_service
from src.services import task_service_completion as task_service_completion_helpers
from src.services import task_service_finalize as task_service_finalize_helpers
from src.services.task_service_message_support import with_submitted_status
from src.services.task_service_types import (
    BotTaskCompletionContext,
    BotTaskFlowContext,
    BotTaskMessageSpec,
    BotTaskSubmissionContext,
)
from src.services.tg_task_runtime import get_or_send_status_message
from src.utils import robust_edit_text, robust_reply_text


def mark_task_submission_succeeded(runtime_state, result: dict) -> list[str]:
    runtime_state.task_submitted = True
    runtime_state.actual_cost = result["cost"]
    runtime_state.registry_task_id = result["registry_task_id"]
    return result["saved_inputs"]


async def submit_bot_task(
    *,
    submission: BotTaskSubmissionContext,
) -> tuple[str, list[str]]:
    task_id = str(uuid.uuid4())
    correlation_id.set(task_id)

    result = await process_and_submit_task(
        user_id=submission.internal_user_id,
        username=submission.username,
        task_type=submission.task_type,
        inputs=submission.inputs,
        task_id=task_id,
        client_type="bot",
        source_post_id=submission.source_post_id,
        deduct_quota=submission.deduct_quota,
    )
    saved_inputs = mark_task_submission_succeeded(submission.runtime_state, result)
    return task_id, saved_inputs


async def send_initial_task_status(
    *,
    context,
    update,
    chat_id,
    status_msg_id,
    message_spec: BotTaskMessageSpec,
):
    if update is not None:
        return await robust_reply_text(
            update.effective_message,
            message_spec.initial_status_text,
        )
    return await get_or_send_status_message(
        context, chat_id, status_msg_id, message_spec.initial_status_text
    )


async def update_submitted_task_status(
    *,
    status_msg,
    message_spec: BotTaskMessageSpec,
):
    if message_spec.submitted_status_text:
        await robust_edit_text(status_msg, message_spec.submitted_status_text)
    elif message_spec.progress_wait_text:
        await robust_edit_text(status_msg, message_spec.progress_wait_text)


async def prepare_and_submit_bot_task(
    *,
    context,
    update,
    chat_id,
    status_msg_id=None,
    message_spec: BotTaskMessageSpec,
    submitted_status_builder: Optional[Callable[[int], str]] = None,
    submission: BotTaskSubmissionContext,
):
    status_msg = await send_initial_task_status(
        context=context,
        update=update,
        chat_id=chat_id,
        status_msg_id=status_msg_id,
        message_spec=message_spec,
    )
    task_id, saved_inputs = await submit_bot_task(
        submission=submission,
    )
    if submitted_status_builder is not None:
        message_spec = with_submitted_status(
            message_spec,
            submitted_status_builder(submission.runtime_state.actual_cost),
        )
    await update_submitted_task_status(
        status_msg=status_msg,
        message_spec=message_spec,
    )
    return status_msg, task_id, saved_inputs, message_spec


async def run_bot_task_submission_stage(
    *,
    context,
    update,
    chat_id,
    status_msg_id,
    message_spec: BotTaskMessageSpec,
    submitted_status_builder: Optional[Callable[[int], str]],
    submission: BotTaskSubmissionContext,
):
    return await prepare_and_submit_bot_task(
        context=context,
        update=update,
        chat_id=chat_id,
        status_msg_id=status_msg_id,
        message_spec=message_spec,
        submitted_status_builder=submitted_status_builder,
        submission=submission,
    )


async def run_bot_task_monitor_stage(
    *,
    task_id: str,
    status_msg,
    is_video: bool,
    internal_user_id: int,
):
    return await task_service_completion_helpers.monitor_submitted_bot_task(
        task_id=task_id,
        status_msg=status_msg,
        is_video=is_video,
        internal_user_id=internal_user_id,
        monitor_func=image_service.monitor_progress,
        get_user_priority_and_identity_func=get_user_priority_and_identity,
        monitor_bot_task_progress_func=(
            task_service_completion_helpers.monitor_bot_task_progress
        ),
    )


async def run_bot_task_completion_stage(
    *,
    context,
    chat_id,
    status_msg,
    runtime_state,
    internal_user_id: int,
    username: str,
    prompt: str,
    task_type: str,
    task_id: str,
    saved_inputs: list[str],
    final_info,
    is_video: bool,
    message_spec: BotTaskMessageSpec,
    send_result: bool,
    reply_markup,
    delete_status: bool,
    allow_contribute: bool,
    billing_resolution: Optional[str],
    requested_duration: Optional[int],
    missing_output_should_refund: bool,
):
    return await task_service_completion_helpers.complete_monitored_bot_task(
        completion=BotTaskCompletionContext(
            context=context,
            chat_id=chat_id,
            status_msg=status_msg,
            runtime_state=runtime_state,
            internal_user_id=internal_user_id,
            username=username,
            prompt=prompt,
            task_type=task_type,
            task_id=task_id,
            saved_input_images=saved_inputs,
            final_info=final_info,
            is_video=is_video,
            message_spec=message_spec,
            user_logger=UserLogger(internal_user_id, username),
            send_result=send_result,
            reply_markup=reply_markup,
            delete_status=delete_status,
            allow_contribute=allow_contribute,
            billing_resolution=billing_resolution,
            requested_duration=requested_duration,
            missing_output_should_refund=missing_output_should_refund,
        ),
    )


def should_refund_for_unexpected_bot_error(
    *,
    runtime_state,
    deduct_quota: bool,
    unexpected_should_refund: Optional[Callable],
) -> bool:
    if unexpected_should_refund is not None:
        return unexpected_should_refund(runtime_state)
    return deduct_quota and runtime_state.task_submitted


async def cleanup_bot_task_flow(
    *,
    internal_user_id: int,
    runtime_state,
    cleanup_enabled: bool,
    cleanup_paths: Optional[list[str]],
    cleanup_files_func,
):
    await task_service_finalize_helpers.cleanup_runtime_state_if_needed(
        internal_user_id=internal_user_id,
        registry_task_id=runtime_state.registry_task_id,
        release_lock=runtime_state.task_submitted,
        terminal_state_finalized=runtime_state.terminal_state_finalized,
    )
    if cleanup_enabled and cleanup_paths:
        cleanup_files_func(cleanup_paths)


async def run_bot_task_application(
    *,
    flow: BotTaskFlowContext,
) -> tuple[bytes | None, str | None]:
    media_bytes = None
    full_output_path = None
    submission = BotTaskSubmissionContext(
        runtime_state=flow.runtime_state,
        internal_user_id=flow.internal_user_id,
        username=flow.username,
        task_type=flow.task_type,
        inputs=flow.inputs,
        source_post_id=flow.source_post_id,
        deduct_quota=flow.deduct_quota,
    )

    try:
        status_msg, task_id, saved_inputs, message_spec = await run_bot_task_submission_stage(
            context=flow.context,
            update=flow.update,
            chat_id=flow.chat_id,
            status_msg_id=flow.status_msg_id,
            message_spec=flow.message_spec,
            submitted_status_builder=flow.submitted_status_builder,
            submission=submission,
        )

        final_info = await run_bot_task_monitor_stage(
            task_id=task_id,
            status_msg=status_msg,
            is_video=flow.is_video,
            internal_user_id=flow.internal_user_id,
        )

        media_bytes, full_output_path = await run_bot_task_completion_stage(
            context=flow.context,
            chat_id=flow.chat_id,
            status_msg=status_msg,
            runtime_state=flow.runtime_state,
            internal_user_id=flow.internal_user_id,
            username=flow.username,
            prompt=flow.prompt,
            task_type=flow.task_type,
            task_id=task_id,
            saved_inputs=saved_inputs,
            final_info=final_info,
            is_video=flow.is_video,
            message_spec=message_spec,
            send_result=flow.send_result,
            reply_markup=flow.reply_markup,
            delete_status=flow.delete_status,
            allow_contribute=flow.allow_contribute,
            billing_resolution=flow.billing_resolution,
            requested_duration=flow.requested_duration,
            missing_output_should_refund=flow.missing_output_should_refund,
        )

    except ConcurrencyLimitError as e:
        await task_service_finalize_helpers.send_bot_warning(flow.context, flow.chat_id, e)
        return None, None
    except InsufficientCreditsError as e:
        await task_service_finalize_helpers.send_bot_warning(flow.context, flow.chat_id, e)
        return None, None
    except CoreDomainError as e:
        if str(e) == "cancelled":
            return await task_service_finalize_helpers.handle_bot_cancelled_exception(
                status_msg=locals().get("status_msg"),
                runtime_state=flow.runtime_state,
                internal_user_id=flow.internal_user_id,
                username=flow.username,
                message_spec=locals().get("message_spec", flow.message_spec),
                deduct_quota=flow.deduct_quota,
            )
        await task_service_finalize_helpers.send_bot_domain_error(
            flow.context, flow.chat_id, e
        )
        return None, None
    except Exception as e:
        return await task_service_finalize_helpers.handle_bot_unexpected_exception(
            context=flow.context,
            chat_id=flow.chat_id,
            status_msg=locals().get("status_msg") if flow.prefer_edit_status else None,
            runtime_state=flow.runtime_state,
            internal_user_id=flow.internal_user_id,
            username=flow.username,
            error=e,
            log_message=flow.unexpected_error_log_message.format(
                internal_user_id=flow.internal_user_id,
                error=e,
            ),
            should_refund=should_refund_for_unexpected_bot_error(
                runtime_state=flow.runtime_state,
                deduct_quota=flow.deduct_quota,
                unexpected_should_refund=flow.unexpected_should_refund,
            ),
            generic_error_prefix=flow.unexpected_error_prefix,
            prefer_edit_status=flow.prefer_edit_status,
            refund_suffix_mode=flow.refund_suffix_mode,
        )
    finally:
        await cleanup_bot_task_flow(
            internal_user_id=flow.internal_user_id,
            runtime_state=flow.runtime_state,
            cleanup_enabled=flow.cleanup_enabled,
            cleanup_paths=flow.cleanup_paths,
            cleanup_files_func=flow.cleanup_files_func,
        )

    return media_bytes, full_output_path


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
    cleanup_files_func=None,
) -> tuple[bytes | None, str | None]:
    return await run_bot_task_application(
        flow=BotTaskFlowContext(
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
            cleanup_files_func=cleanup_files_func,
        )
    )
