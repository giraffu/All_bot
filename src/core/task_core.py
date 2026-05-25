import asyncio
import logging
from typing import Optional

from config import MINIO_BUCKET
from src.core.task_core_input_preparation import (
    process_input_path as _process_input_path_impl,
    validate_local_input_paths as _validate_local_input_paths_impl,
)
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
from src.core.task_core_finalization import (
    finalize_task_cancellation_default as _finalize_task_cancellation_default,
    finalize_task_failure_default as _finalize_task_failure_default,
    refund_cancelled_task_default as _refund_cancelled_task_default,
)
from src.core.task_core_dependencies import (
    TaskCoreProcessDependencies,
)
from src.core.task_core_default_dependencies import (
    build_default_task_core_persistence_dependencies,
    build_default_task_core_process_dependencies as _build_task_core_process_dependencies_impl,
)
from src.core.task_core_persistence import (
    persist_successful_task_result_default as _persist_successful_task_result_default,
)
from src.core.task_core_submission import (
    compensate_failed_submission_default as _compensate_failed_submission,
    execute_task_submission_saga_default as _execute_task_submission_saga,
)
from src.core.task_core_runtime import (
    cancel_user_task,
    force_terminate_task,
    get_system_task_stats,
    sync_user_concurrency,
)
from src.core.task_core_types import (
    ConcurrencyLimitError,
    CoreDomainError,
    InsufficientCreditsError,
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
from src.core.task_core_video_request import build_video_task_request
from src.core.task_core_web_monitor import (
    attach_submission_side_effects_default as _attach_submission_side_effects,
    finalize_monitored_web_task_success_default as _finalize_monitored_web_task_success,
    monitor_task_and_release_lock_default as _monitor_task_and_release_lock_default,
    normalize_submission_side_effect_plan as _normalize_submission_side_effect_plan,
)
from src.core.task_core_web_history_warmup import (
    schedule_web_history_r2_warmup_default as _schedule_web_history_r2_warmup_default,
)
from src.logger import UserLogger
from src.task_core_provider_setup import ensure_task_core_service_providers_registered

logger = logging.getLogger(__name__)

ensure_task_core_service_providers_registered()

__all__ = [
    "ConcurrencyLimitError",
    "CoreDomainError",
    "InsufficientCreditsError",
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
    "cancel_user_task",
    "extract_media_metadata_from_bytes_best_effort",
    "extract_media_metadata_from_storage_best_effort",
    "force_terminate_task",
    "generate_and_upload_thumbnail",
    "get_system_task_stats",
    "is_task_backend_busy_error",
    "persist_successful_task_result",
    "process_and_submit_task",
    "get_default_task_core_process_dependencies",
    "resolve_storage_object",
    "sync_user_concurrency",
]

def get_default_task_core_process_dependencies() -> TaskCoreProcessDependencies:
    return _build_task_core_process_dependencies()


def _build_task_core_process_dependencies() -> TaskCoreProcessDependencies:
    from src.constants import VIDEO_TASK_TYPES

    return _build_task_core_process_dependencies_impl(
        video_task_types=VIDEO_TASK_TYPES,
        build_video_task_request_func=build_video_task_request,
        check_concurrency_lock_func=check_concurrency_lock,
        check_and_deduct_credits_func=check_and_deduct_credits,
        execute_task_submission_saga_func=_execute_task_submission_saga,
        attach_submission_side_effects_func=_attach_submission_side_effects,
        compensate_failed_submission_func=_compensate_failed_submission,
        release_concurrency_lock_func=release_concurrency_lock,
        get_strategy_func=StrategyFactory.get_strategy,
        user_logger_factory=UserLogger,
        validate_local_input_paths_func=_validate_local_input_paths_impl,
        get_user_priority_and_identity_func=get_user_priority_and_identity,
        load_prompts_func=load_prompts,
        process_input_path_func=_process_input_path_impl,
        bucket_name=MINIO_BUCKET,
        shield_func=asyncio.shield,
        logger_override=logger,
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
    postprocess_plan: TaskPersistencePostprocessPlan | None = None,
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
    dependencies: TaskCoreProcessDependencies | None = None,
) -> dict:
    dependencies = dependencies or get_default_task_core_process_dependencies()
    submission_side_effect_plan = _normalize_submission_side_effect_plan(
        submission_side_effect_plan=submission_side_effect_plan,
        client_type=client_type,
        source_post_id=source_post_id,
    )
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
                backend_task_id=execution_result.backend_task_id,
                internal_user_id=user_id,
                username=username,
                registry_task_id=registry_task_id,
                submission_context=execution_result.submission_context,
                cost=cost if deduct_quota else 0,
                submission_side_effect_plan=submission_side_effect_plan,
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
