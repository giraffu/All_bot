import asyncio
import logging

from src.core.task_core_types import TaskFinalizationResult
from src.services.task_service_types import BotFinalizationPresentationPolicy
from src.services.task_service_types import BotTaskFailureContext
from src.services.task_service_types import BotTaskMessageSpec
from src.utils import robust_edit_text, robust_send_message

logger = logging.getLogger(__name__)


def build_bot_cancellation_message(cost: int, spec: BotTaskMessageSpec) -> str:
    return spec.cancellation_message_template.format(cost=cost)


def build_bot_cancellation_presentation_policy() -> BotFinalizationPresentationPolicy:
    return BotFinalizationPresentationPolicy(
        message_prefix="✅",
        prefer_edit_status=True,
        fallback_to_send_message=False,
    )


def build_bot_failure_presentation_policy(
    *,
    message_prefix: str = "❌",
    prefer_edit_status: bool = False,
    fallback_to_send_message: bool = True,
) -> BotFinalizationPresentationPolicy:
    return BotFinalizationPresentationPolicy(
        message_prefix=message_prefix,
        prefer_edit_status=prefer_edit_status,
        fallback_to_send_message=fallback_to_send_message,
    )


async def deliver_bot_finalization_message(
    *,
    context,
    chat_id,
    status_msg,
    finalization_result: TaskFinalizationResult,
    policy: BotFinalizationPresentationPolicy,
    edit_text_func=None,
    send_message_func=None,
):
    edit_text_func = edit_text_func or robust_edit_text
    send_message_func = send_message_func or robust_send_message
    if finalization_result.user_message is None:
        return
    rendered_message = f"{policy.message_prefix} {finalization_result.user_message}"
    if policy.prefer_edit_status and status_msg:
        await edit_text_func(status_msg, rendered_message)
        return
    if policy.fallback_to_send_message:
        await send_message_func(context.bot, chat_id, rendered_message)


async def finalize_cancelled_task_for_bot(
    *,
    status_msg,
    internal_user_id,
    username,
    cost,
    task_submitted,
    registry_task_id,
    explicit_user_message,
    finalize_task_cancellation_func=None,
    edit_text_func=None,
):
    from src.core.task_core_finalization import finalize_task_cancellation

    finalize_task_cancellation_func = (
        finalize_task_cancellation_func or finalize_task_cancellation
    )
    cancellation_result = await finalize_task_cancellation_func(
        internal_user_id=internal_user_id,
        username=username,
        cost=cost,
        task_submitted=task_submitted,
        registry_task_id=registry_task_id,
        release_lock=task_submitted,
        explicit_user_message=explicit_user_message,
    )
    await deliver_bot_finalization_message(
        context=None,
        chat_id=None,
        status_msg=status_msg,
        finalization_result=cancellation_result,
        policy=build_bot_cancellation_presentation_policy(),
        edit_text_func=edit_text_func,
    )
    return cancellation_result


async def finalize_failed_task_for_bot(
    *,
    context,
    chat_id,
    status_msg,
    failure: BotTaskFailureContext,
    message_prefix="❌",
    prefer_edit_status=False,
    fallback_to_send_message=True,
    finalize_task_failure_func=None,
    edit_text_func=None,
    send_message_func=None,
):
    from src.core.task_core_finalization import finalize_task_failure

    finalize_task_failure_func = finalize_task_failure_func or finalize_task_failure
    failure_result = await finalize_task_failure_func(
        internal_user_id=failure.internal_user_id,
        username=failure.username,
        cost=failure.cost,
        should_refund=failure.should_refund,
        registry_task_id=failure.registry_task_id,
        release_lock=failure.release_lock,
        explicit_user_message=failure.explicit_user_message,
        error=failure.error,
        generic_error_prefix=failure.generic_error_prefix,
        refund_suffix_mode=failure.refund_suffix_mode,
    )
    await deliver_bot_finalization_message(
        context=context,
        chat_id=chat_id,
        status_msg=status_msg,
        finalization_result=failure_result,
        policy=build_bot_failure_presentation_policy(
            message_prefix=message_prefix,
            prefer_edit_status=prefer_edit_status,
            fallback_to_send_message=fallback_to_send_message,
        ),
        edit_text_func=edit_text_func,
        send_message_func=send_message_func,
    )
    return failure_result


async def send_bot_warning(context, chat_id, error, send_message_func=None):
    send_message_func = send_message_func or robust_send_message
    await send_message_func(context.bot, chat_id, f"⚠️ {error}")


async def send_bot_domain_error(context, chat_id, error, send_message_func=None):
    send_message_func = send_message_func or robust_send_message
    await send_message_func(context.bot, chat_id, f"❌ {error}")


async def handle_bot_cancelled_exception(
    *,
    status_msg,
    runtime_state,
    internal_user_id,
    username,
    message_spec,
    deduct_quota=True,
):
    await finalize_cancelled_task_for_bot(
        status_msg=status_msg,
        internal_user_id=internal_user_id,
        username=username,
        cost=runtime_state.actual_cost,
        task_submitted=deduct_quota and runtime_state.task_submitted,
        registry_task_id=runtime_state.registry_task_id,
        explicit_user_message=build_bot_cancellation_message(
            runtime_state.actual_cost, message_spec
        ),
    )
    runtime_state.terminal_state_finalized = True
    return None, None


async def handle_bot_unexpected_exception(
    *,
    context,
    chat_id,
    status_msg,
    runtime_state,
    internal_user_id,
    username,
    error,
    log_message,
    should_refund,
    generic_error_prefix,
    prefer_edit_status=False,
    refund_suffix_mode="if_refunded",
):
    logger.error(log_message, exc_info=True)
    await finalize_failed_task_for_bot(
        context=context,
        chat_id=chat_id,
        status_msg=status_msg,
        failure=BotTaskFailureContext(
            internal_user_id=internal_user_id,
            username=username,
            cost=runtime_state.actual_cost,
            should_refund=should_refund,
            registry_task_id=runtime_state.registry_task_id,
            release_lock=runtime_state.task_submitted,
            error=error,
            generic_error_prefix=generic_error_prefix,
            refund_suffix_mode=refund_suffix_mode,
        ),
        prefer_edit_status=prefer_edit_status,
    )
    runtime_state.terminal_state_finalized = True
    return None, None


async def cleanup_runtime_state_if_needed(
    *,
    internal_user_id,
    registry_task_id,
    release_lock,
    terminal_state_finalized,
    cleanup_task_runtime_state_func=None,
):
    if terminal_state_finalized or not (release_lock or registry_task_id):
        return

    from src.core.task_core_runtime import cleanup_task_runtime_state

    cleanup_task_runtime_state_func = (
        cleanup_task_runtime_state_func or cleanup_task_runtime_state
    )
    await asyncio.shield(
        cleanup_task_runtime_state_func(
            internal_user_id=internal_user_id,
            registry_task_id=registry_task_id,
            release_lock=release_lock,
        )
    )
