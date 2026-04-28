import logging

from src.services.redis_client import redis_client

logger = logging.getLogger(__name__)

import time


class TaskRegistry:
    @classmethod
    async def add_task(cls, task_id: str, user_id: int, username: str, cost: int, task_type: str, chat_id: int = None, message_id: int = None, **kwargs) -> str:
        task_data = {
            "user_id": user_id,
            "username": username,
            "cost": cost,
            "task_type": task_type,
            "chat_id": chat_id,
            "message_id": message_id,
            "backend_task_id": None,  # Will be updated once submitted
            "created_at": time.time(), # Added to track queue duration
            **kwargs
        }
        await redis_client.add_active_task(task_id, task_data)
        return task_id

    @classmethod
    async def update_backend_task_id(cls, registry_task_id: str, backend_task_id: str):
        tasks = await redis_client.get_active_tasks()
        if registry_task_id in tasks:
            task_data = tasks[registry_task_id]
            task_data["backend_task_id"] = backend_task_id
            await redis_client.add_active_task(registry_task_id, task_data)

    @classmethod
    async def remove_task(cls, task_id: str):
        await redis_client.remove_active_task(task_id)

    @classmethod
    async def get_all_tasks(cls):
        return await redis_client.get_active_tasks()

    @classmethod
    async def refund_all(cls, bot=None):
        """
        退款逻辑。在新的架构下，如果 bot 重启，我们不再强制执行退款，
        因为任务可能还在 AI 后端运行。
        这个函数可以被保留作为紧急维护时的手动调用，或者彻底改变其行为。
        目前可以只打印日志，或者在恢复机制中如果发现任务丢失再单独调用退款。
        """
        logger.info("refund_all is called, but tasks are now persisted in Redis. "
                    "Skipping bulk refund to allow tasks to continue on restart.")
        # 如果需要实现完全的清理退款，可以读取 get_all_tasks() 并处理。
