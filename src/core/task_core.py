import asyncio
import logging
from typing import Optional

from config import MINIO_BUCKET
from src.core.task_core_input_preparation import (
    prepare_task_submission_payload as _prepare_task_submission_payload_impl,
    process_input_path as _process_input_path_impl,
    validate_local_input_paths as _validate_local_input_paths_impl,
)
from src.core.media_paths import resolve_storage_object
from src.core.media_processor import (
    extract_media_metadata_from_bytes_best_effort,
    extract_media_metadata_from_storage_best_effort,
    generate_and_upload_thumbnail,
)
from src.core.task_core_finalization import (
    finalize_task_cancellation as _finalize_task_cancellation_impl,
    finalize_task_failure as _finalize_task_failure_impl,
    finalize_terminated_task as _finalize_terminated_task_impl,
    handle_failed_task_exception as _handle_failed_task_exception_impl,
    refund_cancelled_task as _refund_cancelled_task_impl,
    refund_failed_task as _refund_failed_task_impl,
)
from src.core.task_core_dependencies import (
    TaskCoreFinalizationDependencies,
    TaskCoreMonitorDependencies,
    TaskCorePersistenceDependencies,
    TaskCoreProcessDependencies,
    TaskCoreRuntimeDependencies,
    TaskCoreSideEffectDependencies,
    TaskCoreSubmissionDependencies,
    TaskCoreWarmupDependencies,
)
from src.core.task_core_persistence import (
    _persist_successful_web_history as _persist_successful_web_history_impl,
    persist_successful_task_result as _persist_successful_task_result_impl,
)
from src.core.task_core_submission import (
    compensate_failed_submission as _compensate_failed_submission_impl,
    dispatch_registered_task as _dispatch_registered_task_impl,
    execute_task_submission_saga as _execute_task_submission_saga_impl,
    register_task_submission as _register_task_submission_impl,
)
from src.core.task_core_runtime import (
    cancel_user_task,
    cleanup_task_runtime_state as _cleanup_task_runtime_state_impl,
    force_terminate_task as _force_terminate_task_impl,
    get_system_task_stats,
    sync_user_concurrency,
)
from src.core.task_core_types import (
    ConcurrencyLimitError,
    CoreDomainError,
    InsufficientCreditsError,
    TaskCancellationFinalizationResult,
    TaskFailureFinalizationResult,
    TaskSubmissionContext,
    TaskSubmissionExecutionResult,
    TaskSuccessPersistenceResult,
    TaskTerminationFinalizationResult,
    VideoTaskRequest,
    build_failed_task_user_message,
    build_video_task_request,
    infer_requested_billing_resolution,
    infer_requested_output_metadata,
    is_task_backend_busy_error,
    normalize_terminal_status,
)
from src.core.task_core_web_monitor import (
    attach_web_task_monitor as _attach_web_task_monitor_impl,
    finalize_monitored_web_task_cancellation as _finalize_monitored_web_task_cancellation_impl,
    finalize_monitored_web_task_failure as _finalize_monitored_web_task_failure_impl,
    finalize_monitored_web_task_success as _finalize_monitored_web_task_success_impl,
    monitor_task_and_release_lock as _monitor_task_and_release_lock_impl,
)
from src.core.task_core_web_history_warmup import (
    schedule_web_history_r2_warmup as _schedule_web_history_r2_warmup_impl,
)
from src.logger import UserLogger
from src.services.image_service import image_service
from src.services.storage import storage
from src.services.task_registry import TaskRegistry

logger = logging.getLogger(__name__)

__all__ = [
    "ConcurrencyLimitError",
    "CoreDomainError",
    "InsufficientCreditsError",
    "TaskCancellationFinalizationResult",
    "TaskFailureFinalizationResult",
    "TaskSubmissionContext",
    "TaskSubmissionExecutionResult",
    "TaskSuccessPersistenceResult",
    "TaskTerminationFinalizationResult",
    "VideoTaskRequest",
    "build_failed_task_user_message",
    "_infer_requested_billing_resolution",
    "_infer_requested_output_metadata",
    "cancel_user_task",
    "cleanup_task_runtime_state",
    "extract_media_metadata_from_bytes_best_effort",
    "extract_media_metadata_from_storage_best_effort",
    "finalize_task_cancellation",
    "finalize_task_failure",
    "finalize_terminated_task",
    "force_terminate_task",
    "generate_and_upload_thumbnail",
    "get_system_task_stats",
    "handle_failed_task_exception",
    "is_task_backend_busy_error",
    "persist_successful_task_result",
    "process_and_submit_task",
    "refund_cancelled_task",
    "refund_failed_task",
    "resolve_storage_object",
    "schedule_web_history_r2_warmup",
    "storage",
    "sync_user_concurrency",
]

_infer_requested_output_metadata = infer_requested_output_metadata
_infer_requested_billing_resolution = infer_requested_billing_resolution


def _build_task_core_warmup_dependencies() -> TaskCoreWarmupDependencies:
    return TaskCoreWarmupDependencies(
        resolve_storage_object_func=resolve_storage_object,
        copy_to_r2_func=storage.async_copy_to_r2,
        generate_and_upload_thumbnail_func=generate_and_upload_thumbnail,
        prune_user_web_history_r2_cache_func=storage.async_prune_user_web_history_r2_cache,
        create_task_func=asyncio.create_task,
        logger=logger,
    )


def _build_task_core_runtime_dependencies() -> TaskCoreRuntimeDependencies:
    return TaskCoreRuntimeDependencies(
        release_concurrency_lock_func=release_concurrency_lock,
        remove_task_func=TaskRegistry.remove_task,
    )


def _build_task_core_submission_dependencies() -> TaskCoreSubmissionDependencies:
    from src.services.redis_client import redis_client

    return TaskCoreSubmissionDependencies(
        add_task_func=TaskRegistry.add_task,
        update_backend_task_id_func=TaskRegistry.update_backend_task_id,
        mark_task_status_func=TaskRegistry.mark_task_status,
        remove_task_func=TaskRegistry.remove_task,
        add_pending_refund_func=redis_client.add_pending_refund,
        dispatch_to_worker_func=dispatch_to_worker,
        is_task_backend_busy_error_func=is_task_backend_busy_error,
        logger=logger,
    )


def _build_task_core_process_dependencies() -> TaskCoreProcessDependencies:
    from src.constants import VIDEO_TASK_TYPES

    return TaskCoreProcessDependencies(
        get_strategy_func=StrategyFactory.get_strategy,
        video_task_types=set(VIDEO_TASK_TYPES),
        build_video_task_request_func=build_video_task_request,
        check_concurrency_lock_func=check_concurrency_lock,
        prepare_task_submission_payload_func=_prepare_task_submission_payload,
        check_and_deduct_credits_func=check_and_deduct_credits,
        execute_task_submission_saga_func=_execute_task_submission_saga,
        attach_submission_side_effects_func=_attach_submission_side_effects,
        compensate_failed_submission_func=_compensate_failed_submission,
        release_concurrency_lock_func=release_concurrency_lock,
        shield_func=asyncio.shield,
        logger=logger,
    )


def _build_task_core_persistence_dependencies() -> TaskCorePersistenceDependencies:
    return TaskCorePersistenceDependencies(
        user_logger_factory=UserLogger,
        extract_media_metadata_from_bytes_best_effort_func=(
            extract_media_metadata_from_bytes_best_effort
        ),
        extract_media_metadata_from_storage_best_effort_func=(
            extract_media_metadata_from_storage_best_effort
        ),
        schedule_web_history_r2_warmup_func=schedule_web_history_r2_warmup,
        refresh_user_group_func=None,
    )


def _build_task_core_monitor_dependencies() -> TaskCoreMonitorDependencies:
    return TaskCoreMonitorDependencies(
        monitor_progress_func=image_service.monitor_progress,
        normalize_terminal_status_func=normalize_terminal_status,
        finalize_success_func=_finalize_monitored_web_task_success,
        finalize_cancellation_func=_finalize_monitored_web_task_cancellation,
        finalize_failure_func=_finalize_monitored_web_task_failure,
        logger=logger,
    )


def _build_task_core_finalization_dependencies() -> TaskCoreFinalizationDependencies:
    return TaskCoreFinalizationDependencies(
        refund_credits_func=refund_credits,
        cleanup_task_runtime_state_func=cleanup_task_runtime_state,
        refund_cancelled_task_func=refund_cancelled_task,
        force_terminate_task_func=force_terminate_task,
    )


def _build_task_core_side_effect_dependencies() -> TaskCoreSideEffectDependencies:
    from src.core.gallery_core import record_apply_interaction

    return TaskCoreSideEffectDependencies(
        attach_web_task_monitor_func=_attach_web_task_monitor_impl,
        monitor_web_task_func=monitor_task_and_release_lock,
        record_apply_interaction_func=record_apply_interaction,
        create_task_func=asyncio.create_task,
    )


def schedule_web_history_r2_warmup(
    *,
    user_id: int,
    task_id: str,
    output_file: str,
    media_type: str,
    source: str,
):
    dependencies = _build_task_core_warmup_dependencies()
    return _schedule_web_history_r2_warmup_impl(
        user_id=user_id,
        task_id=task_id,
        output_file=output_file,
        media_type=media_type,
        source=source,
        resolve_storage_object_func=dependencies.resolve_storage_object_func,
        copy_to_r2_func=dependencies.copy_to_r2_func,
        generate_and_upload_thumbnail_func=(
            dependencies.generate_and_upload_thumbnail_func
        ),
        prune_user_web_history_r2_cache_func=(
            dependencies.prune_user_web_history_r2_cache_func
        ),
        logger=dependencies.logger,
        create_task_func=dependencies.create_task_func,
    )


async def cleanup_task_runtime_state(
    *,
    internal_user_id: int,
    registry_task_id: str | None,
    release_lock: bool = True,
):
    dependencies = _build_task_core_runtime_dependencies()
    return await _cleanup_task_runtime_state_impl(
        internal_user_id=internal_user_id,
        registry_task_id=registry_task_id,
        release_lock=release_lock,
        release_concurrency_lock_func=dependencies.release_concurrency_lock_func,
        remove_task_func=dependencies.remove_task_func,
    )


async def force_terminate_task(task_id: str, user_id: int | None = None):
    return await _force_terminate_task_impl(
        task_id,
        user_id=user_id,
        cleanup_task_runtime_state_func=cleanup_task_runtime_state,
    )


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
) -> TaskSuccessPersistenceResult:
    dependencies = _build_task_core_persistence_dependencies()
    return await _persist_successful_task_result_impl(
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
        user_logger_factory=dependencies.user_logger_factory,
        extract_media_metadata_from_bytes_best_effort_func=(
            dependencies.extract_media_metadata_from_bytes_best_effort_func
        ),
        extract_media_metadata_from_storage_best_effort_func=(
            dependencies.extract_media_metadata_from_storage_best_effort_func
        ),
        schedule_web_history_r2_warmup_func=(
            dependencies.schedule_web_history_r2_warmup_func
        ),
        refresh_user_group_func=dependencies.refresh_user_group_func,
    )


async def _persist_successful_web_history(
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
    result_path: str,
    billing_resolution: str | None,
    output_width: int | None,
    output_height: int | None,
    output_duration: int | None,
    requested_duration: int | None,
):
    return await _persist_successful_web_history_impl(
        backend_task_id=backend_task_id,
        registry_task_id=registry_task_id,
        internal_user_id=internal_user_id,
        username=username,
        prompt=prompt,
        task_type=task_type,
        input_images=input_images,
        allow_contribute=allow_contribute,
        is_video=is_video,
        result_path=result_path,
        billing_resolution=billing_resolution,
        output_width=output_width,
        output_height=output_height,
        output_duration=output_duration,
        requested_duration=requested_duration,
        persist_successful_task_result_func=persist_successful_task_result,
    )


async def refund_cancelled_task(
    *,
    internal_user_id: int,
    username: str,
    cost: int,
    task_submitted: bool,
) -> bool:
    dependencies = _build_task_core_finalization_dependencies()
    return await _refund_cancelled_task_impl(
        internal_user_id=internal_user_id,
        username=username,
        cost=cost,
        task_submitted=task_submitted,
        refund_credits_func=dependencies.refund_credits_func,
    )


async def refund_failed_task(
    *,
    internal_user_id: int,
    username: str,
    cost: int,
    should_refund: bool,
) -> bool:
    dependencies = _build_task_core_finalization_dependencies()
    return await _refund_failed_task_impl(
        internal_user_id=internal_user_id,
        username=username,
        cost=cost,
        should_refund=should_refund,
        refund_credits_func=dependencies.refund_credits_func,
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
) -> str:
    dependencies = _build_task_core_finalization_dependencies()
    return await _handle_failed_task_exception_impl(
        internal_user_id=internal_user_id,
        username=username,
        cost=cost,
        should_refund=should_refund,
        error=error,
        generic_error_prefix=generic_error_prefix,
        refund_suffix_mode=refund_suffix_mode,
        refund_credits_func=dependencies.refund_credits_func,
    )


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
) -> TaskFailureFinalizationResult:
    dependencies = _build_task_core_finalization_dependencies()
    return await _finalize_task_failure_impl(
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


async def finalize_task_cancellation(
    *,
    internal_user_id: int,
    username: str,
    cost: int,
    task_submitted: bool,
    registry_task_id: str | None,
    release_lock: bool = True,
    explicit_user_message: str | None = None,
) -> TaskCancellationFinalizationResult:
    dependencies = _build_task_core_finalization_dependencies()
    return await _finalize_task_cancellation_impl(
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


async def finalize_terminated_task(
    *,
    registry_task_id: str,
    user_id: int | None,
    username: str,
    cost: int,
    should_refund: bool,
    refund_task_type: str,
) -> TaskTerminationFinalizationResult:
    dependencies = _build_task_core_finalization_dependencies()
    return await _finalize_terminated_task_impl(
        registry_task_id=registry_task_id,
        user_id=user_id,
        username=username,
        cost=cost,
        should_refund=should_refund,
        refund_task_type=refund_task_type,
        force_terminate_task_func=dependencies.force_terminate_task_func,
        refund_credits_func=dependencies.refund_credits_func,
    )


async def _process_input_path(
    user_logger: UserLogger,
    path: str,
    bucket_name: str = MINIO_BUCKET,
) -> str:
    return await _process_input_path_impl(
        user_logger=user_logger,
        path=path,
        bucket_name=bucket_name,
    )


from src.core.billing_core import (
    check_and_deduct_credits,
    check_concurrency_lock,
    get_user_priority_and_identity,
    refund_credits,
    release_concurrency_lock,
)
from src.core.task_dispatcher import StrategyFactory, dispatch_to_worker
from src.utils import load_prompts

def _validate_local_input_paths(
    paths_to_upload: list[str],
    bucket_name: str = MINIO_BUCKET,
):
    _validate_local_input_paths_impl(
        paths_to_upload=paths_to_upload,
        bucket_name=bucket_name,
    )


async def _prepare_task_submission_payload(
    *,
    user_id: int,
    username: str,
    task_type: str,
    inputs: dict,
    strategy,
    base_priority: int,
    is_template: bool,
    is_video_task: bool,
    video_request: VideoTaskRequest,
) -> TaskSubmissionContext:
    def _validate_local_input_paths_adapter(*, paths_to_upload: list[str], bucket_name: str):
        _ = bucket_name
        _validate_local_input_paths(paths_to_upload)

    async def _process_input_path_adapter(
        *,
        user_logger: UserLogger,
        path: str,
        bucket_name: str,
    ) -> str:
        _ = bucket_name
        return await _process_input_path(user_logger, path)

    return await _prepare_task_submission_payload_impl(
        user_id=user_id,
        username=username,
        task_type=task_type,
        inputs=inputs,
        strategy=strategy,
        base_priority=base_priority,
        is_template=is_template,
        is_video_task=is_video_task,
        video_request=video_request,
        user_logger_factory=UserLogger,
        validate_local_input_paths_func=_validate_local_input_paths_adapter,
        get_user_priority_and_identity_func=get_user_priority_and_identity,
        load_prompts_func=load_prompts,
        process_input_path_func=_process_input_path_adapter,
        bucket_name=MINIO_BUCKET,
    )


async def _register_task_submission(
    *,
    registry_task_id: str,
    user_id: int,
    username: str,
    cost: int,
    submission_context: TaskSubmissionContext,
) -> str:
    dependencies = _build_task_core_submission_dependencies()
    return await _register_task_submission_impl(
        registry_task_id=registry_task_id,
        user_id=user_id,
        username=username,
        cost=cost,
        submission_context=submission_context,
        add_task_func=dependencies.add_task_func,
    )


async def _dispatch_registered_task(
    *,
    registry_task_id: str,
    task_type: str,
    inputs: dict,
    final_priority: int,
) -> str:
    dependencies = _build_task_core_submission_dependencies()
    return await _dispatch_registered_task_impl(
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


async def _execute_task_submission_saga(
    *,
    task_type: str,
    inputs: dict,
    registry_task_id: str,
    cost: int,
    submission_context: TaskSubmissionContext,
) -> TaskSubmissionExecutionResult:
    return await _execute_task_submission_saga_impl(
        task_type=task_type,
        inputs=inputs,
        registry_task_id=registry_task_id,
        cost=cost,
        submission_context=submission_context,
        register_task_submission_func=_register_task_submission,
        dispatch_registered_task_func=_dispatch_registered_task,
    )


async def _compensate_failed_submission(
    *,
    user_id: int,
    username: str,
    cost: int,
    error: Exception,
    credits_deducted: bool,
    registry_task_id: str,
):
    dependencies = _build_task_core_submission_dependencies()
    await _compensate_failed_submission_impl(
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


def _attach_web_task_monitor(
    *,
    backend_task_id: str,
    internal_user_id: int,
    username: str,
    registry_task_id: str,
    submission_context: TaskSubmissionContext,
    cost: int,
):
    dependencies = _build_task_core_side_effect_dependencies()
    dependencies.attach_web_task_monitor_func(
        backend_task_id=backend_task_id,
        internal_user_id=internal_user_id,
        username=username,
        registry_task_id=registry_task_id,
        submission_context=submission_context,
        cost=cost,
        monitor_web_task_func=dependencies.monitor_web_task_func,
    )


def _schedule_apply_interaction(user_id: int, source_post_id: Optional[int]):
    if not source_post_id:
        return
    dependencies = _build_task_core_side_effect_dependencies()
    dependencies.create_task_func(
        dependencies.record_apply_interaction_func(user_id, source_post_id)
    )


def _attach_submission_side_effects(
    *,
    client_type: str,
    backend_task_id: str,
    internal_user_id: int,
    username: str,
    registry_task_id: str,
    submission_context: TaskSubmissionContext,
    cost: int,
    source_post_id: Optional[int],
):
    if client_type == "web":
        try:
            _attach_web_task_monitor(
                backend_task_id=backend_task_id,
                internal_user_id=internal_user_id,
                username=username,
                registry_task_id=registry_task_id,
                submission_context=submission_context,
                cost=cost,
            )
        except Exception as e:
            raise CoreDomainError(f"后台监控挂载失败: {e}")

    _schedule_apply_interaction(internal_user_id, source_post_id)


async def _finalize_monitored_web_task_success(
    *,
    backend_task_id: str,
    internal_user_id: int,
    username: str,
    registry_task_id: str,
    submission_context: TaskSubmissionContext,
    result_path: str,
):
    await _finalize_monitored_web_task_success_impl(
        backend_task_id=backend_task_id,
        internal_user_id=internal_user_id,
        username=username,
        registry_task_id=registry_task_id,
        submission_context=submission_context,
        result_path=result_path,
        persist_successful_web_history_func=_persist_successful_web_history,
        cleanup_task_runtime_state_func=cleanup_task_runtime_state,
        logger=logger,
    )


async def _finalize_monitored_web_task_cancellation(
    *,
    internal_user_id: int,
    username: str,
    cost: int,
    registry_task_id: str,
):
    await _finalize_monitored_web_task_cancellation_impl(
        internal_user_id=internal_user_id,
        username=username,
        cost=cost,
        registry_task_id=registry_task_id,
        finalize_task_cancellation_func=finalize_task_cancellation,
        logger=logger,
    )


async def _finalize_monitored_web_task_failure(
    *,
    internal_user_id: int,
    username: str,
    cost: int,
    registry_task_id: str,
    final_status: str | None,
):
    await _finalize_monitored_web_task_failure_impl(
        internal_user_id=internal_user_id,
        username=username,
        cost=cost,
        registry_task_id=registry_task_id,
        final_status=final_status,
        finalize_task_failure_func=finalize_task_failure,
        logger=logger,
    )

async def monitor_task_and_release_lock(
    backend_task_id: str,
    internal_user_id: int,
    username: str,
    registry_task_id: str,
    submission_context: TaskSubmissionContext,
    cost: int = 0,
):
    dependencies = _build_task_core_monitor_dependencies()
    """
    Background task to monitor progress and release concurrency lock.
    """
    await _monitor_task_and_release_lock_impl(
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
) -> dict:
    dependencies = _build_task_core_process_dependencies()
    strategy = dependencies.get_strategy_func(task_type)
    cost = strategy.get_cost(inputs)
    is_video_task = task_type in dependencies.video_task_types

    video_request = (
        dependencies.build_video_task_request_func(task_type, inputs)
        if is_video_task
        else VideoTaskRequest()
    )

    if check_lock:
        can_run, err = await dependencies.check_concurrency_lock_func(user_id)
        if not can_run:
            raise ConcurrencyLimitError(err)

    task_submitted_successfully = False
    credits_deducted = False
    registry_task_id = task_id

    try:
        submission_context = await dependencies.prepare_task_submission_payload_func(
            user_id=user_id,
            username=username,
            task_type=task_type,
            inputs=inputs,
            strategy=strategy,
            base_priority=base_priority,
            is_template=is_template,
            is_video_task=is_video_task,
            video_request=video_request,
        )

        if deduct_quota:
            success, err = await dependencies.check_and_deduct_credits_func(
                user_id, cost, task_type, username
            )
            if not success:
                raise InsufficientCreditsError(err)
            credits_deducted = True

        try:
            execution_result = await dependencies.execute_task_submission_saga_func(
                task_type=task_type,
                inputs=inputs,
                registry_task_id=registry_task_id,
                cost=cost,
                submission_context=submission_context,
            )
            registry_task_id = execution_result.registry_task_id
            dependencies.attach_submission_side_effects_func(
                client_type=client_type,
                backend_task_id=execution_result.backend_task_id,
                internal_user_id=user_id,
                username=username,
                registry_task_id=registry_task_id,
                submission_context=execution_result.submission_context,
                cost=cost if deduct_quota else 0,
                source_post_id=source_post_id,
            )

            task_submitted_successfully = True

            return {
                "task_id": registry_task_id,
                "registry_task_id": registry_task_id,
                "backend_task_id": execution_result.backend_task_id,
                "cost": cost,
                "saved_inputs": execution_result.submission_context.saved_inputs,
            }

        except Exception as e:
            dependencies.logger.error(f"Saga Execute Failed: {e}")
            await dependencies.compensate_failed_submission_func(
                user_id=user_id,
                username=username,
                cost=cost,
                error=e,
                credits_deducted=credits_deducted,
                registry_task_id=registry_task_id,
            )
            raise CoreDomainError(f"系统派发失败，灵石已全额退还。错误: {str(e)}")

    finally:
        # 兜底保障：确保并发锁释放
        if check_lock and not task_submitted_successfully:
            await dependencies.shield_func(
                dependencies.release_concurrency_lock_func(user_id)
            )
