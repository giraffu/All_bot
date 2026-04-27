import asyncio
import logging
import time
import sys
import os

# 确保能找到 src 包
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.services.redis_client import redis_client
from src.services.permission_service import permission_service
from src.services.task_registry import TaskRegistry
from config import REDIS_PREFIX

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fix_locks")

async def reset_user_concurrency(user_id: int):
    """强制重置用户的并发锁为 0"""
    key = f"{REDIS_PREFIX}user_concurrency:{user_id}"
    try:
        await redis_client.redis.set(key, 0)
        logger.info(f"✅ 已强制重置用户 {user_id} 的并发锁为 0。")
    except Exception as e:
        logger.error(f"❌ 重置用户 {user_id} 并发锁失败: {e}")

async def clean_stuck_tasks_and_reset_locks(timeout_seconds=300):
    """
    清理超时（默认 5 分钟）的任务，退还灵石，并重置这些用户的并发锁。
    """
    try:
        tasks = await redis_client.get_active_tasks()
        if not tasks:
            logger.info("没有找到活跃的排队/生成中任务。")
            return

        now = time.time()
        removed_count = 0
        affected_users = set()

        for task_id, task in tasks.items():
            created_at = task.get('created_at', now)
            age_seconds = now - created_at

            # 如果任务驻留超过 timeout_seconds (默认 300秒)
            if age_seconds > timeout_seconds:
                user_id = task.get("user_id")
                username = task.get("username", "Unknown")
                cost = task.get("cost", 0)

                logger.warning(f"🧟 发现卡死的任务 {task_id} (用户: {user_id}, 已卡住: {age_seconds:.0f}秒)")

                # 1. 退还灵石
                if cost > 0 and user_id:
                    try:
                        await permission_service.increment_quota(
                            user_id, 
                            cost=-cost, 
                            username=username, 
                            task_type="refund_admin_force_script"
                        )
                        logger.info(f"💰 已为用户 {user_id} 退还 {cost} 灵石。")
                    except Exception as e:
                        logger.error(f"退还用户 {user_id} 灵石失败: {e}")

                # 2. 从 Bot 的活跃任务和注册表中移除
                try:
                    await redis_client.remove_active_task(task_id)
                    await TaskRegistry.remove_task(task_id)
                    logger.info(f"🗑️ 已移除卡死任务 {task_id}")
                except Exception as e:
                    logger.error(f"移除任务 {task_id} 失败: {e}")

                if user_id:
                    affected_users.add(user_id)
                removed_count += 1

        # 3. 强制重置所有受影响用户的并发锁
        for user_id in affected_users:
            await reset_user_concurrency(user_id)

        logger.info(f"🎉 清理完成！共移除了 {removed_count} 个卡死任务，并重置了 {len(affected_users)} 个用户的并发锁。")

    except Exception as e:
        logger.error(f"执行脚本时出错: {e}", exc_info=True)
    finally:
        await redis_client.close()

if __name__ == "__main__":
    # 如果想直接清理所有任务（不看时间），可以把 timeout_seconds 设为 0
    # 或者如果你只想要清理卡了超过 5 分钟的，就保持 300
    timeout_str = input("请输入要清理卡死任务的超时时间（秒，默认 300，直接按回车即可）：")
    timeout = 300 if not timeout_str.strip() else int(timeout_str.strip())
    
    asyncio.run(clean_stuck_tasks_and_reset_locks(timeout))
