import logging
from collections.abc import Awaitable, Callable
from typing import Any

from src.core.task_core_finalization import (
    finalize_task_cancellation_default,
    finalize_task_failure_default,
)
from src.core.task_core_persistence import persist_successful_web_history_default
from src.core.task_core_runtime import cleanup_task_runtime_state
from src.core.task_core_types import TaskSubmissionContext
from src.domain_config.scail2_video import is_scail2_task_type
from src.services.ltx_video_extension_service import (
    merge_ltx_history_context_into_extra_outputs,
)
from src.services.wan22_video_v2_extension_service import (
    merge_wan22_history_context_into_extra_outputs,
)


SCAIL2_HISTORY_CONTEXT_KEY = "scail2_context"


def merge_scail2_history_context_into_extra_outputs(
    *,
    task_type: str | None,
    extra_outputs: dict[str, object] | None,
    metadata: dict[str, object] | None,
) -> dict[str, object] | None:
    if not is_scail2_task_type(task_type):
        return extra_outputs
    context = {
        key: value
        for key, value in {
            "scail2_negative_prompt": (metadata or {}).get("scail2_negative_prompt"),
            "scail2_duration_seconds": (metadata or {}).get("scail2_duration_seconds"),
        }.items()
        if value is not None
    }
    if not context and not extra_outputs:
        return extra_outputs
    merged = dict(extra_outputs or {})
    if context:
        merged[SCAIL2_HISTORY_CONTEXT_KEY] = context
    return merged


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
        persisted_extra_outputs = merge_wan22_history_context_into_extra_outputs(
            task_type=submission_context.task_type,
            extra_outputs=extra_outputs,
            metadata=submission_context.metadata,
        )
        persisted_extra_outputs = merge_ltx_history_context_into_extra_outputs(
            task_type=submission_context.task_type,
            extra_outputs=persisted_extra_outputs,
            metadata=submission_context.metadata,
        )
        persisted_extra_outputs = merge_scail2_history_context_into_extra_outputs(
            task_type=submission_context.task_type,
            extra_outputs=persisted_extra_outputs,
            metadata=submission_context.metadata,
        )
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
            extra_outputs=persisted_extra_outputs,
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
        raise
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
