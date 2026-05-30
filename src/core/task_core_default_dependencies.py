import asyncio
import logging
from functools import lru_cache

from src.core.async_side_effect_runner import get_default_async_side_effect_runner
from src.core.billing_core import release_concurrency_lock
from src.core.media_paths import resolve_storage_object
from src.core.media_processor import (
    extract_media_metadata_from_bytes_best_effort,
    extract_media_metadata_from_storage_best_effort,
    generate_and_upload_thumbnail,
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
from src.core.task_core_input_preparation import (
    prepare_task_submission_payload as prepare_task_submission_payload_impl,
)
from src.core.task_core_types import CoreDomainError
from src.core.task_core_dependency_builders import (
    build_task_core_finalization_dependencies,
    build_task_core_monitor_dependencies,
    build_task_core_persistence_dependencies,
    build_task_core_process_dependencies,
    build_task_core_runtime_dependencies,
    build_task_core_side_effect_dependencies,
    build_task_core_submission_dependencies,
    build_task_core_warmup_dependencies,
)
from src.core.task_core_service_providers import (
    build_task_core_image_capabilities,
    build_task_core_permission_capabilities,
    build_task_core_runtime_capabilities,
    build_task_core_storage_capabilities,
    build_task_core_submission_outbox_capabilities,
    build_task_core_task_registry_capabilities,
)
from src.core.task_core_error_helpers import is_task_backend_busy_error
from src.core.task_dispatcher import dispatch_to_worker
from src.logger import UserLogger

logger = logging.getLogger("src.core.task_core")


@lru_cache(maxsize=1)
def get_default_task_core_async_runner():
    return get_default_async_side_effect_runner()


def build_default_task_core_warmup_dependencies(
    *,
    create_task_func=None,
    resolve_storage_object_func=resolve_storage_object,
    generate_and_upload_thumbnail_func=generate_and_upload_thumbnail,
    logger_override=logger,
) -> TaskCoreWarmupDependencies:
    storage_capabilities = build_task_core_storage_capabilities()
    if create_task_func is None:
        create_task_func = get_default_task_core_async_runner().schedule
    return build_task_core_warmup_dependencies(
        copy_to_r2_func=storage_capabilities.copy_to_r2_func,
        prune_user_web_history_r2_cache_func=(
            storage_capabilities.prune_user_web_history_r2_cache_func
        ),
        resolve_storage_object_func=resolve_storage_object_func,
        generate_and_upload_thumbnail_func=generate_and_upload_thumbnail_func,
        create_task_func=create_task_func,
        logger=logger_override,
    )


def build_default_task_core_runtime_dependencies(
    *,
    release_concurrency_lock_func=release_concurrency_lock,
) -> TaskCoreRuntimeDependencies:
    registry_capabilities = build_task_core_task_registry_capabilities()
    runtime_capabilities = build_task_core_runtime_capabilities()
    return build_task_core_runtime_dependencies(
        remove_task_func=registry_capabilities.remove_task_func,
        release_concurrency_lock_func=release_concurrency_lock_func,
        get_active_tasks_func=runtime_capabilities.get_active_tasks_func,
        get_all_user_concurrencies_func=(
            runtime_capabilities.get_all_user_concurrencies_func
        ),
        cancel_task_func=runtime_capabilities.cancel_task_func,
        get_task_func=runtime_capabilities.get_task_func,
        find_task_by_backend_task_id_func=(
            runtime_capabilities.find_task_by_backend_task_id_func
        ),
        set_runtime_value_func=runtime_capabilities.set_runtime_value_func,
        expire_runtime_value_func=runtime_capabilities.expire_runtime_value_func,
        delete_runtime_value_func=runtime_capabilities.delete_runtime_value_func,
    )


def build_default_task_core_submission_dependencies(
    *,
    dispatch_to_worker_func=dispatch_to_worker,
    is_task_backend_busy_error_func=is_task_backend_busy_error,
    logger_override=logger,
) -> TaskCoreSubmissionDependencies:
    registry_capabilities = build_task_core_task_registry_capabilities()
    outbox_capabilities = build_task_core_submission_outbox_capabilities()
    return build_task_core_submission_dependencies(
        add_task_func=registry_capabilities.add_task_func,
        update_backend_task_id_func=registry_capabilities.update_backend_task_id_func,
        mark_task_status_func=registry_capabilities.mark_task_status_func,
        remove_task_func=registry_capabilities.remove_task_func,
        add_pending_refund_func=outbox_capabilities.add_pending_refund_func,
        dispatch_to_worker_func=dispatch_to_worker_func,
        is_task_backend_busy_error_func=is_task_backend_busy_error_func,
        logger=logger_override,
    )


def build_default_task_core_persistence_dependencies(
    *,
    schedule_web_history_r2_warmup_func,
    user_logger_factory=UserLogger,
    extract_media_metadata_from_bytes_best_effort_func=(
        extract_media_metadata_from_bytes_best_effort
    ),
    extract_media_metadata_from_storage_best_effort_func=(
        extract_media_metadata_from_storage_best_effort
    ),
) -> TaskCorePersistenceDependencies:
    image_capabilities = build_task_core_image_capabilities()
    permission_capabilities = build_task_core_permission_capabilities()
    return build_task_core_persistence_dependencies(
        download_result_func=image_capabilities.download_result_func,
        download_video_result_func=image_capabilities.download_video_result_func,
        refresh_user_group_func=permission_capabilities.refresh_user_group_func,
        user_logger_factory=user_logger_factory,
        extract_media_metadata_from_bytes_best_effort_func=(
            extract_media_metadata_from_bytes_best_effort_func
        ),
        extract_media_metadata_from_storage_best_effort_func=(
            extract_media_metadata_from_storage_best_effort_func
        ),
        schedule_web_history_r2_warmup_func=schedule_web_history_r2_warmup_func,
    )

def build_default_task_core_monitor_dependencies(
    *,
    normalize_terminal_status_func,
    finalize_success_func,
    finalize_cancellation_func,
    finalize_failure_func,
    logger_override=logger,
) -> TaskCoreMonitorDependencies:
    image_capabilities = build_task_core_image_capabilities()
    return build_task_core_monitor_dependencies(
        monitor_progress_func=image_capabilities.monitor_progress_func,
        normalize_terminal_status_func=normalize_terminal_status_func,
        finalize_success_func=finalize_success_func,
        finalize_cancellation_func=finalize_cancellation_func,
        finalize_failure_func=finalize_failure_func,
        logger=logger_override,
    )


def build_default_task_core_finalization_dependencies(
    *,
    refund_credits_func,
    cleanup_task_runtime_state_func,
    refund_cancelled_task_func,
    force_terminate_task_func,
) -> TaskCoreFinalizationDependencies:
    return build_task_core_finalization_dependencies(
        refund_credits_func=refund_credits_func,
        cleanup_task_runtime_state_func=cleanup_task_runtime_state_func,
        refund_cancelled_task_func=refund_cancelled_task_func,
        force_terminate_task_func=force_terminate_task_func,
    )


def build_default_task_core_side_effect_dependencies(
    *,
    attach_web_task_monitor_func,
    monitor_web_task_func,
    record_apply_interaction_func,
    create_task_func=None,
) -> TaskCoreSideEffectDependencies:
    if create_task_func is None:
        create_task_func = get_default_task_core_async_runner().schedule
    return build_task_core_side_effect_dependencies(
        attach_web_task_monitor_func=attach_web_task_monitor_func,
        monitor_web_task_func=monitor_web_task_func,
        record_apply_interaction_func=record_apply_interaction_func,
        create_task_func=create_task_func,
    )


def build_default_task_core_process_dependencies(
    *,
    video_task_types,
    build_video_task_request_func,
    check_concurrency_lock_func,
    check_and_deduct_credits_func,
    execute_task_submission_saga_func,
    attach_submission_side_effects_func,
    compensate_failed_submission_func,
    release_concurrency_lock_func,
    get_strategy_func,
    user_logger_factory,
    validate_local_input_paths_func,
    get_user_priority_and_identity_func,
    load_prompts_func,
    process_input_path_func,
    bucket_name,
    shield_func=asyncio.shield,
    logger_override=logger,
) -> TaskCoreProcessDependencies:
    async def prepare_task_submission_payload_func(**kwargs):
        return await prepare_task_submission_payload_impl(
            user_id=kwargs["user_id"],
            username=kwargs["username"],
            task_type=kwargs["task_type"],
            inputs=kwargs["inputs"],
            strategy=kwargs["strategy"],
            base_priority=kwargs["base_priority"],
            is_template=kwargs["is_template"],
            is_video_task=kwargs["is_video_task"],
            video_request=kwargs["video_request"],
            user_logger_factory=user_logger_factory,
            validate_local_input_paths_func=validate_local_input_paths_func,
            get_user_priority_and_identity_func=get_user_priority_and_identity_func,
            load_prompts_func=load_prompts_func,
            process_input_path_func=process_input_path_func,
            bucket_name=bucket_name,
        )

    return build_task_core_process_dependencies(
        get_strategy_func=get_strategy_func,
        video_task_types=video_task_types,
        build_video_task_request_func=build_video_task_request_func,
        check_concurrency_lock_func=check_concurrency_lock_func,
        prepare_task_submission_payload_func=prepare_task_submission_payload_func,
        check_and_deduct_credits_func=check_and_deduct_credits_func,
        execute_task_submission_saga_func=execute_task_submission_saga_func,
        attach_submission_side_effects_func=attach_submission_side_effects_func,
        compensate_failed_submission_func=compensate_failed_submission_func,
        release_concurrency_lock_func=release_concurrency_lock_func,
        shield_func=shield_func,
        logger=logger_override,
    )
