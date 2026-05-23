import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from src.core.task_core_types import TaskSubmissionContext


def attach_web_task_monitor(
    *,
    backend_task_id: str,
    internal_user_id: int,
    username: str,
    registry_task_id: str,
    submission_context: TaskSubmissionContext,
    cost: int,
    monitor_web_task_func: Callable[..., Awaitable[None]],
    create_task_func=None,
):
    if create_task_func is None:
        create_task_func = asyncio.create_task

    create_task_func(
        monitor_web_task_func(
            backend_task_id=backend_task_id,
            internal_user_id=internal_user_id,
            username=username,
            registry_task_id=registry_task_id,
            submission_context=submission_context,
            cost=cost,
        )
    )


async def finalize_monitored_web_task_success(
    *,
    backend_task_id: str,
    internal_user_id: int,
    username: str,
    registry_task_id: str,
    submission_context: TaskSubmissionContext,
    result_path: str,
    persist_successful_web_history_func: Callable[..., Awaitable[None]],
    cleanup_task_runtime_state_func: Callable[..., Awaitable[None]],
    logger: logging.Logger,
):
    try:
        await persist_successful_web_history_func(
            backend_task_id=backend_task_id,
            registry_task_id=registry_task_id,
            internal_user_id=internal_user_id,
            username=username,
            prompt=submission_context.log_prompt,
            task_type=submission_context.task_type,
            input_images=submission_context.saved_inputs,
            allow_contribute=submission_context.allow_contribute,
            is_video=submission_context.is_video_task,
            result_path=result_path,
            billing_resolution=submission_context.billing_resolution,
            output_width=submission_context.output_width,
            output_height=submission_context.output_height,
            output_duration=submission_context.output_duration,
            requested_duration=submission_context.requested_duration,
        )
    except Exception as log_err:
        logger.error(
            "Failed to log task history for %s: %s",
            registry_task_id,
            log_err,
        )
    await cleanup_task_runtime_state_func(
        internal_user_id=internal_user_id,
        registry_task_id=registry_task_id,
    )


async def finalize_monitored_web_task_cancellation(
    *,
    internal_user_id: int,
    username: str,
    cost: int,
    registry_task_id: str,
    finalize_task_cancellation_func: Callable[..., Awaitable[Any]],
    logger: logging.Logger,
):
    try:
        await finalize_task_cancellation_func(
            internal_user_id=internal_user_id,
            username=username,
            cost=cost,
            task_submitted=True,
            registry_task_id=registry_task_id,
        )
    except Exception as refund_err:
        logger.critical(
            "Async cancellation finalize failed for user %s: %s",
            internal_user_id,
            refund_err,
        )


async def finalize_monitored_web_task_failure(
    *,
    internal_user_id: int,
    username: str,
    cost: int,
    registry_task_id: str,
    final_status: str | None,
    finalize_task_failure_func: Callable[..., Awaitable[Any]],
    logger: logging.Logger,
):
    try:
        await finalize_task_failure_func(
            internal_user_id=internal_user_id,
            username=username,
            cost=cost,
            should_refund=cost > 0,
            registry_task_id=registry_task_id,
            refund_task_type=f"refund_async_failed_{final_status}",
        )
    except Exception as refund_err:
        logger.critical(
            "Async refund failed for user %s: %s",
            internal_user_id,
            refund_err,
        )


async def monitor_task_and_release_lock(
    *,
    backend_task_id: str,
    internal_user_id: int,
    username: str,
    registry_task_id: str,
    submission_context: TaskSubmissionContext,
    cost: int,
    monitor_progress_func: Callable[[str, bool], AsyncIterator[dict[str, Any]]],
    normalize_terminal_status_func: Callable[[Any], str | None],
    finalize_success_func: Callable[..., Awaitable[None]],
    finalize_cancellation_func: Callable[..., Awaitable[None]],
    finalize_failure_func: Callable[..., Awaitable[None]],
    logger: logging.Logger,
):
    final_status = None
    result_path = None
    try:
        async for progress in monitor_progress_func(
            backend_task_id,
            submission_context.is_video_task,
        ):
            normalized_status = normalize_terminal_status_func(progress.get("status"))
            if normalized_status in ["done", "error", "cancelled"]:
                final_status = normalized_status
                result_path = progress.get("result_path")
                break
    except asyncio.CancelledError:
        logger.error("Task monitor %s cancelled.", backend_task_id)
        final_status = "cancelled"
    except Exception as exc:
        logger.error(
            "Background monitoring error for task %s: %s",
            backend_task_id,
            exc,
        )
        final_status = "error"
    finally:
        if final_status == "done" and result_path:
            await finalize_success_func(
                backend_task_id=backend_task_id,
                internal_user_id=internal_user_id,
                username=username,
                registry_task_id=registry_task_id,
                submission_context=submission_context,
                result_path=result_path,
            )
        elif final_status == "cancelled":
            await finalize_cancellation_func(
                internal_user_id=internal_user_id,
                username=username,
                cost=cost,
                registry_task_id=registry_task_id,
            )
        else:
            await finalize_failure_func(
                internal_user_id=internal_user_id,
                username=username,
                cost=cost,
                registry_task_id=registry_task_id,
                final_status=final_status,
            )
