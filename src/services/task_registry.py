import logging
import time

from src.services.redis_client import redis_client

logger = logging.getLogger(__name__)


class TaskRegistry:
    @classmethod
    async def add_task(
        cls,
        task_id: str,
        user_id: int,
        username: str,
        cost: int,
        task_type: str,
        chat_id: int = None,
        message_id: int = None,
        **kwargs,
    ) -> str:
        task_data = {
            "user_id": user_id,
            "username": username,
            "cost": cost,
            "task_type": task_type,
            "chat_id": chat_id,
            "message_id": message_id,
            "backend_task_id": None,  # Will be updated once submitted
            "created_at": time.time(),  # Added to track queue duration
            **kwargs,
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
    async def mark_task_status(cls, registry_task_id: str, status: str):
        tasks = await redis_client.get_active_tasks()
        if registry_task_id in tasks:
            task_data = tasks[registry_task_id]
            task_data["status"] = status
            await redis_client.add_active_task(registry_task_id, task_data)

    @classmethod
    async def get_task(cls, registry_task_id: str):
        tasks = await redis_client.get_active_tasks()
        return tasks.get(registry_task_id)

    @classmethod
    async def find_task_by_backend_task_id(cls, backend_task_id: str):
        tasks = await redis_client.get_active_tasks()
        for registry_task_id, task_data in tasks.items():
            if task_data.get("backend_task_id") == backend_task_id:
                return registry_task_id, task_data
        return None, None

    @classmethod
    async def remove_task(cls, task_id: str):
        await redis_client.remove_active_task(task_id)

    @classmethod
    async def get_all_tasks(cls):
        return await redis_client.get_active_tasks()

    @classmethod
    async def log_restart_recovery_policy(cls, bot=None):
        """Record startup recovery behavior without mutating running tasks."""
        _ = bot
        logger.info(
            "Task registry startup recovery check: tasks are persisted in Redis. "
            "Skipping bulk refund to allow tasks to continue on restart."
        )
