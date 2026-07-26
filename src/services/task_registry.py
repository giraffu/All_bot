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
        await redis_client.add_active_task_strict(task_id, task_data)
        return task_id

    @classmethod
    async def update_backend_task_id(cls, registry_task_id: str, backend_task_id: str):
        tasks = await redis_client.get_active_tasks_strict()
        if registry_task_id not in tasks:
            raise LookupError("Task registry entry disappeared before backend binding")
        task_data = tasks[registry_task_id]
        task_data["backend_task_id"] = backend_task_id
        await redis_client.add_active_task_strict(registry_task_id, task_data)

    @classmethod
    async def mark_task_status(cls, registry_task_id: str, status: str):
        tasks = await redis_client.get_active_tasks_strict()
        if registry_task_id in tasks:
            task_data = tasks[registry_task_id]
            task_data["status"] = status
            await redis_client.add_active_task_strict(registry_task_id, task_data)

    @classmethod
    async def transition_backend_task(
        cls,
        registry_task_id: str,
        *,
        backend_task_id: str,
        task_type: str,
        saved_input_images: list[str],
        allow_contribute: bool,
        user_cancel_allowed: bool,
        status: str,
        task_updates: dict | None = None,
    ) -> None:
        """Persist a logical task's move to a non-cancellable backend stage."""
        tasks = await redis_client.get_active_tasks_strict()
        if registry_task_id not in tasks:
            raise LookupError("Task registry entry disappeared before stage transition")
        task_data = tasks[registry_task_id]
        task_data.update(
            {
                "backend_task_id": backend_task_id,
                "task_type": task_type,
                "saved_input_images": list(saved_input_images),
                "allow_contribute": bool(allow_contribute),
                "user_cancel_allowed": bool(user_cancel_allowed),
                "status": status,
            }
        )
        if task_updates:
            allowed_updates = {
                "is_video",
                "prompt",
                "billing_resolution",
                "requested_duration",
                "metadata",
            }
            task_data.update(
                {
                    key: value
                    for key, value in task_updates.items()
                    if key in allowed_updates
                }
            )
        metadata = task_data.get("metadata")
        if isinstance(metadata, dict):
            metadata = dict(metadata)
            metadata.pop("_web_free_edit_v3", None)
            task_data["metadata"] = metadata
        await redis_client.add_active_task_strict(registry_task_id, task_data)

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
        await redis_client.remove_active_task_strict(task_id)

    @classmethod
    async def get_all_tasks(cls):
        return await redis_client.get_active_tasks()

    @classmethod
    async def get_task_strict(cls, registry_task_id: str):
        tasks = await redis_client.get_active_tasks_strict()
        return tasks.get(registry_task_id)

    @classmethod
    async def get_all_tasks_strict(cls):
        return await redis_client.get_active_tasks_strict()

    @classmethod
    async def log_restart_recovery_policy(cls, bot=None):
        """Record startup recovery behavior without mutating running tasks."""
        _ = bot
        logger.info(
            "Task registry startup recovery check: tasks are persisted in Redis. "
            "Skipping bulk refund to allow tasks to continue on restart."
        )
