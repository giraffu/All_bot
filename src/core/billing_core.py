import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Tuple

from src.constants import MAX_CONCURRENT_TASKS
from src.core.exceptions import InsufficientCreditsError
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

    try:
        await quota_manager.deduct_credits(
            internal_user_id, cost, username=username, task_type=task_type
        )
        return True, ""
    except InsufficientCreditsError as e:
        return (
            False,
            f"🚫 **灵石不足**\n\n当前余额: `{e.current}` 灵石\n本次需要: `{e.cost}` 灵石\n请获取更多灵石。",
        )
    except Exception as e:
        logger.error(f"Error deducting credits for user {internal_user_id}: {e}")
        return False, "系统错误，扣费失败"


async def refund_credits(
    internal_user_id: int, cost: int, task_type: str = "refund", username: str = None
):
    """退还灵石"""
    if cost > 0:
        await quota_manager.add_credits(
            internal_user_id, cost, username=username, task_type=task_type
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

DEFAULT_IDENTITY = "外门弟子"
IDENTITY_PRIORITY = {
    "外门弟子": 0,
    "内门弟子": 1,
    "核心弟子": 2,
    "真传弟子": 3,
}
IDENTITY_RATIO = {
    "外门弟子": 1,
    "内门弟子": 2,
    "核心弟子": 5,
    "真传弟子": 10,
}


@dataclass(frozen=True)
class MembershipSettlementResult:
    final_identity: str
    final_expire_at: datetime | None
    credits_to_grant: int
    converted_days: int
    settlement_reason: str
    is_pure_credit_plan: bool
    kept_current_identity: bool
    is_upgrade: bool
    is_downgrade: bool
    is_same_identity_renewal: bool


def normalize_membership_identity(identity: str | None) -> str:
    return identity if identity in IDENTITY_PRIORITY else DEFAULT_IDENTITY


def calculate_membership_settlement(
    current_identity: str,
    current_expire_at: datetime | None,
    target_identity: str,
    duration_days: int,
    reward_credits: int,
    grant_reward_credits: bool,
    now: datetime,
) -> MembershipSettlementResult:
    current_identity = normalize_membership_identity(current_identity)
    target_identity = normalize_membership_identity(target_identity)
    credits_to_grant = int(reward_credits or 0) if grant_reward_credits else 0

    if duration_days < 0:
        raise ValueError("duration_days must be non-negative")

    if duration_days == 0:
        return MembershipSettlementResult(
            final_identity=current_identity,
            final_expire_at=current_expire_at,
            credits_to_grant=credits_to_grant,
            converted_days=0,
            settlement_reason="PURE_CREDIT_PLAN",
            is_pure_credit_plan=True,
            kept_current_identity=True,
            is_upgrade=False,
            is_downgrade=False,
            is_same_identity_renewal=False,
        )

    current_priority = IDENTITY_PRIORITY[current_identity]
    target_priority = IDENTITY_PRIORITY[target_identity]
    has_active_membership = current_expire_at is not None and current_expire_at > now

    if has_active_membership:
        if current_identity == target_identity:
            return MembershipSettlementResult(
                final_identity=target_identity,
                final_expire_at=current_expire_at + timedelta(days=duration_days),
                credits_to_grant=credits_to_grant,
                converted_days=0,
                settlement_reason="RENEWAL",
                is_pure_credit_plan=False,
                kept_current_identity=False,
                is_upgrade=False,
                is_downgrade=False,
                is_same_identity_renewal=True,
            )

        if target_priority > current_priority:
            remaining_days = (current_expire_at - now).total_seconds() / 86400.0
            converted_days = math.ceil(
                (remaining_days * IDENTITY_RATIO[current_identity])
                / IDENTITY_RATIO[target_identity]
            )
            return MembershipSettlementResult(
                final_identity=target_identity,
                final_expire_at=now + timedelta(days=duration_days + converted_days),
                credits_to_grant=credits_to_grant,
                converted_days=converted_days,
                settlement_reason="UPGRADE_CONVERSION",
                is_pure_credit_plan=False,
                kept_current_identity=False,
                is_upgrade=True,
                is_downgrade=False,
                is_same_identity_renewal=False,
            )

        converted_days = math.ceil(
            (duration_days * IDENTITY_RATIO[target_identity])
            / IDENTITY_RATIO[current_identity]
        )
        return MembershipSettlementResult(
            final_identity=current_identity,
            final_expire_at=current_expire_at + timedelta(days=converted_days),
            credits_to_grant=credits_to_grant,
            converted_days=converted_days,
            settlement_reason="DOWNGRADE_EXTENSION",
            is_pure_credit_plan=False,
            kept_current_identity=True,
            is_upgrade=False,
            is_downgrade=True,
            is_same_identity_renewal=False,
        )

    settlement_reason = "NEW_PURCHASE"
    if current_expire_at is not None and current_expire_at <= now:
        settlement_reason = "EXPIRED_REPLACE"
    return MembershipSettlementResult(
        final_identity=target_identity,
        final_expire_at=now + timedelta(days=duration_days),
        credits_to_grant=credits_to_grant,
        converted_days=0,
        settlement_reason=settlement_reason,
        is_pure_credit_plan=False,
        kept_current_identity=False,
        is_upgrade=False,
        is_downgrade=False,
        is_same_identity_renewal=False,
    )


def calculate_identity_conversion(
    current_identity: str,
    current_expire_at: datetime | None,
    new_identity: str,
    duration_days: int,
) -> Tuple[str, datetime | None]:
    """
    兼容旧接口：内部转调统一会员结算 primitive。
    返回 (最终身份, 最终过期时间)
    """
    result = calculate_membership_settlement(
        current_identity=current_identity,
        current_expire_at=current_expire_at,
        target_identity=new_identity,
        duration_days=duration_days,
        reward_credits=0,
        grant_reward_credits=False,
        now=datetime.now(),
    )
    return result.final_identity, result.final_expire_at


def calculate_identity_manual_conversion(
    current_identity: str, current_expire_at: datetime | None, new_identity: str
) -> datetime | None:
    """
    手动修改身份时的残值折算逻辑。
    返回折算后的过期时间。
    """
    now = datetime.now()
    current_identity = normalize_membership_identity(current_identity)
    new_identity = normalize_membership_identity(new_identity)

    if not current_expire_at or current_expire_at <= now or current_identity == new_identity:
        return current_expire_at

    remaining_days = (current_expire_at - now).total_seconds() / 86400.0
    old_ratio = IDENTITY_RATIO.get(current_identity, 1)
    new_ratio = IDENTITY_RATIO.get(new_identity, 1)

    # 残值 = 剩余天数 * 旧比例，折算天数 = 残值 / 新比例
    converted_days = math.ceil((remaining_days * old_ratio) / new_ratio)
    return now + timedelta(days=converted_days)
