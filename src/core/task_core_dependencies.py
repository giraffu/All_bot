from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TaskCoreWarmupDependencies:
    resolve_storage_object_func: Callable[..., Any]
    copy_to_r2_func: Callable[..., Awaitable[Any]]
    generate_and_upload_thumbnail_func: Callable[..., Awaitable[Any]]
    prune_user_web_history_r2_cache_func: Callable[..., Awaitable[Any]]
    create_task_func: Callable[..., Any]
    logger: Any


@dataclass(frozen=True)
class TaskCoreRuntimeDependencies:
    release_concurrency_lock_func: Callable[..., Awaitable[Any]]
    remove_task_func: Callable[..., Awaitable[Any]]


@dataclass(frozen=True)
class TaskCoreSubmissionDependencies:
    add_task_func: Callable[..., Awaitable[Any]]
    update_backend_task_id_func: Callable[..., Awaitable[Any]]
    mark_task_status_func: Callable[..., Awaitable[Any]]
    remove_task_func: Callable[..., Awaitable[Any]]
    add_pending_refund_func: Callable[..., Awaitable[Any]]
    dispatch_to_worker_func: Callable[..., Awaitable[Any]]
    is_task_backend_busy_error_func: Callable[[str], bool]
    logger: Any


@dataclass(frozen=True)
class TaskCoreProcessDependencies:
    get_strategy_func: Callable[[str], Any]
    video_task_types: set[str]
    build_video_task_request_func: Callable[..., Any]
    check_concurrency_lock_func: Callable[..., Awaitable[Any]]
    prepare_task_submission_payload_func: Callable[..., Awaitable[Any]]
    check_and_deduct_credits_func: Callable[..., Awaitable[Any]]
    execute_task_submission_saga_func: Callable[..., Awaitable[Any]]
    attach_submission_side_effects_func: Callable[..., Any]
    compensate_failed_submission_func: Callable[..., Awaitable[Any]]
    release_concurrency_lock_func: Callable[..., Awaitable[Any]]
    shield_func: Callable[[Awaitable[Any]], Awaitable[Any]]
    logger: Any


@dataclass(frozen=True)
class TaskCorePersistenceDependencies:
    user_logger_factory: Callable[..., Any]
    extract_media_metadata_from_bytes_best_effort_func: Callable[..., Any]
    extract_media_metadata_from_storage_best_effort_func: Callable[..., Awaitable[Any]] | Callable[..., Any]
    schedule_web_history_r2_warmup_func: Callable[..., Any]
    refresh_user_group_func: Callable[..., Awaitable[Any]] | None


@dataclass(frozen=True)
class TaskCoreMonitorDependencies:
    monitor_progress_func: Callable[..., Any]
    normalize_terminal_status_func: Callable[..., Any]
    finalize_success_func: Callable[..., Awaitable[Any]]
    finalize_cancellation_func: Callable[..., Awaitable[Any]]
    finalize_failure_func: Callable[..., Awaitable[Any]]
    logger: Any


@dataclass(frozen=True)
class TaskCoreFinalizationDependencies:
    refund_credits_func: Callable[..., Awaitable[Any]]
    cleanup_task_runtime_state_func: Callable[..., Awaitable[Any]]
    refund_cancelled_task_func: Callable[..., Awaitable[Any]]
    force_terminate_task_func: Callable[..., Awaitable[Any]]


@dataclass(frozen=True)
class TaskCoreSideEffectDependencies:
    attach_web_task_monitor_func: Callable[..., Any]
    monitor_web_task_func: Callable[..., Awaitable[Any]]
    record_apply_interaction_func: Callable[..., Awaitable[Any]]
    create_task_func: Callable[..., Any]
