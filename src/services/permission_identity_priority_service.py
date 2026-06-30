from src.constants import (
    DYNAMIC_PRIORITY_RULES,
    WEB_ACCESS_ALLOWED_GROUPS,
    WEB_ACCESS_ALLOWED_IDENTITIES,
)
from src.database.core import AsyncSessionLocal
from src.quota import QuotaManager


LOW_TRUST_FREE_TIER_CHECKIN_THRESHOLD = 7
TRUSTED_USER_PRIORITY_BONUS = 40


def _coerce_int(value, default: int = 0) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return default


class PermissionIdentityPriorityService:
    def __init__(self, quota_manager: QuotaManager):
        self.quota_manager = quota_manager

    async def calculate_user_priority(self, user_id: int) -> int:
        stats = await self.quota_manager.get_user_stats(user_id)
        is_low_trust_free_tier = await self.is_low_trust_free_tier_user(
            user_id,
            stats=stats,
        )

        if _coerce_int(stats.get("generation_count")) < 2:
            base_priority = 30
            return (
                base_priority
                if is_low_trust_free_tier
                else base_priority + TRUSTED_USER_PRIORITY_BONUS
            )

        group = await self.get_user_group(user_id)
        identity = await self.get_user_identity(user_id)
        usage = await self.quota_manager.get_daily_usage(user_id)

        group_priority = 0
        group_rules = DYNAMIC_PRIORITY_RULES.get(group, [])
        for limit, priority in group_rules:
            if usage < limit:
                group_priority = priority
                break

        identity_priority = 0
        identity_rules = DYNAMIC_PRIORITY_RULES.get(identity, [])
        for limit, priority in identity_rules:
            if usage < limit:
                identity_priority = priority
                break

        base_priority = group_priority + identity_priority
        return (
            base_priority
            if is_low_trust_free_tier
            else base_priority + TRUSTED_USER_PRIORITY_BONUS
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

    async def is_low_trust_free_tier_user(
        self,
        user_id: int,
        *,
        stats: dict | None = None,
    ) -> bool:
        if stats is None:
            stats = await self.quota_manager.get_user_stats(user_id)

        if (
            _coerce_int(stats.get("checkin_count"))
            <= LOW_TRUST_FREE_TIER_CHECKIN_THRESHOLD
        ):
            return False

        return not await self._has_successful_order(user_id)

    async def refresh_user_group(self, user_id: int, is_member: bool = None) -> str:
        stats = await self.quota_manager.get_user_stats(user_id)
        is_channel_member = (
            is_member
            if is_member is not None
            else (stats.get("is_channel_member") or False)
        )

        group = "凡人"
        if (
            stats["invitation_count"] > 100
            and stats["checkin_count"] > 300
            and stats["generation_count"] > 1000
        ):
            group = "元婴期"
        elif (
            stats["invitation_count"] > 10
            and stats["checkin_count"] > 30
            and stats["generation_count"] > 100
        ):
            group = "金丹期"
        elif (
            stats["invitation_count"] > 1
            and stats["checkin_count"] > 3
            and stats["generation_count"] > 10
        ):
            group = "筑基期"
        elif is_channel_member:
            group = "练气期"

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
        group = await self.get_user_group(user_id)
        identity = await self.get_user_identity(user_id)
        return (
            identity in WEB_ACCESS_ALLOWED_IDENTITIES
            or group in WEB_ACCESS_ALLOWED_GROUPS
        )
