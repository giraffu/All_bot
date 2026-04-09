import asyncio
import logging
import time
from src.services.redis_client import redis_client
from src.services.permission_service import permission_service
from src.services.task_registry import TaskRegistry
from src.api_client import api_client

logger = logging.getLogger("bot.zombie_cleaner")

async def clean_zombies():
    """
    扫描并清理驻留过长（超过2小时）的僵尸任务。
    1. 识别卡死的任务。
    2. 为用户退还预扣的灵石。
    3. 解除用户的并发锁。
    4. 调用中控 API 彻底取消该任务，防止算力浪费。
    """
    try:
        tasks = await redis_client.get_active_tasks()
        if not tasks:
            logger.debug("No active tasks found during zombie cleanup.")
            return

        now = time.time()
        removed_count = 0

        for task_id, task in tasks.items():
            # 如果没有 created_at 时间戳，为了安全起见假设它刚创建
            created_at = task.get('created_at', now)
            age_seconds = now - created_at

            # 如果任务驻留超过 2 小时 (7200秒)，判定为僵尸任务
            if age_seconds > 7200:
                user_id = task.get("user_id")
                username = task.get("username", "Unknown")
                cost = task.get("cost", 0)
                backend_task_id = task.get("backend_task_id")

                logger.warning(f"🧟 Detected zombie task {task_id} for user {user_id} (age: {age_seconds:.0f}s). Initiating cleanup.")

                # 1. 退还灵石
                if cost > 0 and user_id:
                    try:
                        await permission_service.increment_quota(
                            user_id, 
                            cost=-cost, 
                            username=username, 
                            task_type="refund_zombie_cleanup"
                        )
                        logger.info(f"💰 Refunded {cost} credits to user {user_id} for zombie task {task_id}.")
                    except Exception as e:
                        logger.error(f"Error refunding during zombie cleanup for user {user_id}: {e}")

                # 2. 解除用户并发锁
                if user_id:
                    try:
                        await redis_client.decrement_user_concurrency(user_id)
                        logger.info(f"🔓 Decremented concurrency lock for user {user_id}.")
                    except Exception as e:
                        logger.error(f"Error decrementing concurrency for user {user_id}: {e}")

                # 3. 从 Bot 侧的任务注册表中移除
                try:
                    await TaskRegistry.remove_task(task_id)
                except Exception as e:
                    logger.error(f"Error removing task {task_id} from registry: {e}")

                # 4. 通知中控 API 取消任务（双向剔除）
                if backend_task_id:
                    try:
                        # 假设中控 API 有一个取消任务的 DELETE 接口
                        # 从之前的分析中得知路径为 /api/tasks/{task_id}
                        await api_client.cancel_task(backend_task_id)
                        logger.info(f"🛑 Sent cancellation request to Central API for backend task {backend_task_id}.")
                    except Exception as e:
                        logger.error(f"Error cancelling backend task {backend_task_id} at Central API: {e}")

                removed_count += 1

        if removed_count > 0:
            logger.info(f"🧹 Zombie cleanup complete. Removed {removed_count} zombie tasks.")

    except Exception as e:
        logger.error(f"Error during zombie task cleanup loop: {e}", exc_info=True)

async def main():
    """
    独立的入口函数，如果需要手动运行此脚本时调用。
    """
    logging.basicConfig(level=logging.INFO)
    logger.info("Starting manual zombie cleanup...")
    await clean_zombies()
    logger.info("Manual zombie cleanup finished.")

if __name__ == "__main__":
    asyncio.run(main())
