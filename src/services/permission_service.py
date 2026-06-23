from src.quota import QuotaManager
from src.services.permission_access_service import PermissionAccessService
from src.services.permission_growth_channel_service import (
    PermissionGrowthChannelService,
)
from src.services.permission_identity_priority_service import (
    PermissionIdentityPriorityService,
)
from src.services.permission_quota_service import PermissionQuotaService


class PermissionService:
    def __init__(self):
        self.quota_manager = QuotaManager()
        self.quota = PermissionQuotaService(self.quota_manager)
        self.identity_priority = PermissionIdentityPriorityService(self.quota_manager)
        self.growth_channel = PermissionGrowthChannelService(
            self.quota_manager,
            refresh_user_group_func=self.identity_priority.refresh_user_group,
            get_user_group_func=self.identity_priority.get_user_group,
            get_user_identity_func=self.identity_priority.get_user_identity,
            get_user_credits_func=self.quota.get_user_credits,
        )
        self.access = PermissionAccessService(
            self.quota_manager,
            check_channel_reward_func=self.growth_channel.check_channel_reward,
            refresh_user_group_func=self.identity_priority.refresh_user_group,
            check_web_access_func=self.identity_priority.check_web_access,
        )

    async def _build_user_detailed_stats(self, internal_user_id: int) -> dict:
        stats = await self.quota_manager.get_user_stats(internal_user_id)
        group = await self.identity_priority.get_user_group(internal_user_id)
        identity = await self.identity_priority.get_user_identity(internal_user_id)
        priority = await self.identity_priority.calculate_user_priority(internal_user_id)
        credits = await self.quota_manager.get_credits(internal_user_id)

        invitation_recharge_stats = await self.growth_channel.get_invitation_recharge_stats(
            internal_user_id,
        )

        return {
            "group": group,
            "identity": identity,
            "identity_expire_at": stats.get("identity_expire_at"),
            "priority": priority,
            "credits": credits,
            "invitations": stats.get("invitation_count", 0),
            "checkins": stats.get("checkin_count", 0),
            "generations": stats.get("generation_count", 0),
            "today_generations": stats.get("today_generation_count", 0),
            "total_contributions": stats.get("total_contributions", 0),
            "approved_contributions": stats.get("approved_contributions", 0),
            "invitation_recharge": invitation_recharge_stats,
        }

    async def calculate_user_priority(self, user_id: int) -> int:
        return await self.identity_priority.calculate_user_priority(user_id)

    async def check_access(
        self, tg_id: int, username: str, full_name: str, is_member: bool = None
    ) -> int:
        return await self.access.check_access(tg_id, username, full_name, is_member)

    async def check_channel_reward(
        self, tg_id: int, username: str, full_name: str, internal_user_id: int = None
    ) -> int:
        return await self.growth_channel.check_channel_reward(
            tg_id, username, full_name, internal_user_id
        )

    async def check_quota(
        self, tg_id: int, username: str, full_name: str, cost: int = 1
    ) -> bool:
        return await self.quota.check_quota(tg_id, username, full_name, cost)

    async def increment_quota(
        self,
        user_id: int,
        credits: int = 1,
        username: str = None,
        task_type: str = "generation",
    ):
        await self.quota.increment_quota(
            user_id=user_id,
            credits=credits,
            username=username,
            task_type=task_type,
        )

    async def refund_quota(
        self,
        user_id: int,
        credits: int,
        username: str = None,
        task_type: str = "refund",
    ):
        await self.quota.refund_quota(
            user_id=user_id,
            credits=credits,
            username=username,
            task_type=task_type,
        )

    async def is_user_exists(self, user_id: int) -> bool:
        return await self.quota.is_user_exists(user_id)

    async def sync_channel_status(
        self, tg_id: int, username: str, full_name: str, is_member: bool
    ) -> int:
        return await self.growth_channel.sync_channel_status(
            tg_id, username, full_name, is_member
        )

    async def ensure_user(
        self, tg_id: int, username: str, full_name: str, language_code: str = None
    ) -> bool:
        return await self.access.ensure_user(
            tg_id, username, full_name, language_code
        )

    async def refresh_user_group(self, user_id: int, is_member: bool = None) -> str:
        return await self.identity_priority.refresh_user_group(user_id, is_member)

    async def get_user_detailed_stats(self, tg_id: int) -> dict:
        """Get comprehensive stats for a user profile"""
        from src.core.user_core import get_or_create_user_by_telegram

        internal_user, _ = await get_or_create_user_by_telegram(tg_id)
        return await self._build_user_detailed_stats(internal_user.id)

    async def get_user_detailed_stats_by_user_id(self, user_id: int) -> dict:
        """Get comprehensive stats for a user profile by internal user id."""
        return await self._build_user_detailed_stats(user_id)

    async def get_invitation_recharge_stats(self, user_id: int) -> dict:
        return await self.growth_channel.get_invitation_recharge_stats(user_id)

    async def get_user_credits(self, tg_id: int, username: str, full_name: str) -> int:
        return await self.quota.get_user_credits(tg_id, username, full_name)

    async def get_user_group(self, user_id: int) -> str:
        return await self.identity_priority.get_user_group(user_id)

    async def get_user_identity(self, user_id: int) -> str:
        return await self.identity_priority.get_user_identity(user_id)

    async def perform_checkin(
        self, tg_id: int, username: str, full_name: str
    ) -> tuple[bool, int, str, int, int]:
        return await self.growth_channel.perform_checkin(tg_id, username, full_name)

    async def process_referral(
        self, tg_id: int, username: str, full_name: str, inviter_tg_id: int
    ) -> tuple[bool, str]:
        return await self.growth_channel.process_referral(
            tg_id, username, full_name, inviter_tg_id
        )

    async def get_referral_count(self, user_id: int) -> int:
        return await self.growth_channel.get_referral_count(user_id)

    async def record_contribution(self, tg_id: int, file_path: str, file_type: str):
        await self.growth_channel.record_contribution(tg_id, file_path, file_type)

    async def check_web_access(self, user_id: int) -> bool:
        return await self.access.check_web_access(user_id)


# Singleton instance
permission_service = PermissionService()
