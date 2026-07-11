import logging

import httpx

from src.core.billing_core import release_concurrency_lock
from src.core.task_core_default_dependencies import (
    build_default_task_core_runtime_dependencies,
)
from src.core.task_core_types import CoreDomainError

logger = logging.getLogger(__name__)


async def cleanup_task_runtime_state(
    *,
    internal_user_id: int,
    registry_task_id: str | None,
    release_lock: bool = True,
    release_concurrency_lock_func=None,
    remove_task_func=None,
    runtime_dependencies=None,
):
    if release_concurrency_lock_func is None or remove_task_func is None:
        runtime_dependencies = runtime_dependencies or build_default_task_core_runtime_dependencies(
            release_concurrency_lock_func=release_concurrency_lock
        )
        if release_concurrency_lock_func is None:
            release_concurrency_lock_func = (
                runtime_dependencies.release_concurrency_lock_func
            )
        if remove_task_func is None:
            remove_task_func = runtime_dependencies.remove_task_func

    if release_lock:
        try:
            await release_concurrency_lock_func(internal_user_id)
        except Exception as e:
            logger.error(
                f"Failed to release concurrency lock for {internal_user_id}: {e}"
            )

    if registry_task_id:
        try:
            await remove_task_func(registry_task_id)
        except Exception as e:
            logger.error(f"Failed to remove registry task {registry_task_id}: {e}")


async def get_system_task_stats(
    *,
    submission_outbox=None,
    runtime_dependencies=None,
) -> tuple[dict, dict]:
    """
    获取全系统任务统计信息。
    返回 (active_tasks, user_concurrencies)
    """
    if submission_outbox is not None:
        active_tasks = await submission_outbox.get_active_tasks()
        user_concurrencies = await submission_outbox.get_all_user_concurrencies()
        return active_tasks, user_concurrencies

    runtime_dependencies = runtime_dependencies or build_default_task_core_runtime_dependencies(
        release_concurrency_lock_func=release_concurrency_lock
    )
    active_tasks = await runtime_dependencies.get_active_tasks_func()
    user_concurrencies = await runtime_dependencies.get_all_user_concurrencies_func()
    return active_tasks, user_concurrencies


async def cancel_backend_task_best_effort(
    *,
    backend_task_id: str | None,
    registry_task_id: str,
    raise_on_error: bool = False,
    cancel_task_func=None,
    logger_override=logger,
    runtime_dependencies=None,
) -> bool:
    """Best-effort backend cancellation shared by runtime cleanup call sites."""
    if not backend_task_id:
        return False

    if cancel_task_func is None:
        runtime_dependencies = runtime_dependencies or build_default_task_core_runtime_dependencies(
            release_concurrency_lock_func=release_concurrency_lock
        )
        cancel_task_func = runtime_dependencies.cancel_task_func

    try:
        await cancel_task_func(backend_task_id)
        return True
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            logger_override.info(
                "Backend task %s already missing during cleanup of %s.",
                backend_task_id,
                registry_task_id,
            )
            return False

        logger_override.exception(
            "Failed to cancel backend task %s for registry task %s.",
            backend_task_id,
            registry_task_id,
        )
        if raise_on_error:
            raise
        return False
    except Exception:
        logger_override.exception(
            "Failed to cancel backend task %s for registry task %s.",
            backend_task_id,
            registry_task_id,
        )
        if raise_on_error:
            raise
        return False


async def force_terminate_task(
    task_id: str,
    user_id: int | None = None,
    submission_outbox=None,
    cleanup_task_runtime_state_func=None,
    cancel_backend_task_best_effort_func=None,
    runtime_dependencies=None,
):
    """
    强制终止一个活跃任务并释放对应的用户锁。

    这里的 ``task_id`` 是 Bot 侧注册表中的任务 ID；真正提交给中控的
    任务 ID 可能保存在 ``backend_task_id`` 中，因此终止时需要双向剔除。
    """
    if cleanup_task_runtime_state_func is None:
        cleanup_task_runtime_state_func = cleanup_task_runtime_state
    if cancel_backend_task_best_effort_func is None:
        cancel_backend_task_best_effort_func = cancel_backend_task_best_effort

    if submission_outbox is not None:
        tasks = await submission_outbox.get_active_tasks()
    else:
        runtime_dependencies = runtime_dependencies or build_default_task_core_runtime_dependencies(
            release_concurrency_lock_func=release_concurrency_lock
        )
        tasks = await runtime_dependencies.get_active_tasks_func()
    task_data = tasks.get(task_id, {}) if tasks else {}
    backend_task_id = task_data.get("backend_task_id")

    if not user_id:
        user_id = task_data.get("user_id")

    if backend_task_id:
        await cancel_backend_task_best_effort_func(
            backend_task_id=backend_task_id,
            registry_task_id=task_id,
            raise_on_error=True,
        )

    await cleanup_task_runtime_state_func(
        internal_user_id=user_id or 0,
        registry_task_id=task_id,
        release_lock=user_id is not None,
    )


async def sync_user_concurrency(
    user_id: int,
    actual_count: int,
    *,
    submission_outbox=None,
    runtime_dependencies=None,
):
    """
    同步用户并发锁到指定数量，当 actual_count 为 0 时删除锁
    """
    from config import REDIS_PREFIX

    key = f"{REDIS_PREFIX}user_concurrency:{user_id}"

    if submission_outbox is not None:
        redis_client = submission_outbox
        if actual_count > 0:
            await redis_client.redis.set(key, actual_count)
            await redis_client.redis.expire(key, 3600)
        else:
            await redis_client.redis.delete(key)
        return

    runtime_dependencies = runtime_dependencies or build_default_task_core_runtime_dependencies(
        release_concurrency_lock_func=release_concurrency_lock
    )
    if actual_count > 0:
        await runtime_dependencies.set_runtime_value_func(key, actual_count)
        await runtime_dependencies.expire_runtime_value_func(key, 3600)
    else:
        await runtime_dependencies.delete_runtime_value_func(key)


async def cancel_user_task(
    task_id: str,
    user_id: int,
    *,
    task_registry=None,
    cancel_task_func=None,
    finalize_task_cancellation_func=None,
    runtime_dependencies=None,
):
    """供用户主动调用的任务撤销逻辑"""
    runtime_dependencies = runtime_dependencies or build_default_task_core_runtime_dependencies(
        release_concurrency_lock_func=release_concurrency_lock
    )
    if task_registry is None:
        task = await runtime_dependencies.get_task_func(task_id)
    else:
        task = await task_registry.get_task(task_id)
    registry_task_id = task_id
    if not task:
        if task_registry is None:
            registry_task_id, task = await runtime_dependencies.find_task_by_backend_task_id_func(
                task_id
            )
        else:
            registry_task_id, task = await task_registry.find_task_by_backend_task_id(
                task_id
            )

    if not task or not registry_task_id:
        raise CoreDomainError("任务不存在或已脱离排队阶段")

    if task.get("user_id") != user_id:
        raise CoreDomainError("无权撤销该任务")

    if task.get("user_cancel_allowed") is False:
        return {
            "state": "not_cancellable",
            "task_id": registry_task_id,
            "message": "任务已进入连续生成阶段，无法再取消",
            "reason": "user_cancel_locked",
        }

    backend_task_id = task.get("backend_task_id") or registry_task_id
    try:
        cancel_task_func = cancel_task_func or runtime_dependencies.cancel_task_func
        cancel_result = await cancel_task_func(backend_task_id)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise CoreDomainError("任务不存在或已结束，当前无法取消")
        raise CoreDomainError(f"撤销请求失败: HTTP {e.response.status_code}")
    except Exception as e:
        logger.error(f"中控取消任务网络异常: {e}")
        raise CoreDomainError("撤销请求失败，请稍后重试")

    if isinstance(cancel_result, dict) and cancel_result.get("state") == "cancelled":
        if finalize_task_cancellation_func is None:
            from src.core.task_core_finalization import (
                finalize_task_cancellation_default,
            )

            finalize_task_cancellation_func = finalize_task_cancellation_default

        try:
            cost = int(task.get("cost") or 0)
        except (TypeError, ValueError):
            cost = 0

        finalization_result = await finalize_task_cancellation_func(
            internal_user_id=user_id,
            username=task.get("username") or "",
            cost=cost,
            task_submitted=bool(task.get("credits_deducted", True)),
            registry_task_id=registry_task_id,
            release_lock=True,
        )
        if getattr(finalization_result, "user_message", None):
            cancel_result = {
                **cancel_result,
                "message": finalization_result.user_message,
            }
        if hasattr(finalization_result, "refunded"):
            cancel_result = {
                **cancel_result,
                "refunded": finalization_result.refunded,
            }
    return cancel_result
