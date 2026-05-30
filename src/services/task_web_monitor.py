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
from src.core.task_core_error_helpers import normalize_terminal_status
from src.core.task_core_persistence import persist_successful_web_history_default
from src.core.task_core_types import TaskSubmissionContext
from src.core.task_core_types import (
    CoreDomainError,
    TaskSubmissionSideEffectPlan,
)
from src.core.task_lifecycle_contract import (
    build_task_terminal_snapshot,
    is_backend_terminal_status,
    normalize_task_submission_side_effect_plan,
)
from src.core.task_core_runtime import cleanup_task_runtime_state
from src.services.task_lifecycle_runner import (
    route_backend_terminal_snapshot,
    run_monitored_task_lifecycle,
)


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
    del monitor_web_task_func, create_task_func
    from src.services.task_web_finalizer import enqueue_pending_web_finalizer

    return enqueue_pending_web_finalizer(
        backend_task_id=backend_task_id,
        internal_user_id=internal_user_id,
        username=username,
        registry_task_id=registry_task_id,
        submission_context=submission_context,
        cost=cost,
    )


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


def normalize_submission_side_effect_plan(
    *,
    submission_side_effect_plan: TaskSubmissionSideEffectPlan | None,
    client_type: str | None,
    source_post_id: int | None,
) -> TaskSubmissionSideEffectPlan:
    return normalize_task_submission_side_effect_plan(
        submission_side_effect_plan=submission_side_effect_plan,
        client_type=client_type,
        source_post_id=source_post_id,
    )


async def attach_submission_side_effects(
    *,
    client_type: str | None = None,
    backend_task_id: str,
    internal_user_id: int,
    username: str,
    registry_task_id: str,
    submission_context: TaskSubmissionContext,
    cost: int,
    source_post_id: int | None = None,
    submission_side_effect_plan: TaskSubmissionSideEffectPlan | None = None,
    attach_web_task_monitor_func,
    schedule_apply_interaction_func,
    core_domain_error_cls,
):
    submission_side_effect_plan = normalize_submission_side_effect_plan(
        submission_side_effect_plan=submission_side_effect_plan,
        client_type=client_type,
        source_post_id=source_post_id,
    )
    if submission_side_effect_plan.attach_web_monitor:
        try:
            maybe_awaitable = attach_web_task_monitor_func(
                backend_task_id=backend_task_id,
                internal_user_id=internal_user_id,
                username=username,
                registry_task_id=registry_task_id,
                submission_context=submission_context,
                cost=cost,
            )
            if asyncio.iscoroutine(maybe_awaitable):
                await maybe_awaitable
        except Exception as exc:
            raise core_domain_error_cls(f"后台监控挂载失败: {exc}")

    schedule_apply_interaction_func(
        internal_user_id, submission_side_effect_plan.source_post_id
    )


async def finalize_monitored_web_task_success(
    *,
    backend_task_id: str,
    internal_user_id: int,
    username: str,
    registry_task_id: str,
    submission_context: TaskSubmissionContext,
    result_path: str,
    extra_outputs: dict[str, object] | None,
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
            extra_outputs=extra_outputs,
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
    async def _monitor_stage():
        terminal_snapshot = build_task_terminal_snapshot(status=None)
        try:
            async for progress in monitor_progress_func(
                backend_task_id,
                submission_context.is_video_task,
            ):
                normalized_status = normalize_terminal_status_func(progress.get("status"))
                if is_backend_terminal_status(normalized_status):
                    terminal_snapshot = build_task_terminal_snapshot(
                        status=normalized_status,
                        result_path=progress.get("result_path"),
                        extra_outputs=progress.get("extra_outputs"),
                        error=progress.get("error") or progress.get("error_msg"),
                        message=progress.get("message"),
                    )
                    break
        except asyncio.CancelledError:
            logger.error("Task monitor %s cancelled.", backend_task_id)
            return build_task_terminal_snapshot(status="cancelled")
        except Exception as exc:
            logger.error(
                "Background monitoring error for task %s: %s",
                backend_task_id,
                exc,
            )
            return build_task_terminal_snapshot(
                status="error",
                error=str(exc),
            )
        return terminal_snapshot

    await run_monitored_task_lifecycle(
        monitor_stage_func=_monitor_stage,
        route_terminal_result_func=lambda terminal_snapshot: route_backend_terminal_snapshot(
            terminal_snapshot=terminal_snapshot,
            handle_success=lambda snapshot: finalize_success_func(
                backend_task_id=backend_task_id,
                internal_user_id=internal_user_id,
                username=username,
                registry_task_id=registry_task_id,
                submission_context=submission_context,
                result_path=snapshot.result_path,
                extra_outputs=snapshot.extra_outputs,
            ),
            handle_cancelled=lambda _snapshot: finalize_cancellation_func(
                internal_user_id=internal_user_id,
                username=username,
                cost=cost,
                registry_task_id=registry_task_id,
            ),
            handle_failure=lambda snapshot: finalize_failure_func(
                internal_user_id=internal_user_id,
                username=username,
                cost=cost,
                registry_task_id=registry_task_id,
                final_status=snapshot.status,
            ),
        ),
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


async def attach_submission_side_effects_default(
    *,
    client_type: str | None = None,
    backend_task_id: str,
    internal_user_id: int,
    username: str,
    registry_task_id: str,
    submission_context: TaskSubmissionContext,
    cost: int,
    source_post_id: int | None = None,
    submission_side_effect_plan: TaskSubmissionSideEffectPlan | None = None,
    attach_web_task_monitor_func=None,
    schedule_apply_interaction_func=None,
    core_domain_error_cls=None,
    dependencies=None,
):
    side_effect_dependencies = dependencies or get_default_task_core_side_effect_dependencies()
    await attach_submission_side_effects(
        client_type=client_type,
        backend_task_id=backend_task_id,
        internal_user_id=internal_user_id,
        username=username,
        registry_task_id=registry_task_id,
        submission_context=submission_context,
        cost=cost,
        source_post_id=source_post_id,
        submission_side_effect_plan=submission_side_effect_plan,
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
    extra_outputs: dict[str, object] | None = None,
    logger_override: logging.Logger | None = None,
):
    await finalize_monitored_web_task_success(
        backend_task_id=backend_task_id,
        internal_user_id=internal_user_id,
        username=username,
        registry_task_id=registry_task_id,
        submission_context=submission_context,
        result_path=result_path,
        extra_outputs=extra_outputs,
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
