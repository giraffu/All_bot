import asyncio
import logging
import time
from src.services.redis_client import redis_client
from src.services.permission_service import permission_service
from src.services.task_registry import TaskRegistry
from src.api_client import api_client

logger = logging.getLogger("bot.clean_all")

async def clean_all():
    try:
        tasks = await redis_client.get_active_tasks()
        if not tasks:
            logger.info("No active tasks found.")
            return

        removed_count = 0

        for task_id, task in tasks.items():
            user_id = task.get("user_id")
            username = task.get("username", "Unknown")
            cost = task.get("cost", 0)
            backend_task_id = task.get("backend_task_id")

            logger.info(f"🧹 Cleaning task {task_id} for user {user_id}.")

            if cost > 0 and user_id:
                try:
                    await permission_service.increment_quota(
                        user_id, 
                        cost=-cost, 
                        username=username, 
                        task_type="refund_zombie_cleanup"
                    )
                    logger.info(f"💰 Refunded {cost} credits to user {user_id} for task {task_id}.")
                except Exception as e:
                    logger.error(f"Error refunding for user {user_id}: {e}")

            if user_id:
                try:
                    await redis_client.decrement_user_concurrency(user_id)
                    logger.info(f"🔓 Decremented concurrency lock for user {user_id}.")
                except Exception as e:
                    logger.error(f"Error decrementing concurrency for user {user_id}: {e}")

            try:
                await TaskRegistry.remove_task(task_id)
            except Exception as e:
                logger.error(f"Error removing task {task_id} from registry: {e}")

            if backend_task_id:
                try:
                    await api_client.cancel_task(backend_task_id)
                    logger.info(f"🛑 Sent cancellation request to Central API for backend task {backend_task_id}.")
                except Exception as e:
                    logger.error(f"Error cancelling backend task {backend_task_id} at Central API: {e}")

            removed_count += 1

        if removed_count > 0:
            logger.info(f"✅ Cleanup complete. Removed {removed_count} tasks.")

    except Exception as e:
        logger.error(f"Error during task cleanup: {e}", exc_info=True)

async def main():
    logging.basicConfig(level=logging.INFO)
    logger.info("Starting task cleanup...")
    await clean_all()
    logger.info("Task cleanup finished.")

if __name__ == "__main__":
    asyncio.run(main())
