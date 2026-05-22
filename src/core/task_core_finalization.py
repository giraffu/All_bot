import asyncio
import logging

from src.core.billing_core import refund_credits
from src.core.task_core_runtime import cleanup_task_runtime_state, force_terminate_task
from src.core.task_core_types import (
    TaskCancellationFinalizationResult,
    TaskFailureFinalizationResult,
    TaskFinalizationContext,
    TaskTerminationFinalizationResult,
    build_failed_task_user_message,
)

logger = logging.getLogger(__name__)


async def _refund_task_with_type(
    *,
    internal_user_id: int,
    username: str,
    cost: int,
    should_refund: bool,
    refund_task_type: str,
    refund_credits_func=refund_credits,
) -> bool:
    if not should_refund or cost <= 0:
        return False
    await asyncio.shield(
        refund_credits_func(
            internal_user_id,
            cost,
            task_type=refund_task_type,
            username=username,
        )
    )
    return True


async def refund_cancelled_task(
    *,
    internal_user_id: int,
    username: str,
    cost: int,
    task_submitted: bool,
    refund_credits_func=refund_credits,
) -> bool:
    return await _refund_task_with_type(
        internal_user_id=internal_user_id,
        username=username,
        cost=cost,
        should_refund=task_submitted,
        refund_task_type="refund_user_cancel",
        refund_credits_func=refund_credits_func,
    )


async def refund_failed_task(
    *,
    internal_user_id: int,
    username: str,
    cost: int,
    should_refund: bool,
    refund_credits_func=refund_credits,
) -> bool:
    return await _refund_task_with_type(
        internal_user_id=internal_user_id,
        username=username,
        cost=cost,
        should_refund=should_refund,
        refund_task_type="refund",
        refund_credits_func=refund_credits_func,
    )


async def handle_failed_task_exception(
    *,
    internal_user_id: int,
    username: str,
    cost: int,
    should_refund: bool,
    error: Exception,
    generic_error_prefix: str,
    refund_suffix_mode: str = "if_refunded",
    refund_credits_func=refund_credits,
) -> str:
    refunded = await refund_failed_task(
        internal_user_id=internal_user_id,
        username=username,
        cost=cost,
        should_refund=should_refund,
        refund_credits_func=refund_credits_func,
    )
    return build_failed_task_user_message(
        error=error,
        generic_error_prefix=generic_error_prefix,
        refunded=refunded,
        refund_suffix_mode=refund_suffix_mode,
    )


async def _cleanup_after_finalization(
    context: TaskFinalizationContext,
    *,
    cleanup_task_runtime_state_func=cleanup_task_runtime_state,
):
    await cleanup_task_runtime_state_func(
        internal_user_id=context.internal_user_id,
        registry_task_id=context.registry_task_id,
        release_lock=context.release_lock,
    )


def _build_cancelled_task_user_message(
    *,
    cost: int,
    refunded: bool,
    explicit_user_message: str | None,
) -> str | None:
    if explicit_user_message is not None:
        return explicit_user_message
    if refunded:
        return f"任务已撤销，预扣的 {cost} 灵石已全额退回。"
    return None


async def _refund_terminated_task_best_effort(
    *,
    user_id: int | None,
    username: str,
    cost: int,
    should_refund: bool,
    refund_task_type: str,
    registry_task_id: str,
    refund_credits_func=refund_credits,
) -> bool:
    if user_id is None:
        return False

    try:
        return await _refund_task_with_type(
            internal_user_id=user_id,
            username=username,
            cost=cost,
            should_refund=should_refund,
            refund_task_type=refund_task_type,
            refund_credits_func=refund_credits_func,
        )
    except Exception:
        logger.exception(
            "Failed to refund terminated task %s for user %s.",
            registry_task_id,
            user_id,
        )
        return False


async def finalize_task_failure(
    *,
    internal_user_id: int,
    username: str,
    cost: int,
    should_refund: bool,
    registry_task_id: str | None,
    release_lock: bool = True,
    refund_task_type: str = "refund",
    error: Exception | None = None,
    generic_error_prefix: str | None = None,
    explicit_user_message: str | None = None,
    refund_suffix_mode: str = "if_refunded",
    refund_credits_func=refund_credits,
    cleanup_task_runtime_state_func=cleanup_task_runtime_state,
) -> TaskFailureFinalizationResult:
    context = TaskFinalizationContext(
        internal_user_id=internal_user_id,
        username=username,
        cost=cost,
        registry_task_id=registry_task_id,
        release_lock=release_lock,
    )
    refunded = await _refund_task_with_type(
        internal_user_id=context.internal_user_id,
        username=context.username,
        cost=context.cost,
        should_refund=should_refund,
        refund_task_type=refund_task_type,
        refund_credits_func=refund_credits_func,
    )

    user_message = explicit_user_message
    if user_message is None and error is not None and generic_error_prefix is not None:
        user_message = build_failed_task_user_message(
            error=error,
            generic_error_prefix=generic_error_prefix,
            refunded=refunded,
            refund_suffix_mode=refund_suffix_mode,
        )

    await _cleanup_after_finalization(
        context,
        cleanup_task_runtime_state_func=cleanup_task_runtime_state_func,
    )

    return TaskFailureFinalizationResult(
        refunded=refunded,
        user_message=user_message,
    )


async def finalize_task_cancellation(
    *,
    internal_user_id: int,
    username: str,
    cost: int,
    task_submitted: bool,
    registry_task_id: str | None,
    release_lock: bool = True,
    explicit_user_message: str | None = None,
    refund_cancelled_task_func=refund_cancelled_task,
    cleanup_task_runtime_state_func=cleanup_task_runtime_state,
) -> TaskCancellationFinalizationResult:
    context = TaskFinalizationContext(
        internal_user_id=internal_user_id,
        username=username,
        cost=cost,
        registry_task_id=registry_task_id,
        release_lock=release_lock,
    )
    refunded = await refund_cancelled_task_func(
        internal_user_id=context.internal_user_id,
        username=context.username,
        cost=context.cost,
        task_submitted=task_submitted,
    )

    await _cleanup_after_finalization(
        context,
        cleanup_task_runtime_state_func=cleanup_task_runtime_state_func,
    )

    user_message = _build_cancelled_task_user_message(
        cost=context.cost,
        refunded=refunded,
        explicit_user_message=explicit_user_message,
    )

    return TaskCancellationFinalizationResult(
        refunded=refunded,
        user_message=user_message,
    )


async def finalize_terminated_task(
    *,
    registry_task_id: str,
    user_id: int | None,
    username: str,
    cost: int,
    should_refund: bool,
    refund_task_type: str,
    force_terminate_task_func=force_terminate_task,
    refund_credits_func=refund_credits,
) -> TaskTerminationFinalizationResult:
    await force_terminate_task_func(registry_task_id, user_id=user_id)

    refunded = await _refund_terminated_task_best_effort(
        user_id=user_id,
        username=username,
        cost=cost,
        should_refund=should_refund,
        refund_task_type=refund_task_type,
        registry_task_id=registry_task_id,
        refund_credits_func=refund_credits_func,
    )

    return TaskTerminationFinalizationResult(
        refunded=refunded,
    )
