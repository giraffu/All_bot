import asyncio
import logging
import time
import json
from src.services.redis_client import redis_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def clear_ghost_tasks():
    """
    Clears leaked tasks from the active_tasks registry without refunding credits
    or releasing concurrency locks, specifically for tasks that have already finished
    but were leaked due to the missing TaskRegistry.remove_task() bug.
    """
    try:
        # Get all tasks from the registry
        active_tasks = await redis_client.get_active_tasks()
        
        if not active_tasks:
            logger.info("No active tasks found in registry.")
            return

        current_time = time.time()
        leaked_tasks_count = 0
        
        # We consider tasks older than 30 minutes as "ghosts" for this one-time cleanup
        # You can adjust this threshold if needed
        THRESHOLD_SECONDS = 30 * 60 

        for registry_task_id, task_data in active_tasks.items():
            created_at = task_data.get("created_at", 0)
            
            # If the task is older than the threshold, it's a ghost
            if current_time - created_at > THRESHOLD_SECONDS:
                # Silently remove from registry without any refund logic
                await redis_client.remove_active_task(registry_task_id)
                leaked_tasks_count += 1
                logger.info(f"Removed ghost task: {registry_task_id} (User: {task_data.get('username')})")

        logger.info(f"Successfully cleared {leaked_tasks_count} ghost tasks without refunding credits.")
        
    except Exception as e:
        logger.error(f"Error during ghost task cleanup: {e}")

if __name__ == "__main__":
    asyncio.run(clear_ghost_tasks())
