import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable

from src.core.billing_core import refund_credits
from src.core.task_core_default_dependencies import (
    build_default_task_core_submission_dependencies,
)
from src.core.task_core_error_helpers import is_task_backend_busy_error
from src.core.task_core_types import (
    CoreDomainError,
    TaskSubmissionContext,
    TaskSubmissionExecutionResult,
)
from src.core.task_dispatcher import dispatch_to_worker


async def register_task_submission(
    *,
    registry_task_id: str,
    user_id: int,
    username: str,
    cost: int,
    submission_context: TaskSubmissionContext,
    add_task_func: Callable[..., Awaitable[str]],
) -> str:
    return await add_task_func(
        task_id=registry_task_id,
        user_id=user_id,
        username=username,
        cost=cost,
        task_type=submission_context.task_type,
        prompt=submission_context.log_prompt,
        saved_input_images=submission_context.registry_saved_inputs(),
        is_video=submission_context.is_video_task,
        priority=submission_context.final_priority,
        allow_contribute=submission_context.allow_contribute,
        metadata=submission_context.metadata,
    )


async def dispatch_registered_task(
    *,
    registry_task_id: str,
    task_type: str,
    inputs: dict,
    final_priority: int,
    dispatch_to_worker_func: Callable[..., Awaitable[str]],
    update_backend_task_id_func: Callable[..., Awaitable[None]],
    mark_task_status_func: Callable[..., Awaitable[None]],
    is_task_backend_busy_error_func: Callable[[str], bool],
    logger: logging.Logger,
) -> str:
    try:
        backend_task_id = await dispatch_to_worker_func(
            registry_task_id,
            task_type,
            inputs,
            final_priority,
        )
        if registry_task_id and backend_task_id:
            await update_backend_task_id_func(registry_task_id, backend_task_id)
        if not backend_task_id:
            raise Exception("Failed to submit task to backend API.")
        return backend_task_id
    except Exception as exc:
        logger.error("Dispatch to worker failed: %s", exc, exc_info=True)
        if registry_task_id:
            with contextlib.suppress(Exception):
                await mark_task_status_func(registry_task_id, "failed")
        error_msg = str(exc)
        if is_task_backend_busy_error_func(error_msg):
            raise CoreDomainError("当前服务器繁忙，请稍后再试") from exc
        raise CoreDomainError(f"System error: {error_msg}") from exc


async def execute_task_submission_saga(
    *,
    task_type: str,
    inputs: dict,
    registry_task_id: str,
    cost: int,
    submission_context: TaskSubmissionContext,
    register_task_submission_func: Callable[..., Awaitable[str]],
    dispatch_registered_task_func: Callable[..., Awaitable[str]],
) -> TaskSubmissionExecutionResult:
    registry_task_id = await register_task_submission_func(
        registry_task_id=registry_task_id,
        user_id=submission_context.user_logger.user_id,
        username=submission_context.user_logger.username,
        cost=cost,
        submission_context=submission_context,
    )
    backend_task_id = await dispatch_registered_task_func(
        registry_task_id=registry_task_id,
        task_type=task_type,
        inputs=inputs,
        final_priority=submission_context.final_priority,
    )
    return TaskSubmissionExecutionResult(
        registry_task_id=registry_task_id,
        backend_task_id=backend_task_id,
        submission_context=submission_context,
    )


async def compensate_failed_submission(
    *,
    user_id: int,
    username: str,
    cost: int,
    error: Exception,
    credits_deducted: bool,
    registry_task_id: str,
    refund_credits_func: Callable[..., Awaitable[None]],
    add_pending_refund_func: Callable[..., Awaitable[None]],
    remove_task_func: Callable[..., Awaitable[None]],
    logger: logging.Logger,
    shield_func=None,
):
    if shield_func is None:
        shield_func = asyncio.shield

    if credits_deducted:
        try:
            await shield_func(
                refund_credits_func(
                    user_id,
                    cost,
                    task_type="refund_saga_failed",
                    username=username,
                )
            )
        except Exception as refund_err:
            logger.critical(
                "REFUND FAILED! Log to Outbox. User: %s, Amount: %s, Error: %s",
                user_id,
                cost,
                refund_err,
            )
            await add_pending_refund_func(
                user_id,
                cost,
                f"Task Failed: {str(error)}",
                username,
            )

    with contextlib.suppress(Exception):
        await shield_func(remove_task_func(registry_task_id))


async def register_task_submission_default(
    *,
    registry_task_id: str,
    user_id: int,
    username: str,
    cost: int,
    submission_context: TaskSubmissionContext,
    logger_override: logging.Logger | None = None,
) -> str:
    dependencies = build_default_task_core_submission_dependencies(
        dispatch_to_worker_func=dispatch_to_worker,
        is_task_backend_busy_error_func=lambda _message: False,
        logger_override=logger_override or logging.getLogger(__name__),
    )
    return await register_task_submission(
        registry_task_id=registry_task_id,
        user_id=user_id,
        username=username,
        cost=cost,
        submission_context=submission_context,
        add_task_func=dependencies.add_task_func,
    )


async def dispatch_registered_task_default(
    *,
    registry_task_id: str,
    task_type: str,
    inputs: dict,
    final_priority: int,
    is_task_backend_busy_error_func=is_task_backend_busy_error,
    logger_override: logging.Logger | None = None,
) -> str:
    dependencies = build_default_task_core_submission_dependencies(
        dispatch_to_worker_func=dispatch_to_worker,
        is_task_backend_busy_error_func=is_task_backend_busy_error_func,
        logger_override=logger_override or logging.getLogger(__name__),
    )
    return await dispatch_registered_task(
        registry_task_id=registry_task_id,
        task_type=task_type,
        inputs=inputs,
        final_priority=final_priority,
        dispatch_to_worker_func=dependencies.dispatch_to_worker_func,
        update_backend_task_id_func=dependencies.update_backend_task_id_func,
        mark_task_status_func=dependencies.mark_task_status_func,
        is_task_backend_busy_error_func=dependencies.is_task_backend_busy_error_func,
        logger=dependencies.logger,
    )


async def execute_task_submission_saga_default(
    *,
    task_type: str,
    inputs: dict,
    registry_task_id: str,
    cost: int,
    submission_context: TaskSubmissionContext,
    is_task_backend_busy_error_func=is_task_backend_busy_error,
    logger_override: logging.Logger | None = None,
) -> TaskSubmissionExecutionResult:
    return await execute_task_submission_saga(
        task_type=task_type,
        inputs=inputs,
        registry_task_id=registry_task_id,
        cost=cost,
        submission_context=submission_context,
        register_task_submission_func=register_task_submission_default,
        dispatch_registered_task_func=lambda **kwargs: dispatch_registered_task_default(
            **kwargs,
            is_task_backend_busy_error_func=is_task_backend_busy_error_func,
            logger_override=logger_override,
        ),
    )


async def compensate_failed_submission_default(
    *,
    user_id: int,
    username: str,
    cost: int,
    error: Exception,
    credits_deducted: bool,
    registry_task_id: str,
    logger_override: logging.Logger | None = None,
):
    dependencies = build_default_task_core_submission_dependencies(
        dispatch_to_worker_func=dispatch_to_worker,
        is_task_backend_busy_error_func=lambda _message: False,
        logger_override=logger_override or logging.getLogger(__name__),
    )
    await compensate_failed_submission(
        user_id=user_id,
        username=username,
        cost=cost,
        error=error,
        credits_deducted=credits_deducted,
        registry_task_id=registry_task_id,
        refund_credits_func=refund_credits,
        add_pending_refund_func=dependencies.add_pending_refund_func,
        remove_task_func=dependencies.remove_task_func,
        logger=dependencies.logger,
    )
