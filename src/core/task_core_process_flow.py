import inspect
from dataclasses import dataclass
from typing import Any

from src.core.task_core_dependencies import TaskCoreProcessDependencies
from src.core.task_core_types import (
    ConcurrencyLimitError,
    CoreDomainError,
    InsufficientCreditsError,
    TaskSubmissionContext,
    TaskSubmissionExecutionResult,
    TaskSubmissionSideEffectPlan,
    VideoTaskRequest,
)


@dataclass(frozen=True)
class PreparedTaskSubmissionRequest:
    strategy: Any
    cost: int
    is_video_task: bool
    video_request: VideoTaskRequest


def build_prepared_task_submission_request(
    *,
    task_type: str,
    inputs: dict[str, Any],
    dependencies: TaskCoreProcessDependencies,
    cost_override: int | None = None,
) -> PreparedTaskSubmissionRequest:
    strategy = dependencies.get_strategy_func(task_type)
    is_video_task = task_type in dependencies.video_task_types
    video_request = (
        dependencies.build_video_task_request_func(task_type, inputs)
        if is_video_task
        else VideoTaskRequest()
    )
    return PreparedTaskSubmissionRequest(
        strategy=strategy,
        cost=(
            int(cost_override)
            if cost_override is not None
            else strategy.get_cost(inputs)
        ),
        is_video_task=is_video_task,
        video_request=video_request,
    )


async def ensure_submission_concurrency_lock(
    *,
    user_id: int,
    check_lock: bool,
    dependencies: TaskCoreProcessDependencies,
) -> None:
    if not check_lock:
        return
    can_run, err = await dependencies.check_concurrency_lock_func(user_id)
    if not can_run:
        raise ConcurrencyLimitError(err)


async def prepare_task_submission_context(
    *,
    user_id: int,
    username: str,
    task_type: str,
    inputs: dict[str, Any],
    base_priority: int,
    is_template: bool,
    request: PreparedTaskSubmissionRequest,
    dependencies: TaskCoreProcessDependencies,
) -> TaskSubmissionContext:
    return await dependencies.prepare_task_submission_payload_func(
        user_id=user_id,
        username=username,
        task_type=task_type,
        inputs=inputs,
        strategy=request.strategy,
        base_priority=base_priority,
        is_template=is_template,
        is_video_task=request.is_video_task,
        video_request=request.video_request,
    )


async def maybe_deduct_submission_credits(
    *,
    user_id: int,
    username: str,
    task_type: str,
    cost: int,
    deduct_quota: bool,
    dependencies: TaskCoreProcessDependencies,
) -> bool:
    if not deduct_quota:
        return False
    success, err = await dependencies.check_and_deduct_credits_func(
        user_id,
        cost,
        task_type,
        username,
    )
    if not success:
        raise InsufficientCreditsError(err)
    return True


async def execute_task_submission_attempt(
    *,
    user_id: int,
    username: str,
    task_type: str,
    inputs: dict[str, Any],
    registry_task_id: str,
    cost: int,
    deduct_quota: bool,
    submission_context: TaskSubmissionContext,
    submission_side_effect_plan: TaskSubmissionSideEffectPlan | None,
    dependencies: TaskCoreProcessDependencies,
) -> TaskSubmissionExecutionResult:
    execution_result = await dependencies.execute_task_submission_saga_func(
        task_type=task_type,
        inputs=inputs,
        registry_task_id=registry_task_id,
        cost=cost,
        credits_deducted=deduct_quota,
        submission_context=submission_context,
    )
    maybe_awaitable = dependencies.attach_submission_side_effects_func(
        backend_task_id=execution_result.backend_task_id,
        internal_user_id=user_id,
        username=username,
        registry_task_id=execution_result.registry_task_id,
        submission_context=execution_result.submission_context,
        cost=cost if deduct_quota else 0,
        submission_side_effect_plan=submission_side_effect_plan,
    )
    if inspect.isawaitable(maybe_awaitable):
        await maybe_awaitable
    return execution_result


async def compensate_failed_task_submission(
    *,
    user_id: int,
    username: str,
    cost: int,
    error: Exception,
    credits_deducted: bool,
    registry_task_id: str,
    dependencies: TaskCoreProcessDependencies,
) -> None:
    dependencies.logger.error("Saga Execute Failed: %s", error)
    await dependencies.compensate_failed_submission_func(
        user_id=user_id,
        username=username,
        cost=cost,
        error=error,
        credits_deducted=credits_deducted,
        registry_task_id=registry_task_id,
    )


def build_successful_submission_response(
    *,
    execution_result: TaskSubmissionExecutionResult,
    cost: int,
) -> dict[str, Any]:
    return {
        "task_id": execution_result.registry_task_id,
        "registry_task_id": execution_result.registry_task_id,
        "backend_task_id": execution_result.backend_task_id,
        "cost": cost,
        "saved_inputs": execution_result.submission_context.saved_inputs,
    }


async def release_submission_lock_if_needed(
    *,
    user_id: int,
    check_lock: bool,
    task_submitted_successfully: bool,
    dependencies: TaskCoreProcessDependencies,
) -> None:
    if not check_lock or task_submitted_successfully:
        return
    await dependencies.shield_func(dependencies.release_concurrency_lock_func(user_id))


def build_submission_failure_error(error: Exception) -> CoreDomainError:
    return CoreDomainError(f"系统派发失败，灵石已全额退还。错误: {str(error)}")
