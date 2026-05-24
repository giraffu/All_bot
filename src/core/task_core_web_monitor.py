import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from src.core.task_core_default_dependencies import (
    build_default_task_core_monitor_dependencies,
    build_default_task_core_side_effect_dependencies,
)
from src.core.task_core_finalization import (
    finalize_task_cancellation_default,
    finalize_task_failure_default,
)
from src.core.task_core_persistence import persist_successful_web_history_default
from src.core.task_core_types import TaskSubmissionContext
from src.core.task_core_types import CoreDomainError, normalize_terminal_status
from src.core.task_core_runtime import cleanup_task_runtime_state


def get_default_task_core_monitor_dependencies():
    return build_default_task_core_monitor_dependencies(
        normalize_terminal_status_func=normalize_terminal_status,
        finalize_success_func=finalize_monitored_web_task_success_default,
        finalize_cancellation_func=finalize_monitored_web_task_cancellation_default,
        finalize_failure_func=finalize_monitored_web_task_failure_default,
        logger_override=logging.getLogger(__name__),
    )


def get_default_task_core_side_effect_dependencies():
    from src.core.gallery_core import record_apply_interaction

    return build_default_task_core_side_effect_dependencies(
        attach_web_task_monitor_func=attach_web_task_monitor,
        monitor_web_task_func=monitor_task_and_release_lock_default,
        record_apply_interaction_func=record_apply_interaction,
    )


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

    monitor_coro = monitor_web_task_func(
        backend_task_id=backend_task_id,
        internal_user_id=internal_user_id,
        username=username,
        registry_task_id=registry_task_id,
        submission_context=submission_context,
        cost=cost,
    )
    try:
        create_task_func(monitor_coro, name="task-core-web-monitor")
    except TypeError:
        create_task_func(monitor_coro)


def schedule_apply_interaction(
    user_id: int,
    source_post_id: int | None,
    *,
    record_apply_interaction_func,
    create_task_func=None,
):
    if not source_post_id:
        return
    if create_task_func is None:
        create_task_func = asyncio.create_task
    interaction_coro = record_apply_interaction_func(user_id, source_post_id)
    try:
        create_task_func(interaction_coro, name="task-core-apply-interaction")
    except TypeError:
        create_task_func(interaction_coro)


def attach_submission_side_effects(
    *,
    client_type: str,
    backend_task_id: str,
    internal_user_id: int,
    username: str,
    registry_task_id: str,
    submission_context: TaskSubmissionContext,
    cost: int,
    source_post_id: int | None,
    attach_web_task_monitor_func,
    schedule_apply_interaction_func,
    core_domain_error_cls,
):
    if client_type == "web":
        try:
            attach_web_task_monitor_func(
                backend_task_id=backend_task_id,
                internal_user_id=internal_user_id,
                username=username,
                registry_task_id=registry_task_id,
                submission_context=submission_context,
                cost=cost,
            )
        except Exception as exc:
            raise core_domain_error_cls(f"后台监控挂载失败: {exc}")

    schedule_apply_interaction_func(internal_user_id, source_post_id)


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


def attach_web_task_monitor_default(
    *,
    backend_task_id: str,
    internal_user_id: int,
    username: str,
    registry_task_id: str,
    submission_context: TaskSubmissionContext,
    cost: int,
    monitor_web_task_func=None,
    dependencies=None,
):
    side_effect_dependencies = dependencies or get_default_task_core_side_effect_dependencies()
    if monitor_web_task_func is None:
        monitor_web_task_func = side_effect_dependencies.monitor_web_task_func
    side_effect_dependencies.attach_web_task_monitor_func(
        backend_task_id=backend_task_id,
        internal_user_id=internal_user_id,
        username=username,
        registry_task_id=registry_task_id,
        submission_context=submission_context,
        cost=cost,
        monitor_web_task_func=monitor_web_task_func,
        create_task_func=side_effect_dependencies.create_task_func,
    )


def schedule_apply_interaction_default(
    user_id: int,
    source_post_id: int | None,
    dependencies=None,
):
    dependencies = dependencies or get_default_task_core_side_effect_dependencies()
    schedule_apply_interaction(
        user_id,
        source_post_id,
        record_apply_interaction_func=dependencies.record_apply_interaction_func,
        create_task_func=dependencies.create_task_func,
    )


def attach_submission_side_effects_default(
    *,
    client_type: str,
    backend_task_id: str,
    internal_user_id: int,
    username: str,
    registry_task_id: str,
    submission_context: TaskSubmissionContext,
    cost: int,
    source_post_id: int | None,
    attach_web_task_monitor_func=None,
    schedule_apply_interaction_func=None,
    core_domain_error_cls=None,
    dependencies=None,
):
    side_effect_dependencies = dependencies or get_default_task_core_side_effect_dependencies()
    attach_submission_side_effects(
        client_type=client_type,
        backend_task_id=backend_task_id,
        internal_user_id=internal_user_id,
        username=username,
        registry_task_id=registry_task_id,
        submission_context=submission_context,
        cost=cost,
        source_post_id=source_post_id,
        attach_web_task_monitor_func=(
            attach_web_task_monitor_func
            or (
                lambda **kwargs: attach_web_task_monitor_default(
                    dependencies=side_effect_dependencies,
                    **kwargs,
                )
            )
        ),
        schedule_apply_interaction_func=(
            schedule_apply_interaction_func
            or (
                lambda user_id, source_post_id: schedule_apply_interaction_default(
                    user_id,
                    source_post_id,
                    dependencies=side_effect_dependencies,
                )
            )
        ),
        core_domain_error_cls=core_domain_error_cls or CoreDomainError,
    )


async def finalize_monitored_web_task_success_default(
    *,
    backend_task_id: str,
    internal_user_id: int,
    username: str,
    registry_task_id: str,
    submission_context: TaskSubmissionContext,
    result_path: str,
    logger_override: logging.Logger | None = None,
):
    await finalize_monitored_web_task_success(
        backend_task_id=backend_task_id,
        internal_user_id=internal_user_id,
        username=username,
        registry_task_id=registry_task_id,
        submission_context=submission_context,
        result_path=result_path,
        persist_successful_web_history_func=persist_successful_web_history_default,
        cleanup_task_runtime_state_func=cleanup_task_runtime_state,
        logger=logger_override or logging.getLogger(__name__),
    )


async def finalize_monitored_web_task_cancellation_default(
    *,
    internal_user_id: int,
    username: str,
    cost: int,
    registry_task_id: str,
    logger_override: logging.Logger | None = None,
):
    await finalize_monitored_web_task_cancellation(
        internal_user_id=internal_user_id,
        username=username,
        cost=cost,
        registry_task_id=registry_task_id,
        finalize_task_cancellation_func=finalize_task_cancellation_default,
        logger=logger_override or logging.getLogger(__name__),
    )


async def finalize_monitored_web_task_failure_default(
    *,
    internal_user_id: int,
    username: str,
    cost: int,
    registry_task_id: str,
    final_status: str | None,
    logger_override: logging.Logger | None = None,
):
    await finalize_monitored_web_task_failure(
        internal_user_id=internal_user_id,
        username=username,
        cost=cost,
        registry_task_id=registry_task_id,
        final_status=final_status,
        finalize_task_failure_func=finalize_task_failure_default,
        logger=logger_override or logging.getLogger(__name__),
    )


async def monitor_task_and_release_lock_default(
    backend_task_id: str,
    internal_user_id: int,
    username: str,
    registry_task_id: str,
    submission_context: TaskSubmissionContext,
    cost: int = 0,
    logger_override: logging.Logger | None = None,
    dependencies=None,
):
    if dependencies is None and logger_override is not None:
        dependencies = build_default_task_core_monitor_dependencies(
            normalize_terminal_status_func=normalize_terminal_status,
            finalize_success_func=finalize_monitored_web_task_success_default,
            finalize_cancellation_func=finalize_monitored_web_task_cancellation_default,
            finalize_failure_func=finalize_monitored_web_task_failure_default,
            logger_override=logger_override,
        )
    else:
        dependencies = dependencies or get_default_task_core_monitor_dependencies()
    await monitor_task_and_release_lock(
        backend_task_id=backend_task_id,
        internal_user_id=internal_user_id,
        username=username,
        registry_task_id=registry_task_id,
        submission_context=submission_context,
        cost=cost,
        monitor_progress_func=dependencies.monitor_progress_func,
        normalize_terminal_status_func=dependencies.normalize_terminal_status_func,
        finalize_success_func=dependencies.finalize_success_func,
        finalize_cancellation_func=dependencies.finalize_cancellation_func,
        finalize_failure_func=dependencies.finalize_failure_func,
        logger=dependencies.logger,
    )
