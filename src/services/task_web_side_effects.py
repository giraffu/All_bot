import asyncio
import inspect
from collections.abc import Awaitable, Callable

from src.core.task_core_default_dependencies import (
    build_default_task_core_side_effect_dependencies,
)
from src.core.task_core_types import CoreDomainError, TaskSubmissionContext
from src.core.task_core_types import (
    TaskSubmissionSideEffectPlan,
)
from src.core.task_lifecycle_contract import (
    normalize_task_submission_side_effect_plan,
)
from src.services.task_web_lifecycle_monitor import monitor_task_and_release_lock_default


def get_default_task_core_side_effect_dependencies():
    from src.core.gallery_core import record_apply_interaction

    return build_default_task_core_side_effect_dependencies(
        attach_web_task_monitor_func=attach_web_task_monitor,
        monitor_web_task_func=monitor_task_and_release_lock_default,
        record_apply_interaction_func=record_apply_interaction,
    )


def attach_web_task_monitor(
    *,
    backend_task_id: str,
    internal_user_id: int,
    username: str,
    registry_task_id: str,
    submission_context: TaskSubmissionContext,
    cost: int,
    source_post_id: int | None = None,
    monitor_web_task_func: Callable[..., Awaitable[None]],
    create_task_func=None,
):
    del monitor_web_task_func, create_task_func
    from src.services.task_web_finalizer import enqueue_pending_web_finalizer

    return enqueue_pending_web_finalizer(
        backend_task_id=backend_task_id,
        internal_user_id=internal_user_id,
        username=username,
        registry_task_id=registry_task_id,
        submission_context=submission_context,
        cost=cost,
        source_post_id=source_post_id,
    )


def schedule_apply_interaction(
    user_id: int,
    source_post_id: int | None,
    *,
    record_apply_interaction_func,
    create_task_func=None,
):
    if not source_post_id:
        return
    if create_task_func is None:
        create_task_func = asyncio.create_task
    interaction_coro = record_apply_interaction_func(user_id, source_post_id)
    try:
        create_task_func(interaction_coro, name="task-core-apply-interaction")
    except TypeError:
        create_task_func(interaction_coro)


def normalize_submission_side_effect_plan(
    *,
    submission_side_effect_plan: TaskSubmissionSideEffectPlan | None,
    client_type: str | None,
    source_post_id: int | None,
) -> TaskSubmissionSideEffectPlan:
    return normalize_task_submission_side_effect_plan(
        submission_side_effect_plan=submission_side_effect_plan,
        client_type=client_type,
        source_post_id=source_post_id,
    )


async def attach_submission_side_effects(
    *,
    client_type: str | None = None,
    backend_task_id: str,
    internal_user_id: int,
    username: str,
    registry_task_id: str,
    submission_context: TaskSubmissionContext,
    cost: int,
    source_post_id: int | None = None,
    submission_side_effect_plan: TaskSubmissionSideEffectPlan | None = None,
    attach_web_task_monitor_func,
    schedule_apply_interaction_func,
    core_domain_error_cls,
):
    submission_side_effect_plan = normalize_submission_side_effect_plan(
        submission_side_effect_plan=submission_side_effect_plan,
        client_type=client_type,
        source_post_id=source_post_id,
    )
    if submission_side_effect_plan.attach_web_monitor:
        try:
            maybe_awaitable = attach_web_task_monitor_func(
                backend_task_id=backend_task_id,
                internal_user_id=internal_user_id,
                username=username,
                registry_task_id=registry_task_id,
                submission_context=submission_context,
                cost=cost,
                source_post_id=submission_side_effect_plan.source_post_id,
            )
            if inspect.isawaitable(maybe_awaitable):
                await maybe_awaitable
        except Exception as exc:
            raise core_domain_error_cls(f"后台监控挂载失败: {exc}")

    if not submission_side_effect_plan.attach_web_monitor:
        schedule_apply_interaction_func(
            internal_user_id, submission_side_effect_plan.source_post_id
        )


def attach_web_task_monitor_default(
    *,
    backend_task_id: str,
    internal_user_id: int,
    username: str,
    registry_task_id: str,
    submission_context: TaskSubmissionContext,
    cost: int,
    source_post_id: int | None = None,
    monitor_web_task_func=None,
    dependencies=None,
):
    side_effect_dependencies = dependencies or get_default_task_core_side_effect_dependencies()
    if monitor_web_task_func is None:
        monitor_web_task_func = side_effect_dependencies.monitor_web_task_func
    return side_effect_dependencies.attach_web_task_monitor_func(
        backend_task_id=backend_task_id,
        internal_user_id=internal_user_id,
        username=username,
        registry_task_id=registry_task_id,
        submission_context=submission_context,
        cost=cost,
        source_post_id=source_post_id,
        monitor_web_task_func=monitor_web_task_func,
        create_task_func=side_effect_dependencies.create_task_func,
    )


def schedule_apply_interaction_default(
    user_id: int,
    source_post_id: int | None,
    dependencies=None,
):
    dependencies = dependencies or get_default_task_core_side_effect_dependencies()
    schedule_apply_interaction(
        user_id,
        source_post_id,
        record_apply_interaction_func=dependencies.record_apply_interaction_func,
        create_task_func=dependencies.create_task_func,
    )


async def attach_submission_side_effects_default(
    *,
    client_type: str | None = None,
    backend_task_id: str,
    internal_user_id: int,
    username: str,
    registry_task_id: str,
    submission_context: TaskSubmissionContext,
    cost: int,
    source_post_id: int | None = None,
    submission_side_effect_plan: TaskSubmissionSideEffectPlan | None = None,
    attach_web_task_monitor_func=None,
    schedule_apply_interaction_func=None,
    core_domain_error_cls=None,
    dependencies=None,
):
    side_effect_dependencies = dependencies or get_default_task_core_side_effect_dependencies()
    await attach_submission_side_effects(
        client_type=client_type,
        backend_task_id=backend_task_id,
        internal_user_id=internal_user_id,
        username=username,
        registry_task_id=registry_task_id,
        submission_context=submission_context,
        cost=cost,
        source_post_id=source_post_id,
        submission_side_effect_plan=submission_side_effect_plan,
        attach_web_task_monitor_func=(
            attach_web_task_monitor_func
            or (
                lambda **kwargs: attach_web_task_monitor_default(
                    dependencies=side_effect_dependencies,
                    **kwargs,
                )
            )
        ),
        schedule_apply_interaction_func=(
            schedule_apply_interaction_func
            or (
                lambda user_id, source_post_id: schedule_apply_interaction_default(
                    user_id,
                    source_post_id,
                    dependencies=side_effect_dependencies,
                )
            )
        ),
        core_domain_error_cls=core_domain_error_cls or CoreDomainError,
    )
