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
    检查用户并发锁及队列限制。
    返回 (是否允许执行, 错误信息)
    """
    from src.api_client import get_system_status
    from src.services.permission_service import permission_service

    # 1. 检查队列长度与身份
    identity_str = await permission_service.get_user_identity(internal_user_id)
    if identity_str == "外门弟子":
        # 补充检查修为境界：凡人、练气期不可突破排队限制，筑基期及以上可以
        user_group = await permission_service.get_user_group(internal_user_id)
        if user_group in ["凡人", "练气期"]:
            sys_status = await get_system_status()
            if sys_status and sys_status.get("queue_size", 0) > 200:
                return False, "⚠️ **服务器繁忙**\n\n当前排队任务已超过 200 个，为了保证服务稳定性，**练气期及以下外门弟子**暂不可提交新任务。\n\n💡 请稍后再试，或努力提升修为至**筑基期**，也可通过「个人中心」升级至内门弟子及以上身份获取特权！"

    # 2. 原有并发锁检查
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
