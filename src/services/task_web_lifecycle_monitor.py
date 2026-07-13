import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from src.core.task_core_default_dependencies import (
    build_default_task_core_monitor_dependencies,
)
from src.core.task_core_error_helpers import normalize_terminal_status
from src.core.task_core_types import TaskSubmissionContext
from src.core.task_lifecycle_contract import (
    build_task_terminal_snapshot,
    is_backend_terminal_status,
)
from src.services.task_lifecycle_runner import (
    route_backend_terminal_snapshot,
    run_monitored_task_lifecycle,
)
from src.services.task_web_terminal_finalization import (
    finalize_monitored_web_task_cancellation_default,
    finalize_monitored_web_task_failure_default,
    finalize_monitored_web_task_success_default,
)


def get_default_task_core_monitor_dependencies():
    return build_default_task_core_monitor_dependencies(
        normalize_terminal_status_func=normalize_terminal_status,
        finalize_success_func=finalize_monitored_web_task_success_default,
        finalize_cancellation_func=finalize_monitored_web_task_cancellation_default,
        finalize_failure_func=finalize_monitored_web_task_failure_default,
        logger_override=logging.getLogger(__name__),
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
