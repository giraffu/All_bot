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
from src.core.task_core_dependencies import (
    TaskCoreProcessDependencies,
)
from src.core.task_core_default_dependencies import (
    build_default_task_core_attach_submission_side_effects_func,
    build_default_task_core_process_dependencies as _build_task_core_process_dependencies_impl,
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
from src.core.task_lifecycle_contract import (
    normalize_task_submission_side_effect_plan,
)
from src.logger import UserLogger

logger = logging.getLogger(__name__)

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
    "normalize_terminal_status",
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
        attach_submission_side_effects_func=(
            build_default_task_core_attach_submission_side_effects_func(
                core_domain_error_cls=CoreDomainError
            )
        ),
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

from src.core.billing_core import (
    check_and_deduct_credits,
    check_concurrency_lock,
    get_user_priority_and_identity,
    release_concurrency_lock,
)
from src.core.task_dispatcher import StrategyFactory
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
    submission_side_effect_plan = normalize_task_submission_side_effect_plan(
        submission_side_effect_plan=submission_side_effect_plan,
        client_type=client_type,
        source_post_id=source_post_id,
    )
    request = build_prepared_task_submission_request(
        task_type=task_type,
        inputs=inputs,
        dependencies=dependencies,
    )
    await ensure_submission_concurrency_lock(
        user_id=user_id,
        check_lock=check_lock,
        dependencies=dependencies,
    )

    task_submitted_successfully = False
    credits_deducted = False
    registry_task_id = task_id

    try:
        submission_context = await prepare_task_submission_context(
            user_id=user_id,
            username=username,
            task_type=task_type,
            inputs=inputs,
            base_priority=base_priority,
            is_template=is_template,
            request=request,
            dependencies=dependencies,
        )

        credits_deducted = await maybe_deduct_submission_credits(
            user_id=user_id,
            username=username,
            task_type=task_type,
            cost=request.cost,
            deduct_quota=deduct_quota,
            dependencies=dependencies,
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
            )
            registry_task_id = execution_result.registry_task_id
            task_submitted_successfully = True
            return build_successful_submission_response(
                execution_result=execution_result,
                cost=request.cost,
            )

        except Exception as e:
            await compensate_failed_task_submission(
                user_id=user_id,
                username=username,
                cost=request.cost,
                error=e,
                credits_deducted=credits_deducted,
                registry_task_id=registry_task_id,
                dependencies=dependencies,
            )
            raise build_submission_failure_error(e)

    finally:
        await release_submission_lock_if_needed(
            user_id=user_id,
            check_lock=check_lock,
            task_submitted_successfully=task_submitted_successfully,
            dependencies=dependencies,
        )
