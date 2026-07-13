import asyncio
import logging

from src.core.billing_core import refund_credits
from src.core.task_core_error_helpers import build_failed_task_user_message
from src.core.task_core_default_dependencies import (
    build_default_task_core_finalization_dependencies,
)
from src.core.task_core_runtime import cleanup_task_runtime_state, force_terminate_task
from src.core.task_core_types import (
    TaskCancellationFinalizationResult,
    TaskFailureFinalizationResult,
    TaskFinalizationContext,
    TaskTerminationFinalizationResult,
)

logger = logging.getLogger(__name__)


def build_task_refund_idempotency_key(
    *, refund_task_type: str, registry_task_id: str | None
) -> str | None:
    _ = refund_task_type
    if not registry_task_id:
        return None
    return f"task_refund:task:{registry_task_id}"


async def _refund_task_with_type(
    *,
    internal_user_id: int,
    username: str,
    cost: int,
    should_refund: bool,
    refund_task_type: str,
    idempotency_key: str | None = None,
    refund_credits_func=None,
) -> bool:
    if refund_credits_func is None:
        refund_credits_func = refund_credits

    if not should_refund or cost <= 0:
        return False
    kwargs = {
        "task_type": refund_task_type,
        "username": username,
    }
    if idempotency_key:
        kwargs["idempotency_key"] = idempotency_key
    refund_result = await asyncio.shield(
        refund_credits_func(
            internal_user_id,
            cost,
            **kwargs,
        )
    )
    return refund_result is not False


async def refund_cancelled_task(
    *,
    internal_user_id: int,
    username: str,
    cost: int,
    task_submitted: bool,
    idempotency_key: str | None = None,
    refund_credits_func=None,
) -> bool:
    return await _refund_task_with_type(
        internal_user_id=internal_user_id,
        username=username,
        cost=cost,
        should_refund=task_submitted,
        refund_task_type="refund_user_cancel",
        idempotency_key=idempotency_key,
        refund_credits_func=refund_credits_func,
    )


async def send_task_finalization_notice_best_effort(
    *,
    message: str | None,
    send_user_notice_func=None,
    logger_override=logger,
    notice_failure_log_message: str = "Failed to send task finalization notice",
) -> bool:
    if not message or send_user_notice_func is None:
        return False

    try:
        await send_user_notice_func(message)
        return True
    except Exception as exc:
        logger_override.error("%s: %s", notice_failure_log_message, exc)
        return False


async def _cleanup_after_finalization(
    context: TaskFinalizationContext,
    *,
    cleanup_task_runtime_state_func=None,
):
    if cleanup_task_runtime_state_func is None:
        cleanup_task_runtime_state_func = cleanup_task_runtime_state

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
    refund_credits_func=None,
) -> bool:
    if refund_credits_func is None:
        refund_credits_func = refund_credits

    if user_id is None:
        return False

    try:
        return await _refund_task_with_type(
            internal_user_id=user_id,
            username=username,
            cost=cost,
            should_refund=should_refund,
            refund_task_type=refund_task_type,
            idempotency_key=build_task_refund_idempotency_key(
                refund_task_type=refund_task_type,
                registry_task_id=registry_task_id,
            ),
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
    refund_credits_func=None,
    cleanup_task_runtime_state_func=None,
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
        idempotency_key=build_task_refund_idempotency_key(
            refund_task_type=refund_task_type,
            registry_task_id=context.registry_task_id,
        ),
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


async def finalize_task_failure_with_notice(
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
    send_user_notice_func=None,
    notice_message: str | None = None,
    logger_override=logger,
    notice_failure_log_message: str = "Failed to send task finalization notice",
    finalize_task_failure_func=None,
) -> TaskFailureFinalizationResult:
    if finalize_task_failure_func is None:
        finalize_task_failure_func = finalize_task_failure

    result = await finalize_task_failure_func(
        internal_user_id=internal_user_id,
        username=username,
        cost=cost,
        should_refund=should_refund,
        registry_task_id=registry_task_id,
        release_lock=release_lock,
        refund_task_type=refund_task_type,
        error=error,
        generic_error_prefix=generic_error_prefix,
        explicit_user_message=explicit_user_message,
        refund_suffix_mode=refund_suffix_mode,
    )

    await send_task_finalization_notice_best_effort(
        message=notice_message or result.user_message,
        send_user_notice_func=send_user_notice_func,
        logger_override=logger_override,
        notice_failure_log_message=notice_failure_log_message,
    )
    return result


async def finalize_task_cancellation(
    *,
    internal_user_id: int,
    username: str,
    cost: int,
    task_submitted: bool,
    registry_task_id: str | None,
    release_lock: bool = True,
    explicit_user_message: str | None = None,
    refund_cancelled_task_func=None,
    cleanup_task_runtime_state_func=None,
) -> TaskCancellationFinalizationResult:
    if refund_cancelled_task_func is None:
        refund_cancelled_task_func = refund_cancelled_task

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
        idempotency_key=build_task_refund_idempotency_key(
            refund_task_type="refund_user_cancel",
            registry_task_id=context.registry_task_id,
        ),
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
    force_terminate_task_func=None,
    refund_credits_func=None,
) -> TaskTerminationFinalizationResult:
    if force_terminate_task_func is None:
        force_terminate_task_func = force_terminate_task

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


async def refund_cancelled_task_default(
    *,
    internal_user_id: int,
    username: str,
    cost: int,
    task_submitted: bool,
    idempotency_key: str | None = None,
) -> bool:
    dependencies = build_default_task_core_finalization_dependencies(
        refund_credits_func=refund_credits,
        cleanup_task_runtime_state_func=cleanup_task_runtime_state,
        refund_cancelled_task_func=refund_cancelled_task_default,
        force_terminate_task_func=force_terminate_task,
    )
    return await refund_cancelled_task(
        internal_user_id=internal_user_id,
        username=username,
        cost=cost,
        task_submitted=task_submitted,
        idempotency_key=idempotency_key,
        refund_credits_func=dependencies.refund_credits_func,
    )


async def finalize_task_failure_default(
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
) -> TaskFailureFinalizationResult:
    dependencies = build_default_task_core_finalization_dependencies(
        refund_credits_func=refund_credits,
        cleanup_task_runtime_state_func=cleanup_task_runtime_state,
        refund_cancelled_task_func=refund_cancelled_task_default,
        force_terminate_task_func=force_terminate_task,
    )
    return await finalize_task_failure(
        internal_user_id=internal_user_id,
        username=username,
        cost=cost,
        should_refund=should_refund,
        registry_task_id=registry_task_id,
        release_lock=release_lock,
        refund_task_type=refund_task_type,
        error=error,
        generic_error_prefix=generic_error_prefix,
        explicit_user_message=explicit_user_message,
        refund_suffix_mode=refund_suffix_mode,
        refund_credits_func=dependencies.refund_credits_func,
        cleanup_task_runtime_state_func=dependencies.cleanup_task_runtime_state_func,
    )


async def finalize_task_cancellation_default(
    *,
    internal_user_id: int,
    username: str,
    cost: int,
    task_submitted: bool,
    registry_task_id: str | None,
    release_lock: bool = True,
    explicit_user_message: str | None = None,
) -> TaskCancellationFinalizationResult:
    dependencies = build_default_task_core_finalization_dependencies(
        refund_credits_func=refund_credits,
        cleanup_task_runtime_state_func=cleanup_task_runtime_state,
        refund_cancelled_task_func=refund_cancelled_task_default,
        force_terminate_task_func=force_terminate_task,
    )
    return await finalize_task_cancellation(
        internal_user_id=internal_user_id,
        username=username,
        cost=cost,
        task_submitted=task_submitted,
        registry_task_id=registry_task_id,
        release_lock=release_lock,
        explicit_user_message=explicit_user_message,
        refund_cancelled_task_func=dependencies.refund_cancelled_task_func,
        cleanup_task_runtime_state_func=dependencies.cleanup_task_runtime_state_func,
    )
