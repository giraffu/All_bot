import asyncio
from src.core.billing_core import release_concurrency_lock
from src.services.task_registry import TaskRegistry
from src.services.image_service import image_service
from src.logger import get_logger

logger = get_logger(__name__)

async def monitor_and_cleanup(task_id: str, internal_user_id: int, registry_task_id: str, is_video: bool = False):
    try:
        async for progress in image_service.monitor_progress(task_id, is_video):
            if progress.get("status") in ["done", "error", "cancelled"]:
                break
    except Exception as e:
        logger.error(f"Error monitoring task {task_id}: {e}")
    finally:
        await release_concurrency_lock(internal_user_id)
        if registry_task_id:
            await TaskRegistry.remove_task(registry_task_id)
