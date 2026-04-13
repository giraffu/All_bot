from typing import Tuple
import logging

from src.database.core import AsyncSessionLocal
from src.database.models import User
from src.services.redis_client import redis_client
from src.constants import MAX_CONCURRENT_TASKS
from src.quota import QuotaManager

logger = logging.getLogger(__name__)
quota_manager = QuotaManager()

async def check_concurrency_lock(internal_user_id: int) -> Tuple[bool, str]:
    """
    检查用户并发锁。
    返回 (是否允许执行, 错误信息)
    """
    active_tasks = await redis_client.increment_user_concurrency(internal_user_id)
    if active_tasks > MAX_CONCURRENT_TASKS:
        await redis_client.decrement_user_concurrency(internal_user_id)
        return False, f"您当前已有 {MAX_CONCURRENT_TASKS} 个任务正在处理中，请等待其中一个完成后再试！"
    return True, ""

async def release_concurrency_lock(internal_user_id: int):
    """释放用户并发锁"""
    await redis_client.decrement_user_concurrency(internal_user_id)

async def check_and_deduct_credits(internal_user_id: int, cost: int, task_type: str, username: str = None) -> Tuple[bool, str]:
    """
    检查灵石余额并扣除。
    返回 (是否成功, 错误信息)
    """
    if cost <= 0:
        return True, ""

    has_enough = await quota_manager.check_credits(internal_user_id, cost)
    if not has_enough:
        current = await quota_manager.get_credits(internal_user_id)
        return False, f"🚫 **灵石不足**\n\n当前余额: `{current}` 灵石\n本次需要: `{cost}` 灵石\n请获取更多灵石。"

    try:
        await quota_manager.deduct_credits(internal_user_id, cost, username=username, task_type=task_type)
        return True, ""
    except Exception as e:
        logger.error(f"Error deducting credits for user {internal_user_id}: {e}")
        return False, "系统错误，扣费失败"

async def refund_credits(internal_user_id: int, cost: int, task_type: str = "refund", username: str = None):
    """退还灵石"""
    if cost > 0:
        await quota_manager.deduct_credits(internal_user_id, -cost, username=username, task_type=task_type)

async def get_user_priority_and_identity(internal_user_id: int) -> Tuple[int, str, str]:
    """
    获取用户的优先级、身份和组。
    """
    from src.services.permission_service import permission_service
    priority = await permission_service.calculate_user_priority(internal_user_id)
    identity_str = await permission_service.get_user_identity(internal_user_id)
    user_group = await permission_service.get_user_group(internal_user_id)
    return priority, identity_str, user_group
