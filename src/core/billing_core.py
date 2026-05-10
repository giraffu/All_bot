import logging
from typing import Tuple

from src.constants import MAX_CONCURRENT_TASKS
from src.quota import QuotaManager
from src.services.redis_client import redis_client

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
                return (
                    False,
                    "⚠️ **服务器繁忙**\n\n当前排队任务已超过 200 个，为了保证服务稳定性，**练气期及以下外门弟子**暂不可提交新任务。\n\n💡 请稍后再试，或努力提升修为至**筑基期**，也可通过「个人中心」升级至内门弟子及以上身份获取特权！",
                )

    # 2. 原有并发锁检查
    active_tasks = await redis_client.increment_user_concurrency(internal_user_id)
    if active_tasks > MAX_CONCURRENT_TASKS:
        await redis_client.decrement_user_concurrency(internal_user_id)
        return (
            False,
            f"您当前已有 {MAX_CONCURRENT_TASKS} 个任务正在处理中，请等待其中一个完成后再试！",
        )
    return True, ""


async def release_concurrency_lock(internal_user_id: int):
    """释放用户并发锁"""
    await redis_client.decrement_user_concurrency(internal_user_id)


async def check_and_deduct_credits(
    internal_user_id: int, cost: int, task_type: str, username: str = None
) -> Tuple[bool, str]:
    """
    检查灵石余额并扣除。
    返回 (是否成功, 错误信息)
    """
    if cost <= 0:
        return True, ""

    has_enough = await quota_manager.check_credits(internal_user_id, cost)
    if not has_enough:
        current = await quota_manager.get_credits(internal_user_id)
        return (
            False,
            f"🚫 **灵石不足**\n\n当前余额: `{current}` 灵石\n本次需要: `{cost}` 灵石\n请获取更多灵石。",
        )

    try:
        await quota_manager.deduct_credits(
            internal_user_id, cost, username=username, task_type=task_type
        )
        return True, ""
    except Exception as e:
        logger.error(f"Error deducting credits for user {internal_user_id}: {e}")
        return False, "系统错误，扣费失败"


async def refund_credits(
    internal_user_id: int, cost: int, task_type: str = "refund", username: str = None
):
    """退还灵石"""
    if cost > 0:
        await quota_manager.deduct_credits(
            internal_user_id, -cost, username=username, task_type=task_type
        )


async def get_user_priority_and_identity(internal_user_id: int) -> Tuple[int, str, str]:
    """
    获取用户的优先级、身份和组。
    """
    from src.services.permission_service import permission_service

    priority = await permission_service.calculate_user_priority(internal_user_id)
    identity_str = await permission_service.get_user_identity(internal_user_id)
    user_group = await permission_service.get_user_group(internal_user_id)
    return priority, identity_str, user_group


import math
from datetime import datetime, timedelta


def calculate_identity_conversion(
    current_identity: str,
    current_expire_at: datetime,
    new_identity: str,
    duration_days: int,
) -> Tuple[str, datetime]:
    """
    计算身份折算逻辑。
    返回 (最终身份, 最终过期时间)
    """
    now = datetime.now()
    new_expire_at = current_expire_at
    final_identity = new_identity

    identity_priority = {"外门弟子": 0, "内门弟子": 1, "核心弟子": 2, "真传弟子": 3}
    identity_ratio = {"外门弟子": 1, "内门弟子": 2, "核心弟子": 5, "真传弟子": 10}

    current_priority = identity_priority.get(current_identity, 0)
    new_priority = identity_priority.get(new_identity, 0)

    if new_expire_at and new_expire_at > now:
        if current_identity == new_identity:
            # 同套餐续费
            new_expire_at += timedelta(days=duration_days)
        elif new_priority > current_priority:
            # 升级：将旧身份残值折算为新身份天数
            remaining_days = (new_expire_at - now).total_seconds() / 86400.0
            old_ratio = identity_ratio.get(current_identity, 1)
            new_ratio = identity_ratio.get(new_identity, 1)

            # 残值 = 剩余天数 * 旧比例，折算天数 = 残值 / 新比例
            converted_days = math.ceil((remaining_days * old_ratio) / new_ratio)
            new_expire_at = now + timedelta(days=duration_days + converted_days)
        else:
            # 降级或同级：保留高等级身份，将新赠送的低等级套餐价值折算为高等级身份的天数
            final_identity = current_identity

            old_ratio = identity_ratio.get(current_identity, 1)
            new_ratio = identity_ratio.get(new_identity, 1)

            # 新购价值 = 新套餐天数 * 新比例，折算天数 = 新购价值 / 旧比例
            extra_days = math.ceil((duration_days * new_ratio) / old_ratio)
            new_expire_at += timedelta(days=extra_days)
    else:
        # 已过期或无身份，直接覆盖
        new_expire_at = now + timedelta(days=duration_days)

    return final_identity, new_expire_at


def calculate_identity_manual_conversion(
    current_identity: str, current_expire_at: datetime, new_identity: str
) -> datetime:
    """
    手动修改身份时的残值折算逻辑。
    返回折算后的过期时间。
    """
    now = datetime.now()
    if (
        not current_expire_at
        or current_expire_at <= now
        or current_identity == new_identity
    ):
        return current_expire_at

    identity_ratio = {"外门弟子": 1, "内门弟子": 2, "核心弟子": 5, "真传弟子": 10}

    remaining_days = (current_expire_at - now).total_seconds() / 86400.0
    old_ratio = identity_ratio.get(current_identity, 1)
    new_ratio = identity_ratio.get(new_identity, 1)

    # 残值 = 剩余天数 * 旧比例，折算天数 = 残值 / 新比例
    converted_days = math.ceil((remaining_days * old_ratio) / new_ratio)
    return now + timedelta(days=converted_days)
