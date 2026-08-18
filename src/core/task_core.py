import asyncio
import inspect
import logging
from collections.abc import Awaitable, Callable
from typing import Any, Optional

from src.core.task_core_error_helpers import (
    build_failed_task_user_message,
    is_task_backend_busy_error,
    normalize_terminal_status,
)
from src.core.media_paths import resolve_storage_object
from src.core.media_processor import (
    extract_media_metadata_from_bytes_best_effort,
    extract_media_metadata_from_storage_best_effort,
    generate_and_upload_thumbnail,
)
from src.core.task_core_dependencies import (
    TaskCoreProcessDependencies,
)
from src.core.task_core_process_flow import (
    build_prepared_task_submission_request,
    build_submission_failure_error,
    build_successful_submission_response,
    compensate_failed_task_submission,
    ensure_submission_concurrency_lock,
    execute_task_submission_attempt,
    maybe_deduct_submission_credits,
    prepare_task_submission_context,
    release_submission_lock_if_needed,
)
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
    SubmissionReconciliationPending,
    TaskCancellationFinalizationResult,
    TaskPersistencePostprocessPlan,
    TaskSubmissionSideEffectPlan,
    TaskFailureFinalizationResult,
    TaskSubmissionContext,
    TaskSubmissionExecutionResult,
    TaskSuccessPersistenceResult,
    TaskTerminationFinalizationResult,
    VideoTaskRequest,
)
from src.core.task_lifecycle_contract import (
    normalize_task_submission_side_effect_plan,
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
    "get_default_task_core_process_dependencies",
    "resolve_storage_object",
    "sync_user_concurrency",
]


def get_default_task_core_process_dependencies() -> TaskCoreProcessDependencies:
    from src.task_core_process_defaults import (
        build_runtime_default_task_core_process_dependencies,
    )

    return build_runtime_default_task_core_process_dependencies(logger_override=logger)


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
    dependencies: TaskCoreProcessDependencies | None = None,
) -> dict:
    dependencies = dependencies or get_default_task_core_process_dependencies()
    concurrency_idempotency_key = (
        submission_concurrency_idempotency_key or f"task_concurrency:{task_id}"
    )
    release_idempotency_key = (
        submission_release_idempotency_key or concurrency_idempotency_key
    )
    submission_side_effect_plan = normalize_task_submission_side_effect_plan(
        submission_side_effect_plan=submission_side_effect_plan,
        client_type=client_type,
        source_post_id=source_post_id,
    )
    request = build_prepared_task_submission_request(
        task_type=task_type,
        inputs=inputs,
        dependencies=dependencies,
        cost_override=cost_override,
    )
    await ensure_submission_concurrency_lock(
        user_id=user_id,
        task_type=task_type,
        check_lock=check_lock,
        dependencies=dependencies,
        idempotency_key=concurrency_idempotency_key,
    )

    task_submitted_successfully = False
    credits_deducted = False
    registry_task_id = task_id

    try:
        prepare_kwargs = dict(
            user_id=user_id,
            username=username,
            task_type=task_type,
            inputs=inputs,
            base_priority=base_priority,
            is_template=is_template,
            request=request,
            dependencies=dependencies,
        )
        if submission_prepare_timeout_seconds is None:
            submission_context = await prepare_task_submission_context(**prepare_kwargs)
        else:
            submission_context = await asyncio.wait_for(
                prepare_task_submission_context(**prepare_kwargs),
                timeout=float(submission_prepare_timeout_seconds),
            )
        if registry_metadata:
            submission_context.metadata.update(registry_metadata)
        if allow_contribute_override is not None:
            submission_context.allow_contribute = bool(allow_contribute_override)
        submission_context.client_type = client_type
        submission_context.user_cancel_allowed = user_cancel_allowed
        submission_context.concurrency_acquisition_key = concurrency_idempotency_key
        if delivery_context:
            submission_context.delivery_context.update(
                {
                    key: value
                    for key, value in delivery_context.items()
                    if key in {"chat_id", "message_id"} and value is not None
                }
            )

        if submission_before_debit_func is not None:
            await submission_before_debit_func(
                cost=request.cost,
                registry_task_id=registry_task_id,
            )

        debit_kwargs = dict(
            user_id=user_id,
            username=username,
            task_type=task_type,
            cost=request.cost,
            deduct_quota=deduct_quota,
            dependencies=dependencies,
            idempotency_key=submission_idempotency_key,
        )
        if submission_debit_timeout_seconds is None:
            credits_deducted = await maybe_deduct_submission_credits(**debit_kwargs)
        else:
            credits_deducted = await asyncio.wait_for(
                maybe_deduct_submission_credits(**debit_kwargs),
                timeout=float(submission_debit_timeout_seconds),
            )
        if submission_after_debit_func is not None:
            await submission_after_debit_func(
                cost=request.cost,
                registry_task_id=registry_task_id,
                credits_deducted=credits_deducted,
            )

        try:
            execution_result = await execute_task_submission_attempt(
                user_id=user_id,
                username=username,
                task_type=task_type,
                inputs=inputs,
                registry_task_id=registry_task_id,
                cost=request.cost,
                deduct_quota=deduct_quota,
                submission_context=submission_context,
                submission_side_effect_plan=submission_side_effect_plan,
                dependencies=dependencies,
                submission_before_dispatch_func=submission_before_dispatch_func,
                submission_dispatch_timeout_seconds=(
                    submission_dispatch_timeout_seconds
                ),
            )
            registry_task_id = execution_result.registry_task_id
            task_submitted_successfully = True
            return build_successful_submission_response(
                execution_result=execution_result,
                cost=request.cost,
            )

        except Exception as e:
            should_compensate = True
            if submission_should_compensate_func is not None:
                decision = submission_should_compensate_func(e)
                should_compensate = bool(
                    await decision if inspect.isawaitable(decision) else decision
                )
            if should_compensate:
                if submission_before_compensation_func is not None:
                    await submission_before_compensation_func(
                        error=e,
                        cost=request.cost,
                        registry_task_id=registry_task_id,
                        credits_deducted=credits_deducted,
                    )
                await compensate_failed_task_submission(
                    user_id=user_id,
                    username=username,
                    cost=request.cost,
                    error=e,
                    credits_deducted=credits_deducted,
                    registry_task_id=registry_task_id,
                    dependencies=dependencies,
                    refund_idempotency_key=submission_refund_idempotency_key,
                    refund_task_type=(
                        submission_refund_task_type or "refund_saga_failed"
                    ),
                )
                raise build_submission_failure_error(e)
            # The deterministic dispatch may exist. Its registry owner must
            # retain concurrency until reconciliation or terminal recovery.
            task_submitted_successfully = True
            raise SubmissionReconciliationPending(
                registry_task_id=registry_task_id,
                cost=request.cost,
            ) from e

    finally:
        await release_submission_lock_if_needed(
            user_id=user_id,
            check_lock=check_lock,
            task_submitted_successfully=task_submitted_successfully,
            dependencies=dependencies,
            release_idempotency_key=release_idempotency_key,
        )
