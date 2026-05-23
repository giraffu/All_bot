import asyncio
import logging
import time

from src.core.task_core import sync_user_concurrency
from src.core.task_core_runtime import cancel_backend_task_best_effort
from src.services.redis_client import redis_client
from src.services.task_failure_finalization_service import (
    finalize_zombie_cleanup_for_task_record,
)

logger = logging.getLogger("bot.zombie_cleaner")


async def clean_zombies(bot=None):
    """
    扫描并清理驻留过长（超过2小时）的僵尸任务。
    1. 识别卡死的任务。
    2. 为用户退还预扣的灵石。
    3. 解除用户的并发锁。
    4. 调用中控 API 彻底取消该任务，防止算力浪费。
    5. (可选) 通知用户已退款。
    """
    try:
        tasks = await redis_client.get_active_tasks()
        if not tasks:
            logger.debug("No active tasks found during zombie cleanup.")
            tasks = {}

        now = time.time()
        removed_count = 0

        for task_id, task in tasks.items():
            # 如果没有 created_at 时间戳，为了安全起见假设它刚创建
            created_at = task.get("created_at", now)
            age_seconds = now - created_at

            # 如果任务驻留超过 2 小时 (7200秒)，判定为僵尸任务
            if age_seconds > 7200:
                user_id = task.get("user_id")
                cost = task.get("cost", 0)
                backend_task_id = task.get("backend_task_id")

                logger.warning(
                    f"🧟 Detected zombie task {task_id} for user {user_id} (age: {age_seconds:.0f}s). Initiating cleanup."
                )

                # 1. 统一执行退款 + 运行态清理
                if user_id:
                    try:
                        result, cancelled = await finalize_zombie_cleanup_for_task_record(
                            registry_task_id=task_id,
                            task_data=task,
                            bot=bot,
                            logger_override=logger,
                        )
                        if result.refunded:
                            logger.info(
                                f"💰 Refunded {cost} credits to user {user_id} for zombie task {task_id}."
                            )
                        logger.info(
                            f"🔓 Cleaned runtime state for zombie task {task_id} user {user_id}."
                        )
                        if cancelled:
                            logger.info(
                                f"🛑 Sent cancellation request to Central API for backend task {backend_task_id}."
                            )
                    except Exception as e:
                        logger.error(
                            f"Error finalizing zombie task {task_id} for user {user_id}: {e}"
                        )
                elif backend_task_id:
                    logger.warning(
                        "Zombie task %s has no user_id; skipping refund finalization and only cancelling backend task.",
                        task_id,
                    )
                    cancelled = await cancel_backend_task_best_effort(
                        backend_task_id=backend_task_id,
                        registry_task_id=task_id,
                        logger_override=logger,
                    )
                    if cancelled:
                        logger.info(
                            f"🛑 Sent cancellation request to Central API for backend task {backend_task_id}."
                        )

                removed_count += 1

        if removed_count > 0:
            logger.info(
                f"🧹 Zombie cleanup complete. Removed {removed_count} zombie tasks."
            )

        # 6. 检查并非因为僵尸任务而是由于死锁导致并发数 > 0 但没有活跃任务的用户
        try:
            concurrencies = await redis_client.get_all_user_concurrencies()
            active_user_tasks = {}
            for task_id, task in tasks.items():
                uid = task.get("user_id")
                if uid:
                    active_user_tasks[uid] = active_user_tasks.get(uid, 0) + 1

            for uid, lock_count in concurrencies.items():
                if lock_count > 0 and active_user_tasks.get(uid, 0) == 0:
                    logger.warning(
                        f"🔓 Detected leaked concurrency lock for user {uid} (lock_count={lock_count}, active_tasks=0). Resetting..."
                    )
                    await sync_user_concurrency(uid, 0)
                    logger.info(f"✅ Reset concurrency lock for user {uid}.")
        except Exception as e:
            logger.error(f"Error fixing leaked concurrency locks: {e}")

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
