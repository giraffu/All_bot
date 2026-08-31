import asyncio

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


def build_task_core_warmup_dependencies(
    *,
    copy_to_r2_func,
    prune_user_web_history_r2_cache_func,
    resolve_storage_object_func,
    generate_and_upload_thumbnail_func,
    create_task_func,
    logger,
) -> TaskCoreWarmupDependencies:
    return TaskCoreWarmupDependencies(
        resolve_storage_object_func=resolve_storage_object_func,
        copy_to_r2_func=copy_to_r2_func,
        generate_and_upload_thumbnail_func=generate_and_upload_thumbnail_func,
        prune_user_web_history_r2_cache_func=prune_user_web_history_r2_cache_func,
        create_task_func=create_task_func,
        logger=logger,
    )


def build_task_core_runtime_dependencies(
    *,
    remove_task_func,
    release_concurrency_lock_func,
    get_active_tasks_func,
    get_all_user_concurrencies_func,
    cancel_task_func,
    sync_user_concurrency_func,
    get_task_func,
    find_task_by_backend_task_id_func,
) -> TaskCoreRuntimeDependencies:
    return TaskCoreRuntimeDependencies(
        release_concurrency_lock_func=release_concurrency_lock_func,
        remove_task_func=remove_task_func,
        get_active_tasks_func=get_active_tasks_func,
        get_all_user_concurrencies_func=get_all_user_concurrencies_func,
        cancel_task_func=cancel_task_func,
        sync_user_concurrency_func=sync_user_concurrency_func,
        get_task_func=get_task_func,
        find_task_by_backend_task_id_func=find_task_by_backend_task_id_func,
    )


def build_task_core_submission_dependencies(
    *,
    add_task_func,
    update_backend_task_id_func,
    mark_task_status_func,
    remove_task_func,
    add_pending_refund_func,
    dispatch_to_worker_func,
    is_task_backend_busy_error_func,
    logger,
) -> TaskCoreSubmissionDependencies:
    return TaskCoreSubmissionDependencies(
        add_task_func=add_task_func,
        update_backend_task_id_func=update_backend_task_id_func,
        mark_task_status_func=mark_task_status_func,
        remove_task_func=remove_task_func,
        add_pending_refund_func=add_pending_refund_func,
        dispatch_to_worker_func=dispatch_to_worker_func,
        is_task_backend_busy_error_func=is_task_backend_busy_error_func,
        logger=logger,
    )


def build_task_core_process_dependencies(
    *,
    get_strategy_func,
    video_task_types,
    build_video_task_request_func,
    check_concurrency_lock_func,
    prepare_task_submission_payload_func,
    check_and_deduct_credits_func,
    execute_task_submission_saga_func,
    attach_submission_side_effects_func,
    compensate_failed_submission_func,
    release_concurrency_lock_func,
    shield_func=asyncio.shield,
    logger,
    resolve_task_cost_func=None,
) -> TaskCoreProcessDependencies:
    return TaskCoreProcessDependencies(
        get_strategy_func=get_strategy_func,
        video_task_types=set(video_task_types),
        build_video_task_request_func=build_video_task_request_func,
        check_concurrency_lock_func=check_concurrency_lock_func,
        prepare_task_submission_payload_func=prepare_task_submission_payload_func,
        check_and_deduct_credits_func=check_and_deduct_credits_func,
        execute_task_submission_saga_func=execute_task_submission_saga_func,
        attach_submission_side_effects_func=attach_submission_side_effects_func,
        compensate_failed_submission_func=compensate_failed_submission_func,
        release_concurrency_lock_func=release_concurrency_lock_func,
        shield_func=shield_func,
        logger=logger,
        resolve_task_cost_func=resolve_task_cost_func,
    )


def build_task_core_persistence_dependencies(
    *,
    download_result_func,
    download_video_result_func,
    refresh_user_group_func,
    user_logger_factory,
    extract_media_metadata_from_bytes_best_effort_func,
    extract_media_metadata_from_storage_best_effort_func,
    schedule_web_history_r2_warmup_func,
) -> TaskCorePersistenceDependencies:
    return TaskCorePersistenceDependencies(
        user_logger_factory=user_logger_factory,
        download_result_func=download_result_func,
        download_video_result_func=download_video_result_func,
        extract_media_metadata_from_bytes_best_effort_func=(
            extract_media_metadata_from_bytes_best_effort_func
        ),
        extract_media_metadata_from_storage_best_effort_func=(
            extract_media_metadata_from_storage_best_effort_func
        ),
        schedule_web_history_r2_warmup_func=schedule_web_history_r2_warmup_func,
        refresh_user_group_func=refresh_user_group_func,
    )


def build_task_core_monitor_dependencies(
    *,
    monitor_progress_func,
    normalize_terminal_status_func,
    finalize_success_func,
    finalize_cancellation_func,
    finalize_failure_func,
    logger,
) -> TaskCoreMonitorDependencies:
    return TaskCoreMonitorDependencies(
        monitor_progress_func=monitor_progress_func,
        normalize_terminal_status_func=normalize_terminal_status_func,
        finalize_success_func=finalize_success_func,
        finalize_cancellation_func=finalize_cancellation_func,
        finalize_failure_func=finalize_failure_func,
        logger=logger,
    )


def build_task_core_finalization_dependencies(
    *,
    refund_credits_func,
    cleanup_task_runtime_state_func,
    refund_cancelled_task_func,
    force_terminate_task_func,
) -> TaskCoreFinalizationDependencies:
    return TaskCoreFinalizationDependencies(
        refund_credits_func=refund_credits_func,
        cleanup_task_runtime_state_func=cleanup_task_runtime_state_func,
        refund_cancelled_task_func=refund_cancelled_task_func,
        force_terminate_task_func=force_terminate_task_func,
    )


def build_task_core_side_effect_dependencies(
    *,
    attach_web_task_monitor_func,
    monitor_web_task_func,
    record_apply_interaction_func,
    create_task_func=asyncio.create_task,
) -> TaskCoreSideEffectDependencies:
    return TaskCoreSideEffectDependencies(
        attach_web_task_monitor_func=attach_web_task_monitor_func,
        monitor_web_task_func=monitor_web_task_func,
        record_apply_interaction_func=record_apply_interaction_func,
        create_task_func=create_task_func,
    )
