from config import REQUIRED_CHANNEL_ID
from src.quota import QuotaManager


class PermissionAccessService:
    def __init__(
        self,
        quota_manager: QuotaManager,
        *,
        check_channel_reward_func,
        refresh_user_group_func,
        check_web_access_func,
    ):
        self.quota_manager = quota_manager
        self.check_channel_reward_func = check_channel_reward_func
        self.refresh_user_group_func = refresh_user_group_func
        self.check_web_access_func = check_web_access_func

    async def check_access(
        self, tg_id: int, username: str, full_name: str, is_member: bool = None
    ) -> int | None:
        from src.core.exceptions import AccessDeniedError
        from src.core.user_core import get_or_create_user_by_telegram

        internal_user, _ = await get_or_create_user_by_telegram(
            tg_id, username, full_name
        )
        internal_user_id = internal_user.id
        inviter_id = None

        if REQUIRED_CHANNEL_ID and is_member is not None:
            if is_member:
                inviter_id = await self.check_channel_reward_func(
                    tg_id, username, full_name, internal_user_id
                )
                await self.quota_manager.update_channel_membership(
                    internal_user_id, True
                )
                await self.refresh_user_group_func(internal_user_id, is_member=True)
                return inviter_id

            stats = await self.quota_manager.get_user_stats(internal_user_id)
            if stats.get("is_channel_member"):
                await self.quota_manager.update_channel_membership(internal_user_id, False)
                await self.refresh_user_group_func(internal_user_id, is_member=False)

        credits = await self.quota_manager.get_credits(internal_user_id)
        if credits > 0:
            stats = await self.quota_manager.get_user_stats(internal_user_id)
            if stats.get("is_channel_member"):
                await self.refresh_user_group_func(internal_user_id, is_member=True)
            return inviter_id

        if is_member is None:
            stats = await self.quota_manager.get_user_stats(internal_user_id)
            if stats.get("is_channel_member"):
                return inviter_id

        raise AccessDeniedError()

    async def ensure_user(
        self, tg_id: int, username: str, full_name: str, language_code: str = None
    ) -> bool:
        from src.core.user_core import get_or_create_user_by_telegram

        internal_user, is_new = await get_or_create_user_by_telegram(
            tg_id, username, full_name, language_code
        )

        if internal_user.language_code:
            from src.services.redis_client import redis_client

            if redis_client and redis_client.redis:
                await redis_client.redis.set(
                    f"allbot:user_lang:{internal_user.id}", internal_user.language_code
                )
                await redis_client.redis.set(
                    f"allbot:user_lang:tg:{tg_id}", internal_user.language_code
                )

        await self.quota_manager.ensure_user(
            internal_user.id, username=username, full_name=full_name
        )
        await self.refresh_user_group_func(internal_user.id)
        return is_new

    async def check_web_access(self, user_id: int) -> bool:
        return await self.check_web_access_func(user_id)
