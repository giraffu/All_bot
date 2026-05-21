import logging

import httpx

from src.core.task_core_types import CoreDomainError
from src.services.task_registry import TaskRegistry

logger = logging.getLogger(__name__)


async def cleanup_task_runtime_state(
    *,
    internal_user_id: int,
    registry_task_id: str | None,
    release_lock: bool = True,
):
    from src.core import task_core as compat_task_core

    if release_lock:
        try:
            await compat_task_core.release_concurrency_lock(internal_user_id)
        except Exception as e:
            logger.error(
                f"Failed to release concurrency lock for {internal_user_id}: {e}"
            )

    if registry_task_id:
        try:
            await TaskRegistry.remove_task(registry_task_id)
        except Exception as e:
            logger.error(f"Failed to remove registry task {registry_task_id}: {e}")


async def get_system_task_stats() -> tuple[dict, dict]:
    """
    获取全系统任务统计信息。
    返回 (active_tasks, user_concurrencies)
    """
    from src.services.redis_client import redis_client

    active_tasks = await redis_client.get_active_tasks()
    user_concurrencies = await redis_client.get_all_user_concurrencies()
    return active_tasks, user_concurrencies


async def force_terminate_task(task_id: str, user_id: int | None = None):
    """
    强制终止一个活跃任务并释放对应的用户锁。

    这里的 ``task_id`` 是 Bot 侧注册表中的任务 ID；真正提交给中控的
    任务 ID 可能保存在 ``backend_task_id`` 中，因此终止时需要双向剔除。
    """
    from src.api_client import api_client
    from src.services.redis_client import redis_client

    tasks = await redis_client.get_active_tasks()
    task_data = tasks.get(task_id, {}) if tasks else {}
    backend_task_id = task_data.get("backend_task_id")

    if not user_id:
        user_id = task_data.get("user_id")

    if backend_task_id:
        try:
            await api_client.cancel_task(backend_task_id)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise
            logger.info(
                "Backend task %s already missing during force terminate of %s.",
                backend_task_id,
                task_id,
            )
        except Exception:
            logger.exception(
                "Failed to cancel backend task %s for registry task %s.",
                backend_task_id,
                task_id,
            )
            raise

    from src.core import task_core as compat_task_core

    await compat_task_core.cleanup_task_runtime_state(
        internal_user_id=user_id or 0,
        registry_task_id=task_id,
        release_lock=user_id is not None,
    )


async def sync_user_concurrency(user_id: int, actual_count: int):
    """
    同步用户并发锁到指定数量，当 actual_count 为 0 时删除锁
    """
    from config import REDIS_PREFIX
    from src.services.redis_client import redis_client

    key = f"{REDIS_PREFIX}user_concurrency:{user_id}"

    if actual_count > 0:
        await redis_client.redis.set(key, actual_count)
        await redis_client.redis.expire(key, 3600)
    else:
        await redis_client.redis.delete(key)


async def cancel_user_task(task_id: str, user_id: int):
    """供用户主动调用的任务撤销逻辑"""
    task = await TaskRegistry.get_task(task_id)
    registry_task_id = task_id
    if not task:
        registry_task_id, task = await TaskRegistry.find_task_by_backend_task_id(task_id)

    if not task or not registry_task_id:
        raise CoreDomainError("任务不存在或已脱离排队阶段")

    if task.get("user_id") != user_id:
        raise CoreDomainError("无权撤销该任务")

    from src.api_client import api_client

    backend_task_id = task.get("backend_task_id") or registry_task_id
    try:
        cancel_result = await api_client.cancel_task(backend_task_id)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise CoreDomainError("任务不存在或已结束，当前无法取消")
        raise CoreDomainError(f"撤销请求失败: HTTP {e.response.status_code}")
    except Exception as e:
        logger.error(f"中控取消任务网络异常: {e}")
        raise CoreDomainError("撤销请求失败，请稍后重试")
    return cancel_result
