import logging
from collections.abc import Awaitable, Callable
from typing import Any, Optional

from src.core.task_core_error_helpers import (
    build_failed_task_user_message,
    is_task_backend_busy_error,
    normalize_terminal_status,
)
from src.media_paths import resolve_storage_object
from src.media_processor import (
    extract_media_metadata_from_bytes_best_effort,
    extract_media_metadata_from_storage_best_effort,
    generate_and_upload_thumbnail,
)
from src.core.task_core_dependencies import (
    TaskCoreProcessDependencies,
)
from src.core.task_application import TaskApplication
from src.core.task_core_video_request import build_video_task_request
from src.core.task_core_persistence import (
    persist_successful_task_result_default as _persist_successful_task_result_default,
)
from src.core.task_core_runtime import (
    cancel_user_task,
    force_terminate_task,
    get_system_task_stats,
    sync_user_concurrency,
)
from src.core.task_dispatcher import StrategyFactory
from src.core.task_core_types import (
    ConcurrencyLimitError,
    CoreDomainError,
    InsufficientCreditsError,
    QueueCapacityError,
    SubmissionJournal,
    TaskCancellationFinalizationResult,
    TaskPersistencePostprocessPlan,
    TaskSubmissionSideEffectPlan,
    TaskFailureFinalizationResult,
    TaskSubmissionContext,
    TaskSubmissionCommand,
    TaskSubmissionExecutionResult,
    TaskSubmissionPolicy,
    TaskSuccessPersistenceResult,
    TaskTerminationFinalizationResult,
    VideoTaskRequest,
)

logger = logging.getLogger(__name__)

# Stable facade only: keep runtime-default wiring out of this file when adding new behavior.

__all__ = [
    "ConcurrencyLimitError",
    "CoreDomainError",
    "InsufficientCreditsError",
    "QueueCapacityError",
    "TaskCancellationFinalizationResult",
    "TaskFailureFinalizationResult",
    "TaskPersistencePostprocessPlan",
    "TaskSubmissionContext",
    "TaskSubmissionExecutionResult",
    "TaskSubmissionSideEffectPlan",
    "TaskSuccessPersistenceResult",
    "TaskTerminationFinalizationResult",
    "VideoTaskRequest",
    "build_failed_task_user_message",
    "build_video_task_request",
    "cancel_user_task",
    "extract_media_metadata_from_bytes_best_effort",
    "extract_media_metadata_from_storage_best_effort",
    "force_terminate_task",
    "generate_and_upload_thumbnail",
    "get_system_task_stats",
    "is_task_backend_busy_error",
    "normalize_terminal_status",
    "persist_successful_task_result",
    "process_and_submit_task",
    "StrategyFactory",
    "resolve_storage_object",
    "sync_user_concurrency",
]


class _CallbackSubmissionJournal(SubmissionJournal):
    """Temporary adapter for callers that still use the legacy callback facade."""

    def __init__(
        self,
        *,
        before_debit_func=None,
        after_debit_func=None,
        before_dispatch_func=None,
        should_compensate_func=None,
        before_compensation_func=None,
    ):
        self._before_debit_func = before_debit_func
        self._after_debit_func = after_debit_func
        self._before_dispatch_func = before_dispatch_func
        self._should_compensate_func = should_compensate_func
        self._before_compensation_func = before_compensation_func

    async def before_debit(self, **event: Any) -> None:
        if self._before_debit_func is not None:
            await self._before_debit_func(**event)

    async def after_debit(self, **event: Any) -> None:
        if self._after_debit_func is not None:
            await self._after_debit_func(**event)

    async def before_dispatch(self, **event: Any) -> None:
        if self._before_dispatch_func is not None:
            await self._before_dispatch_func(**event)

    def should_compensate(self, error: Exception):
        if self._should_compensate_func is None:
            return True
        return self._should_compensate_func(error)

    async def before_compensation(self, **event: Any) -> None:
        if self._before_compensation_func is not None:
            await self._before_compensation_func(**event)


async def persist_successful_task_result(
    *,
    backend_task_id: str,
    registry_task_id: str,
    internal_user_id: int,
    username: str,
    prompt: str,
    task_type: str,
    input_images: list[str],
    allow_contribute: bool,
    is_video: bool,
    billing_resolution: str | None,
    requested_duration: int | None,
    output_width: int | None = None,
    output_height: int | None = None,
    output_duration: int | None = None,
    result_path: str | None = None,
    result_asset: dict[str, object] | None = None,
    source: str = "bot",
    refresh_user_group_after_log: bool = False,
    warmup_web_history: bool = False,
    postprocess_plan: TaskPersistencePostprocessPlan | None = None,
    dependencies=None,
) -> TaskSuccessPersistenceResult:
    return await _persist_successful_task_result_default(
        backend_task_id=backend_task_id,
        registry_task_id=registry_task_id,
        internal_user_id=internal_user_id,
        username=username,
        prompt=prompt,
        task_type=task_type,
        input_images=input_images,
        allow_contribute=allow_contribute,
        is_video=is_video,
        billing_resolution=billing_resolution,
        requested_duration=requested_duration,
        output_width=output_width,
        output_height=output_height,
        output_duration=output_duration,
        result_path=result_path,
        result_asset=result_asset,
        source=source,
        refresh_user_group_after_log=refresh_user_group_after_log,
        warmup_web_history=warmup_web_history,
        postprocess_plan=postprocess_plan,
        dependencies=dependencies,
    )


async def process_and_submit_task(
    user_id: int,
    username: str,
    task_type: str,
    inputs: dict,
    task_id: str,
    base_priority: int = 0,
    is_template: bool = False,
    client_type: str = "web",
    deduct_quota: bool = True,
    check_lock: bool = True,
    source_post_id: Optional[int] = None,
    submission_side_effect_plan: TaskSubmissionSideEffectPlan | None = None,
    delivery_context: dict[str, Any] | None = None,
    cost_override: int | None = None,
    user_cancel_allowed: bool = True,
    submission_concurrency_idempotency_key: str | None = None,
    submission_idempotency_key: str | None = None,
    registry_metadata: dict[str, Any] | None = None,
    allow_contribute_override: bool | None = None,
    submission_prepare_timeout_seconds: float | None = None,
    submission_before_debit_func: Callable[..., Awaitable[Any]] | None = None,
    submission_after_debit_func: Callable[..., Awaitable[Any]] | None = None,
    submission_debit_timeout_seconds: float | None = None,
    submission_before_dispatch_func: Callable[..., Awaitable[Any]] | None = None,
    submission_dispatch_timeout_seconds: float | None = None,
    submission_should_compensate_func: Callable[..., Any] | None = None,
    submission_refund_idempotency_key: str | None = None,
    submission_refund_task_type: str | None = None,
    submission_release_idempotency_key: str | None = None,
    submission_before_compensation_func: Callable[..., Awaitable[Any]] | None = None,
    *,
    dependencies: TaskCoreProcessDependencies,
) -> dict:
    journal = _CallbackSubmissionJournal(
        before_debit_func=submission_before_debit_func,
        after_debit_func=submission_after_debit_func,
        before_dispatch_func=submission_before_dispatch_func,
        should_compensate_func=submission_should_compensate_func,
        before_compensation_func=submission_before_compensation_func,
    )
    return await TaskApplication(dependencies=dependencies).submit(
        TaskSubmissionCommand(
            internal_user_id=user_id,
            username=username,
            task_type=task_type,
            inputs=inputs,
            task_id=task_id,
            source_post_id=source_post_id,
            delivery_context=delivery_context,
            registry_metadata=registry_metadata,
        ),
        TaskSubmissionPolicy(
            base_priority=base_priority,
            is_template=is_template,
            client_type=client_type,
            deduct_quota=deduct_quota,
            check_lock=check_lock,
            side_effect_plan=submission_side_effect_plan,
            cost_override=cost_override,
            user_cancel_allowed=user_cancel_allowed,
            concurrency_idempotency_key=submission_concurrency_idempotency_key,
            debit_idempotency_key=submission_idempotency_key,
            allow_contribute_override=allow_contribute_override,
            prepare_timeout_seconds=submission_prepare_timeout_seconds,
            debit_timeout_seconds=submission_debit_timeout_seconds,
            dispatch_timeout_seconds=submission_dispatch_timeout_seconds,
            refund_idempotency_key=submission_refund_idempotency_key,
            refund_task_type=submission_refund_task_type,
            release_idempotency_key=submission_release_idempotency_key,
        ),
        journal,
    )
