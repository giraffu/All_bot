import argparse
import asyncio
import logging
import os
import sys
import time

# 确保能找到 src 包
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.task_core import get_system_task_stats, sync_user_concurrency
from src.core.task_core_finalization import finalize_terminated_task
from src.services.redis_client import redis_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fix_locks")
DEFAULT_TIMEOUT_SECONDS = 7200


async def clean_stuck_tasks_and_reset_locks(timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS):
    """
    清理超时任务，统一走 core helper 做终止、退款和运行态清理。
    之后按用户真实活跃任务数对齐并发锁，避免遗留历史脏锁。
    """
    try:
        tasks, _ = await get_system_task_stats()
        if not tasks:
            logger.info("没有找到活跃的排队/生成中任务。")
            return

        now = time.time()
        removed_count = 0
        affected_users = set()

        for task_id, task in tasks.items():
            created_at = task.get("created_at", now)
            age_seconds = now - created_at

            # 如果任务驻留超过 timeout_seconds (默认 300秒)
            if age_seconds > timeout_seconds:
                user_id = task.get("user_id")
                username = task.get("username", "Unknown")
                cost = task.get("cost", 0)

                logger.warning(
                    f"🧟 发现卡死的任务 {task_id} (用户: {user_id}, 已卡住: {age_seconds:.0f}秒)"
                )

                try:
                    result = await finalize_terminated_task(
                        registry_task_id=task_id,
                        user_id=user_id,
                        username=username,
                        cost=cost,
                        should_refund=cost > 0,
                        refund_task_type="refund_admin_force_script",
                    )
                    if result.refunded:
                        logger.info(f"💰 已为用户 {user_id} 退还 {cost} 灵石。")
                    logger.info(f"🗑️ 已统一收口卡死任务 {task_id}")
                except Exception as e:
                    logger.error(f"收口卡死任务 {task_id} 失败: {e}")
                    continue

                if user_id:
                    affected_users.add(user_id)
                removed_count += 1

        refreshed_tasks, _ = await get_system_task_stats()
        for user_id in affected_users:
            actual_count = sum(
                1 for task in refreshed_tasks.values() if task.get("user_id") == user_id
            )
            await sync_user_concurrency(user_id, actual_count)
            logger.info(f"✅ 已将用户 {user_id} 的并发锁对齐为 {actual_count}。")

        logger.info(
            f"🎉 清理完成！共收口了 {removed_count} 个卡死任务，并同步了 {len(affected_users)} 个用户的并发锁。"
        )

    except Exception as e:
        logger.error(f"执行脚本时出错: {e}", exc_info=True)
    finally:
        await redis_client.close()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="统一收口超时任务，复用 task_core 的终止/退款/清理 helper。"
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"判定为卡死任务的超时阈值，默认 {DEFAULT_TIMEOUT_SECONDS} 秒。",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(clean_stuck_tasks_and_reset_locks(args.timeout_seconds))
