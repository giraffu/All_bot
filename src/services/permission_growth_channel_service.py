from config import CHANNEL_INVITE_LINK, REQUIRED_CHANNEL_ID
from src.database.core import AsyncSessionLocal
from src.quota import QuotaManager


class PermissionGrowthChannelService:
    def __init__(
        self,
        quota_manager: QuotaManager,
        *,
        refresh_user_group_func,
        get_user_group_func,
        get_user_identity_func,
        get_user_credits_func,
    ):
        self.quota_manager = quota_manager
        self.refresh_user_group_func = refresh_user_group_func
        self.get_user_group_func = get_user_group_func
        self.get_user_identity_func = get_user_identity_func
        self.get_user_credits_func = get_user_credits_func

    async def check_channel_reward(
        self, tg_id: int, username: str, full_name: str, internal_user_id: int = None
    ) -> int | None:
        if internal_user_id:
            user_id = internal_user_id
        else:
            from src.core.user_core import get_or_create_user_by_telegram

            internal_user, _ = await get_or_create_user_by_telegram(
                tg_id, username, full_name
            )
            user_id = internal_user.id

        try:
            return await self.quota_manager.process_channel_reward(user_id)
        except Exception as e:
            from src.logger import logger

            logger.warning(f"Failed to check channel reward: {e}")
            return None

    async def sync_channel_status(
        self, tg_id: int, username: str, full_name: str, is_member: bool
    ) -> int | None:
        if not REQUIRED_CHANNEL_ID:
            return None

        from src.core.user_core import get_or_create_user_by_telegram

        internal_user, _ = await get_or_create_user_by_telegram(
            tg_id, username, full_name
        )
        internal_user_id = internal_user.id

        try:
            if is_member:
                await self.quota_manager.update_channel_membership(internal_user_id, True)
                inviter_id = await self.check_channel_reward(
                    tg_id, username, full_name, internal_user_id
                )
                await self.refresh_user_group_func(internal_user_id, is_member=True)
                return inviter_id

            await self.quota_manager.update_channel_membership(internal_user_id, False)
            await self.refresh_user_group_func(internal_user_id, is_member=False)
            return None
        except Exception as e:
            from src.logger import logger

            logger.warning(f"Manual channel sync failed for user {tg_id}: {e}")
            return None

    async def perform_checkin(
        self, tg_id: int, username: str, full_name: str
    ) -> tuple[bool, int, str, int, int]:
        from src.core.user_core import get_or_create_user_by_telegram

        internal_user, _ = await get_or_create_user_by_telegram(
            tg_id, username, full_name
        )
        internal_user_id = internal_user.id

        user_group = await self.get_user_group_func(internal_user_id)
        if user_group == "凡人":
            invite_link = CHANNEL_INVITE_LINK or "https://t.me/AiVisionAV"
            msg = (
                "🚫 **凡人无法签到**\n\n"
                "道友目前尚处于凡人境界，请先 **拜入宗门** 踏入 **练气期** 即可解锁每日签到功能！\n\n"
                f"👉 [点击即刻拜入宗门]({invite_link})"
            )
            return False, 0, msg, 0, 0

        identity = await self.get_user_identity_func(internal_user_id)
        base_reward = 10
        if user_group == "元婴期":
            base_reward = 20
        elif user_group == "金丹期":
            base_reward = 15
        elif user_group == "筑基期":
            base_reward = 12
        elif user_group == "练气期":
            base_reward = 10

        identity_bonus = 0
        if identity == "内门弟子":
            identity_bonus = 30
        elif identity == "核心弟子":
            identity_bonus = 40
        elif identity == "真传弟子":
            identity_bonus = 50

        reward = base_reward + identity_bonus

        success = await self.quota_manager.checkin(
            internal_user_id,
            username=username,
            full_name=full_name,
            reward=reward,
            checkin_base_reward=base_reward,
            checkin_identity_bonus=identity_bonus,
            checkin_user_group=user_group,
            checkin_identity=identity,
        )
        if success:
            await self.refresh_user_group_func(internal_user_id)

        current_credits = await self.get_user_credits_func(tg_id, username, full_name)
        stats = await self.quota_manager.get_user_stats(internal_user_id)
        total_checkins = stats.get("checkin_count", 0)
        return success, current_credits, "", total_checkins, reward

    async def process_referral(
        self, tg_id: int, username: str, full_name: str, inviter_tg_id: int
    ) -> tuple[bool, str]:
        from src.core.user_core import get_or_create_user_by_telegram

        inviter_internal, _ = await get_or_create_user_by_telegram(inviter_tg_id)
        if not inviter_internal:
            return False, "invalid_inviter"
        inviter_internal_id = inviter_internal.id

        new_internal, is_new = await get_or_create_user_by_telegram(
            tg_id, username, full_name
        )
        if not is_new:
            return False, "existing_user"
        new_internal_id = new_internal.id

        inviter_group = await self.get_user_group_func(inviter_internal_id)
        if inviter_group == "凡人":
            return False, "visitor_limit"

        success = await self.quota_manager.process_referral(
            inviter_internal_id,
            new_internal_id,
            new_user_was_created=is_new,
            new_username=username,
            _new_full_name=full_name,
        )
        if success:
            await self.refresh_user_group_func(inviter_internal_id)
            return True, "success"
        return False, "already_invited"

    async def get_referral_count(self, user_id: int) -> int:
        return await self.quota_manager.get_referral_count(user_id)

    async def get_invitation_recharge_stats(self, user_id: int) -> dict:
        import json
        import random

        from src.services.redis_client import redis_client

        cache_key = f"allbot:stats:invitation_recharge:{user_id}"
        if redis_client and redis_client.redis:
            try:
                cached_data = await redis_client.redis.get(cache_key)
                if cached_data:
                    return json.loads(cached_data)
            except Exception:
                pass

        async with AsyncSessionLocal() as session:
            from src.services.referral_stats_service import (
                query_invitation_recharge_stats,
            )

            result_dict = await query_invitation_recharge_stats(session, user_id)
            if redis_client and redis_client.redis:
                try:
                    ttl = random.randint(60, 120)
                    await redis_client.redis.setex(
                        cache_key, ttl, json.dumps(result_dict)
                    )
                except Exception:
                    pass
            return result_dict

    async def record_contribution(self, tg_id: int, file_path: str, file_type: str):
        from src.core.user_core import get_or_create_user_by_telegram

        internal_user, _ = await get_or_create_user_by_telegram(tg_id)
        await self.quota_manager.add_template_contribution(
            internal_user.id, file_path, file_type
        )
