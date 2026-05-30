import uuid
from dataclasses import dataclass
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
from src.services.task_service_message_support import (
    resolve_context_lang,
    with_submitted_status,
)
from src.services.task_service_types import (
    BotTaskCancelled,
    BotTaskCompletionContext,
    BotTaskFlowContext,
    BotTaskMessageSpec,
    BotTaskSubmissionContext,
)
from src.services.tg_task_runtime import (
    get_or_send_status_message,
    build_cancel_task_markup,
)
from src.services.task_lifecycle_runner import run_monitored_task_lifecycle
from src.utils import robust_edit_text, robust_reply_text


@dataclass
class _BotTaskExecutionState:
    status_msg: object | None = None
    registry_task_id: str | None = None
    backend_task_id: str | None = None
    saved_inputs: list[str] | None = None
    message_spec: BotTaskMessageSpec | None = None


def mark_task_submission_succeeded(runtime_state, result: dict) -> list[str]:
    runtime_state.task_submitted = True
    runtime_state.actual_cost = result["cost"]
    runtime_state.registry_task_id = result["registry_task_id"]
    runtime_state.backend_task_id = result.get("backend_task_id") or result["registry_task_id"]
    return result["saved_inputs"]


async def submit_bot_task(
    *,
    submission: BotTaskSubmissionContext,
) -> tuple[str, str, list[str]]:
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
    backend_task_id = submission.runtime_state.backend_task_id or task_id
    return task_id, backend_task_id, saved_inputs


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
    registry_task_id: Optional[str] = None,
):
    reply_markup = (
        build_cancel_task_markup(registry_task_id) if registry_task_id else None
    )
    if message_spec.submitted_status_text:
        await robust_edit_text(
            status_msg,
            message_spec.submitted_status_text,
            reply_markup=reply_markup,
        )
    elif message_spec.progress_wait_text:
        await robust_edit_text(
            status_msg,
            message_spec.progress_wait_text,
            reply_markup=reply_markup,
        )


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
    submission_result = await submit_bot_task(
        submission=submission,
    )
    if len(submission_result) == 2:
        registry_task_id, saved_inputs = submission_result
        backend_task_id = registry_task_id
    else:
        registry_task_id, backend_task_id, saved_inputs = submission_result
    if submitted_status_builder is not None:
        message_spec = with_submitted_status(
            message_spec,
            submitted_status_builder(submission.runtime_state.actual_cost),
        )
    await update_submitted_task_status(
        status_msg=status_msg,
        message_spec=message_spec,
        registry_task_id=registry_task_id,
    )
    return status_msg, registry_task_id, backend_task_id, saved_inputs, message_spec


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
    backend_task_id: str,
    status_msg,
    is_video: bool,
    internal_user_id: int,
    lang: str = "zh",
):
    return await task_service_completion_helpers.monitor_submitted_bot_task(
        task_id=backend_task_id,
        status_msg=status_msg,
        is_video=is_video,
        internal_user_id=internal_user_id,
        monitor_func=image_service.monitor_progress,
        get_user_priority_and_identity_func=get_user_priority_and_identity,
        monitor_bot_task_progress_func=(
            task_service_completion_helpers.monitor_bot_task_progress
        ),
        lang=lang,
    )


async def run_bot_task_completion_stage(
    *,
    context,
    chat_id,
    status_msg,
    runtime_state,
    internal_user_id: int,
    username: Optional[str],
    prompt: str,
    task_type: str,
    registry_task_id: str,
    backend_task_id: str,
    saved_inputs: list[str],
    final_info,
    is_video: bool,
    message_spec,
    send_result: bool,
    reply_markup,
    result_meta: dict | None,
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
            registry_task_id=registry_task_id,
            backend_task_id=backend_task_id,
            saved_input_images=saved_inputs,
            final_info=final_info,
            is_video=is_video,
            message_spec=message_spec,
            user_logger=UserLogger(internal_user_id, username),
            send_result=send_result,
            reply_markup=reply_markup,
            result_meta=result_meta,
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


async def execute_bot_task_stages(
    *,
    flow: BotTaskFlowContext,
    execution: _BotTaskExecutionState,
    submission: BotTaskSubmissionContext,
) -> tuple[bytes | None, str | None]:
    request = flow.request
    presentation = flow.presentation
    billing = flow.billing
    (
        execution.status_msg,
        execution.registry_task_id,
        execution.backend_task_id,
        execution.saved_inputs,
        execution.message_spec,
    ) = await run_bot_task_submission_stage(
        context=request.context,
        update=request.update,
        chat_id=request.chat_id,
        status_msg_id=request.status_msg_id,
        message_spec=presentation.message_spec,
        submitted_status_builder=presentation.submitted_status_builder,
        submission=submission,
    )

    return await run_monitored_task_lifecycle(
        monitor_stage_func=lambda: run_bot_task_monitor_stage(
            backend_task_id=execution.backend_task_id,
            status_msg=execution.status_msg,
            is_video=request.is_video,
            internal_user_id=request.internal_user_id,
            lang=resolve_context_lang(request.context),
        ),
        route_terminal_result_func=lambda final_info: run_bot_task_completion_stage(
            context=request.context,
            chat_id=request.chat_id,
            status_msg=execution.status_msg,
            runtime_state=flow.runtime_state,
            internal_user_id=request.internal_user_id,
            username=request.username,
            prompt=request.prompt,
            task_type=request.task_type,
            registry_task_id=execution.registry_task_id,
            backend_task_id=execution.backend_task_id,
            saved_inputs=execution.saved_inputs or [],
            final_info=final_info,
            is_video=request.is_video,
            message_spec=execution.message_spec or presentation.message_spec,
            send_result=presentation.send_result,
            reply_markup=presentation.reply_markup,
            result_meta=presentation.result_meta,
            delete_status=presentation.delete_status,
            allow_contribute=presentation.allow_contribute,
            billing_resolution=billing.billing_resolution,
            requested_duration=billing.requested_duration,
            missing_output_should_refund=billing.missing_output_should_refund,
        ),
    )


async def run_bot_task_application(
    *,
    flow: BotTaskFlowContext,
) -> tuple[bytes | None, str | None]:
    request = flow.request
    presentation = flow.presentation
    failure_policy = flow.failure_policy
    cleanup_policy = flow.cleanup_policy
    execution = _BotTaskExecutionState(message_spec=presentation.message_spec)
    submission = BotTaskSubmissionContext(
        runtime_state=flow.runtime_state,
        internal_user_id=request.internal_user_id,
        username=request.username,
        task_type=request.task_type,
        inputs=request.inputs,
        source_post_id=request.source_post_id,
        deduct_quota=request.deduct_quota,
    )

    try:
        return await execute_bot_task_stages(
            flow=flow,
            execution=execution,
            submission=submission,
        )
    except ConcurrencyLimitError as e:
        await task_service_finalize_helpers.send_bot_warning(request.context, request.chat_id, e)
        return None, None
    except InsufficientCreditsError as e:
        await task_service_finalize_helpers.send_bot_warning(request.context, request.chat_id, e)
        return None, None
    except BotTaskCancelled:
        return await task_service_finalize_helpers.handle_bot_cancelled_exception(
            status_msg=execution.status_msg,
            runtime_state=flow.runtime_state,
            internal_user_id=request.internal_user_id,
            username=request.username,
            message_spec=execution.message_spec or presentation.message_spec,
            deduct_quota=request.deduct_quota,
        )
    except CoreDomainError as e:
        await task_service_finalize_helpers.send_bot_domain_error(
            request.context, request.chat_id, e
        )
        return None, None
    except Exception as e:
        return await task_service_finalize_helpers.handle_bot_unexpected_exception(
            context=request.context,
            chat_id=request.chat_id,
            status_msg=(execution.status_msg if presentation.prefer_edit_status else None),
            runtime_state=flow.runtime_state,
            internal_user_id=request.internal_user_id,
            username=request.username,
            error=e,
            log_message=failure_policy.unexpected_error_log_message.format(
                internal_user_id=request.internal_user_id,
                error=e,
            ),
            should_refund=should_refund_for_unexpected_bot_error(
                runtime_state=flow.runtime_state,
                deduct_quota=request.deduct_quota,
                unexpected_should_refund=failure_policy.unexpected_should_refund,
            ),
            generic_error_prefix=failure_policy.unexpected_error_prefix,
            prefer_edit_status=presentation.prefer_edit_status,
            refund_suffix_mode=failure_policy.refund_suffix_mode,
        )
    finally:
        await cleanup_bot_task_flow(
            internal_user_id=request.internal_user_id,
            runtime_state=flow.runtime_state,
            cleanup_enabled=cleanup_policy.cleanup_enabled,
            cleanup_paths=cleanup_policy.cleanup_paths,
            cleanup_files_func=cleanup_policy.cleanup_files_func,
        )
