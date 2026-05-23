import math
from dataclasses import dataclass
from datetime import datetime, timedelta

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
) -> tuple[str, datetime | None]:
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

    if (
        not current_expire_at
        or current_expire_at <= now
        or current_identity == new_identity
    ):
        return current_expire_at

    remaining_days = (current_expire_at - now).total_seconds() / 86400.0
    old_ratio = IDENTITY_RATIO.get(current_identity, 1)
    new_ratio = IDENTITY_RATIO.get(new_identity, 1)

    converted_days = math.ceil((remaining_days * old_ratio) / new_ratio)
    return now + timedelta(days=converted_days)
