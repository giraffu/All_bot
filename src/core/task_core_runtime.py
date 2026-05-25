import logging

import httpx

from src.core.billing_core import release_concurrency_lock
from src.core.task_core_service_providers import (
    get_task_core_api_client,
    get_task_core_submission_outbox,
    get_task_core_task_registry,
)
from src.core.task_core_types import CoreDomainError
from src.task_core_provider_setup import ensure_task_core_service_providers_registered

logger = logging.getLogger(__name__)

ensure_task_core_service_providers_registered()


async def cleanup_task_runtime_state(
    *,
    internal_user_id: int,
    registry_task_id: str | None,
    release_lock: bool = True,
    release_concurrency_lock_func=None,
    remove_task_func=None,
):
    if release_concurrency_lock_func is None:
        release_concurrency_lock_func = release_concurrency_lock
    if remove_task_func is None:
        remove_task_func = get_task_core_task_registry().remove_task

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


async def get_system_task_stats(*, submission_outbox=None) -> tuple[dict, dict]:
    """
    获取全系统任务统计信息。
    返回 (active_tasks, user_concurrencies)
    """
    redis_client = submission_outbox or get_task_core_submission_outbox()
    active_tasks = await redis_client.get_active_tasks()
    user_concurrencies = await redis_client.get_all_user_concurrencies()
    return active_tasks, user_concurrencies


async def cancel_backend_task_best_effort(
    *,
    backend_task_id: str | None,
    registry_task_id: str,
    raise_on_error: bool = False,
    cancel_task_func=None,
    logger_override=logger,
) -> bool:
    """Best-effort backend cancellation shared by runtime cleanup call sites."""
    if not backend_task_id:
        return False

    if cancel_task_func is None:
        cancel_task_func = get_task_core_api_client().cancel_task

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

    redis_client = submission_outbox or get_task_core_submission_outbox()
    tasks = await redis_client.get_active_tasks()
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
):
    """
    同步用户并发锁到指定数量，当 actual_count 为 0 时删除锁
    """
    from config import REDIS_PREFIX

    redis_client = submission_outbox or get_task_core_submission_outbox()
    key = f"{REDIS_PREFIX}user_concurrency:{user_id}"

    if actual_count > 0:
        await redis_client.redis.set(key, actual_count)
        await redis_client.redis.expire(key, 3600)
    else:
        await redis_client.redis.delete(key)


async def cancel_user_task(
    task_id: str,
    user_id: int,
    *,
    task_registry=None,
    cancel_task_func=None,
):
    """供用户主动调用的任务撤销逻辑"""
    task_registry = task_registry or get_task_core_task_registry()
    task = await task_registry.get_task(task_id)
    registry_task_id = task_id
    if not task:
        registry_task_id, task = await task_registry.find_task_by_backend_task_id(task_id)

    if not task or not registry_task_id:
        raise CoreDomainError("任务不存在或已脱离排队阶段")

    if task.get("user_id") != user_id:
        raise CoreDomainError("无权撤销该任务")

    backend_task_id = task.get("backend_task_id") or registry_task_id
    try:
        cancel_task_func = cancel_task_func or get_task_core_api_client().cancel_task
        cancel_result = await cancel_task_func(backend_task_id)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise CoreDomainError("任务不存在或已结束，当前无法取消")
        raise CoreDomainError(f"撤销请求失败: HTTP {e.response.status_code}")
    except Exception as e:
        logger.error(f"中控取消任务网络异常: {e}")
        raise CoreDomainError("撤销请求失败，请稍后重试")
    return cancel_result
