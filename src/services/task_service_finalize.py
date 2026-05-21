import asyncio
import logging

from src.services.task_service_types import BotTaskMessageSpec
from src.utils import robust_edit_text, robust_send_message

logger = logging.getLogger(__name__)


def build_bot_cancellation_message(cost: int, spec: BotTaskMessageSpec) -> str:
    return spec.cancellation_message_template.format(cost=cost)


async def finalize_cancelled_task_for_bot(
    *,
    status_msg,
    internal_user_id,
    username,
    cost,
    task_submitted,
    registry_task_id,
    explicit_user_message,
):
    from src.core.task_core import finalize_task_cancellation

    cancellation_result = await finalize_task_cancellation(
        internal_user_id=internal_user_id,
        username=username,
        cost=cost,
        task_submitted=task_submitted,
        registry_task_id=registry_task_id,
        release_lock=task_submitted,
        explicit_user_message=explicit_user_message,
    )
    if status_msg:
        await robust_edit_text(status_msg, f"✅ {cancellation_result.user_message}")
    return cancellation_result


async def finalize_failed_task_for_bot(
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
):
    from src.core.task_core import finalize_task_failure

    failure_result = await finalize_task_failure(
        internal_user_id=internal_user_id,
        username=username,
        cost=cost,
        should_refund=should_refund,
        registry_task_id=registry_task_id,
        release_lock=release_lock,
        explicit_user_message=explicit_user_message,
        error=error,
        generic_error_prefix=generic_error_prefix,
        refund_suffix_mode=refund_suffix_mode,
    )
    if prefer_edit_status and status_msg:
        await robust_edit_text(status_msg, f"{message_prefix} {failure_result.user_message}")
    elif fallback_to_send_message:
        await robust_send_message(
            context.bot,
            chat_id,
            f"{message_prefix} {failure_result.user_message}",
        )
    return failure_result


async def send_bot_warning(context, chat_id, error):
    await robust_send_message(context.bot, chat_id, f"⚠️ {error}")


async def send_bot_domain_error(context, chat_id, error):
    await robust_send_message(context.bot, chat_id, f"❌ {error}")


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
        internal_user_id=internal_user_id,
        username=username,
        cost=runtime_state.actual_cost,
        should_refund=should_refund,
        registry_task_id=runtime_state.registry_task_id,
        release_lock=runtime_state.task_submitted,
        error=error,
        generic_error_prefix=generic_error_prefix,
        prefer_edit_status=prefer_edit_status,
        refund_suffix_mode=refund_suffix_mode,
    )
    runtime_state.terminal_state_finalized = True
    return None, None


async def cleanup_runtime_state_if_needed(
    *,
    internal_user_id,
    registry_task_id,
    release_lock,
    terminal_state_finalized,
):
    if terminal_state_finalized or not (release_lock or registry_task_id):
        return

    from src.core.task_core import cleanup_task_runtime_state

    await asyncio.shield(
        cleanup_task_runtime_state(
            internal_user_id=internal_user_id,
            registry_task_id=registry_task_id,
            release_lock=release_lock,
        )
    )
