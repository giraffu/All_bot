import asyncio
import inspect
from dataclasses import dataclass
from typing import Any

from src.core.task_core_dependencies import TaskCoreProcessDependencies
from src.core.task_core_types import (
    ConcurrencyLimitError,
    CoreDomainError,
    InsufficientCreditsError,
    QueueCapacityError,
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


def _supports_keyword_argument(func: Any, argument_name: str) -> bool:
    """Return whether a dependency seam accepts a named keyword argument.

    Core deployments can temporarily run against an older runtime dependency
    during a narrow Bot-only rollout.  Keep the facade compatible with that
    dependency while preserving idempotency whenever the dependency supports
    it.
    """
    try:
        parameters = inspect.signature(func).parameters.values()
    except (TypeError, ValueError):
        # Builtins and wrapped callables may not expose a signature.  Prefer
        # the modern contract in that case rather than silently dropping it.
        return True
    return any(
        parameter.name == argument_name
        or parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in parameters
    )


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
    task_type: str,
    check_lock: bool,
    dependencies: TaskCoreProcessDependencies,
    idempotency_key: str | None = None,
) -> None:
    if not check_lock:
        return
    kwargs = {}
    if idempotency_key and _supports_keyword_argument(
        dependencies.check_concurrency_lock_func,
        "idempotency_key",
    ):
        kwargs["idempotency_key"] = idempotency_key
    if _supports_keyword_argument(
        dependencies.check_concurrency_lock_func,
        "task_type",
    ):
        kwargs["task_type"] = task_type
    can_run, err = await dependencies.check_concurrency_lock_func(
        user_id,
        **kwargs,
    )
    if not can_run:
        if "当前任务类型排队已达到" in str(err):
            raise QueueCapacityError(err)
        raise ConcurrencyLimitError(err)


async def prepare_task_submission_context(
    *,
    user_id: int,
    username: str,
    task_type: str,
    inputs: dict[str, Any],
    registry_task_id: str,
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
        registry_task_id=registry_task_id,
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
    idempotency_key: str | None = None,
) -> bool:
    if not deduct_quota:
        return False
    kwargs = (
        {"idempotency_key": idempotency_key}
        if idempotency_key
        and _supports_keyword_argument(
            dependencies.check_and_deduct_credits_func,
            "idempotency_key",
        )
        else {}
    )
    success, err = await dependencies.check_and_deduct_credits_func(
        user_id,
        cost,
        task_type,
        username,
        **kwargs,
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
    submission_before_dispatch_func=None,
    submission_dispatch_timeout_seconds: float | None = None,
) -> TaskSubmissionExecutionResult:
    saga_kwargs = dict(
        task_type=task_type,
        inputs=inputs,
        registry_task_id=registry_task_id,
        cost=cost,
        credits_deducted=deduct_quota,
        submission_context=submission_context,
    )
    if submission_before_dispatch_func is not None:
        saga_kwargs["before_dispatch_func"] = submission_before_dispatch_func
    if submission_dispatch_timeout_seconds is None:
        execution_result = await dependencies.execute_task_submission_saga_func(
            **saga_kwargs
        )
    else:
        execution_result = await asyncio.wait_for(
            dependencies.execute_task_submission_saga_func(**saga_kwargs),
            timeout=float(submission_dispatch_timeout_seconds),
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
    refund_idempotency_key: str | None = None,
    refund_task_type: str = "refund_saga_failed",
) -> None:
    dependencies.logger.error("Saga Execute Failed: %s", error)
    kwargs = dict(
        user_id=user_id,
        username=username,
        cost=cost,
        error=error,
        credits_deducted=credits_deducted,
        registry_task_id=registry_task_id,
        refund_task_type=refund_task_type,
    )
    if refund_idempotency_key:
        kwargs["refund_idempotency_key"] = refund_idempotency_key
    await dependencies.compensate_failed_submission_func(**kwargs)


def build_successful_submission_response(
    *,
    execution_result: TaskSubmissionExecutionResult,
    cost: int,
) -> dict[str, Any]:
    saved_inputs_getter = getattr(
        execution_result.submission_context,
        "registry_saved_inputs",
        None,
    )
    saved_inputs = (
        saved_inputs_getter()
        if callable(saved_inputs_getter)
        else list(getattr(execution_result.submission_context, "saved_inputs", []) or [])
    )
    return {
        "task_id": execution_result.registry_task_id,
        "registry_task_id": execution_result.registry_task_id,
        "backend_task_id": execution_result.backend_task_id,
        "cost": cost,
        "saved_inputs": saved_inputs,
    }


async def release_submission_lock_if_needed(
    *,
    user_id: int,
    check_lock: bool,
    task_submitted_successfully: bool,
    dependencies: TaskCoreProcessDependencies,
    release_idempotency_key: str | None = None,
) -> None:
    if not check_lock or task_submitted_successfully:
        return
    kwargs = (
        {"idempotency_key": release_idempotency_key}
        if release_idempotency_key
        and _supports_keyword_argument(
            dependencies.release_concurrency_lock_func,
            "idempotency_key",
        )
        else {}
    )
    await dependencies.shield_func(
        dependencies.release_concurrency_lock_func(user_id, **kwargs)
    )


def build_submission_failure_error(error: Exception) -> CoreDomainError:
    return CoreDomainError(f"系统派发失败，灵石已全额退还。错误: {str(error)}")
