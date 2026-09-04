from src.database.core import AsyncSessionLocal
from src.quota import QuotaManager
from src.services.user_tier_policy_service import (
    CULTIVATION_RANKS,
    get_identity_policy,
    get_priority_for_usage,
    get_rank_policy,
    load_user_tier_policy_config,
)


LOW_TRUST_FREE_TIER_CHECKIN_THRESHOLD = 7
LOW_TRUST_INVITEE_COUNT_EXEMPTION_THRESHOLD = 100
LOW_TRUST_INVITEE_SUCCESS_RATE_PERCENT_THRESHOLD = 3
TRUSTED_USER_PRIORITY_BONUS = 40


def _coerce_int(value, default: int = 0) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return default


def has_high_quality_referral_exemption(
    *,
    referral_count: int,
    successful_invitee_count: int,
    referral_count_threshold: int = LOW_TRUST_INVITEE_COUNT_EXEMPTION_THRESHOLD,
    success_rate_percent_threshold: int = LOW_TRUST_INVITEE_SUCCESS_RATE_PERCENT_THRESHOLD,
) -> bool:
    referral_count = _coerce_int(referral_count)
    successful_invitee_count = _coerce_int(successful_invitee_count)
    return (
        referral_count > referral_count_threshold
        and successful_invitee_count * 100
        > referral_count * success_rate_percent_threshold
    )


class PermissionIdentityPriorityService:
    def __init__(self, quota_manager: QuotaManager, *, policy_loader=load_user_tier_policy_config):
        self.quota_manager = quota_manager
        self.policy_loader = policy_loader

    async def calculate_user_priority(self, user_id: int) -> int:
        policy = await self.policy_loader()
        low_trust = policy["low_trust"]
        stats = await self.quota_manager.get_user_stats(user_id)
        is_low_trust_free_tier = await self.is_low_trust_free_tier_user(
            user_id,
            stats=stats,
            policy=policy,
        )

        if _coerce_int(stats.get("generation_count")) < low_trust["new_user_generation_threshold"]:
            base_priority = low_trust["new_user_base_priority"]
            return (
                base_priority
                if is_low_trust_free_tier
                else base_priority + low_trust["trusted_priority_bonus"]
            )

        group = await self.get_user_group(user_id)
        identity = await self.get_user_identity(user_id)
        usage = await self.quota_manager.get_daily_usage(user_id)

        group_priority = get_priority_for_usage(
            get_rank_policy(policy, group)["priority_rules"], usage
        )
        identity_priority = get_priority_for_usage(
            get_identity_policy(policy, identity)["priority_rules"], usage
        )

        base_priority = group_priority + identity_priority
        return (
            base_priority
            if is_low_trust_free_tier
            else base_priority + low_trust["trusted_priority_bonus"]
        )

    async def _has_successful_order(self, user_id: int) -> bool:
        async with AsyncSessionLocal() as session:
            from sqlalchemy import select

            from src.database.models import Order

            stmt = (
                select(Order.id)
                .where(
                    Order.internal_user_id == user_id,
                    Order.status == "SUCCESS",
                )
                .limit(1)
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none() is not None

    async def _has_high_quality_referral_exemption(
        self,
        user_id: int,
        *,
        referral_count_threshold: int = LOW_TRUST_INVITEE_COUNT_EXEMPTION_THRESHOLD,
        success_rate_percent_threshold: int = LOW_TRUST_INVITEE_SUCCESS_RATE_PERCENT_THRESHOLD,
    ) -> bool:
        async with AsyncSessionLocal() as session:
            from sqlalchemy import and_, func, select

            from src.database.models import Order, Referral

            stmt = (
                select(
                    func.count(func.distinct(Referral.invitee_id)),
                    func.count(func.distinct(Order.internal_user_id)),
                )
                .select_from(Referral)
                .outerjoin(
                    Order,
                    and_(
                        Order.internal_user_id == Referral.invitee_id,
                        Order.status == "SUCCESS",
                    ),
                )
                .where(Referral.inviter_id == user_id)
            )
            result = await session.execute(stmt)
            referral_count, successful_invitee_count = result.one()
            return has_high_quality_referral_exemption(
                referral_count=referral_count,
                successful_invitee_count=successful_invitee_count,
                referral_count_threshold=referral_count_threshold,
                success_rate_percent_threshold=success_rate_percent_threshold,
            )

    async def is_low_trust_free_tier_user(
        self,
        user_id: int,
        *,
        stats: dict | None = None,
        policy: dict | None = None,
    ) -> bool:
        policy = policy or await self.policy_loader()
        low_trust = policy["low_trust"]
        if not low_trust["enabled"]:
            return False
        if stats is None:
            stats = await self.quota_manager.get_user_stats(user_id)

        if (
            _coerce_int(stats.get("checkin_count"))
            <= low_trust["checkin_threshold"]
        ):
            return False

        if low_trust["successful_order_exempt"] and await self._has_successful_order(user_id):
            return False

        return not await self._has_high_quality_referral_exemption(
            user_id,
            referral_count_threshold=low_trust["referral_count_threshold"],
            success_rate_percent_threshold=low_trust["successful_invitee_rate_percent_threshold"],
        )

    async def refresh_user_group(self, user_id: int, is_member: bool = None) -> str:
        policy = await self.policy_loader()
        stats = await self.quota_manager.get_user_stats(user_id)
        is_channel_member = (
            is_member
            if is_member is not None
            else (stats.get("is_channel_member") or False)
        )

        group = "凡人"
        for candidate in reversed(CULTIVATION_RANKS[1:]):
            upgrade = policy["cultivation_ranks"][candidate]["upgrade"]
            if (
                _coerce_int(stats.get("invitation_count")) >= upgrade["invitations"]
                and _coerce_int(stats.get("checkin_count")) >= upgrade["checkins"]
                and _coerce_int(stats.get("generation_count")) >= upgrade["generations"]
                and (not upgrade["channel_member"] or is_channel_member)
            ):
                group = candidate
                break

        await self.quota_manager.update_user_group(user_id, group)
        return group

    async def get_user_group(self, user_id: int) -> str:
        async with AsyncSessionLocal() as session:
            from sqlalchemy import select

            from src.database.models import User

            stmt = select(User.user_group).where(User.id == user_id)
            result = await session.execute(stmt)
            group = result.scalar() or "凡人"
            mapping = {"游客": "凡人", "青铜用户": "练气期", "白银用户": "筑基期"}
            return mapping.get(group, group)

    async def get_user_identity(self, user_id: int) -> str:
        async with AsyncSessionLocal() as session:
            from datetime import datetime
            from sqlalchemy import select

            from src.database.models import User

            stmt = select(User.current_identity, User.identity_expire_at).where(
                User.id == user_id
            )
            result = await session.execute(stmt)
            row = result.first()
            if not row:
                return "外门弟子"

            current_identity = row.current_identity
            identity_expire_at = row.identity_expire_at
            if current_identity and current_identity != "外门弟子":
                if not identity_expire_at or identity_expire_at > datetime.now():
                    return current_identity

            return "外门弟子"

    async def check_web_access(self, user_id: int) -> bool:
        policy = await self.policy_loader()
        group = await self.get_user_group(user_id)
        identity = await self.get_user_identity(user_id)
        return (
            get_identity_policy(policy, identity)["benefits"]["web_access"]
            or get_rank_policy(policy, group)["benefits"]["web_access"]
        )
