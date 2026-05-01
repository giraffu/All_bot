from config import CHANNEL_INVITE_LINK, REQUIRED_CHANNEL_ID
from src.constants import DYNAMIC_PRIORITY_RULES
from src.database.core import AsyncSessionLocal
from src.quota import QuotaManager
from src.utils import robust_send_message


class PermissionService:
    def __init__(self):
        self.quota_manager = QuotaManager()

    async def calculate_user_priority(self, user_id: int) -> int:
        """
        Calculate dynamic priority based on user group (修为), identity (身份), and daily usage.
        Priority from group and identity are calculated independently and then added together.
        Rules defined in DYNAMIC_PRIORITY_RULES.
        """
        # 新手特权：前2次生成固定极高优先级 30
        stats = await self.quota_manager.get_user_stats(user_id)
        if stats.get("generation_count", 0) < 2:
            return 30

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
        
        return group_priority + identity_priority

    async def check_access(self, tg_id: int, username: str, full_name: str, bot, chat_id: int) -> bool:
        """
        Check if the user has access to the bot.
        Priority: Channel Subscription > Credits
        """
        from src.core.user_core import get_or_create_user_by_telegram
        internal_user, _ = await get_or_create_user_by_telegram(tg_id, username, full_name)
        internal_user_id = internal_user.id

        # 1. Check Channel Subscription (If configured, this acts as the primary gatekeeper)
        if REQUIRED_CHANNEL_ID:
            try:
                # chat_id can be string (if username) or int
                channel_id = int(REQUIRED_CHANNEL_ID) if REQUIRED_CHANNEL_ID.lstrip('-').isdigit() else REQUIRED_CHANNEL_ID
                member = await bot.get_chat_member(chat_id=channel_id, user_id=tg_id)
                
                # If subscribed, allow access!
                if member.status not in ['left', 'kicked', 'banned']:
                    await self.check_channel_reward(tg_id, username, full_name, bot, internal_user_id)
                    # Ensure is_channel_member is updated in DB
                    await self.quota_manager.update_channel_membership(internal_user_id, True)
                    await self.quota_manager.process_channel_reward(internal_user_id)
                    await self.refresh_user_group(internal_user_id, is_member=True)
                    return True
                else:
                    # Sync "left" status to DB if it was previously True
                    stats = await self.quota_manager.get_user_stats(internal_user_id)
                    if stats.get("is_channel_member"):
                        await self.quota_manager.update_channel_membership(internal_user_id, False)
                        await self.refresh_user_group(internal_user_id, is_member=False)
                
            except Exception as e:
                print(f"⚠️ Channel check failed: {e}")
                # If check fails, fall through to credits check
                pass

        # 2. Check if user has credits (Mortal check)
        # If user has credits, they can use features even if not in channel
        credits = await self.quota_manager.get_credits(internal_user_id)
        if credits > 0:
            # Even if API check failed, if they have credits, let them pass.
            # BUT, we might want to retry updating their group if they are actually a member in DB
            stats = await self.quota_manager.get_user_stats(internal_user_id)
            if stats.get("is_channel_member"):
                 await self.refresh_user_group(internal_user_id, is_member=True)
            return True

        # Default: Access Denied (Must join channel or get credits)
        invite_link = CHANNEL_INVITE_LINK or "https://t.me/AiVisionAV"
        msg = (
            "⛩️ **尚未拜入宗门**\n\n"
            "欲求长生，必先寻得仙缘。您需要先加入我们的 **官方宗门** 才能开始修炼。\n\n"
            f"👉 [点击即刻拜入宗门]({invite_link})"
        )
        await robust_send_message(bot, chat_id, msg, parse_mode="Markdown")
        return False

    async def check_channel_reward(self, tg_id: int, username: str, full_name: str, bot, internal_user_id: int = None):
        """Check and award channel join reward (10 credits)"""
        if internal_user_id:
            user_id = internal_user_id
        else:
            from src.core.user_core import get_or_create_user_by_telegram
            internal_user, _ = await get_or_create_user_by_telegram(tg_id, username, full_name)
            user_id = internal_user.id
            
        try:
            inviter_internal_id = await self.quota_manager.process_channel_reward(user_id)
            if inviter_internal_id:
                try:
                    # To notify inviter, we need their telegram_id
                    async with AsyncSessionLocal() as session:
                        from sqlalchemy import select

                        from src.database.models import User
                        inviter = (await session.execute(select(User).where(User.id == inviter_internal_id))).scalar_one_or_none()
                        if inviter and inviter.telegram_id:
                            await robust_send_message(
                                bot,
                                chat_id=inviter.telegram_id,
                                text=f"🎉 **宗门进阶奖励！**\n\n道友 {full_name} 已成功拜入宗门。\n获得额外奖励：`10` 灵石。",
                                parse_mode="Markdown"
                            )
                except Exception as e:
                    print(f"Failed to notify inviter {inviter_internal_id}: {e}")
        except Exception as e:
            print(f"Failed to check channel reward: {e}")

    async def check_quota(self, tg_id: int, username: str, full_name: str, bot, chat_id: int, cost: int = 1) -> bool:
        """
        Check if user has sufficient credits.
        Returns True if credits are available.
        """
        from src.core.user_core import get_or_create_user_by_telegram
        internal_user, _ = await get_or_create_user_by_telegram(tg_id, username, full_name)
        internal_user_id = internal_user.id
        
        if not await self.quota_manager.check_credits(internal_user_id, cost):
            current = await self.quota_manager.get_credits(internal_user_id, username=username, full_name=full_name)
            msg = f"🚫 **灵石不足**\n\n道友当前余额: `{current}` 灵石\n本次修炼需要: `{cost}` 灵石\n请联系管理员获取更多灵石。"
            await robust_send_message(bot, chat_id, msg, parse_mode="Markdown")
            return False
            
        return True

    async def increment_quota(self, user_id: int, cost: int = 1, username: str = None, task_type: str = "generation"):
        """Deduct credits from user"""
        await self.quota_manager.deduct_credits(user_id, cost, username=username, task_type=task_type)
        # We'll refresh the group separately after the task is logged to ensure counts are accurate.

    async def is_user_exists(self, user_id: int) -> bool:
        """Check if user exists"""
        return await self.quota_manager.is_user_exists(user_id)

    async def sync_channel_status(self, tg_id: int, username: str, full_name: str, bot) -> bool:
        """
        Force sync channel membership status from Telegram API to Database.
        Returns True if user is a member, False otherwise.
        """
        if not REQUIRED_CHANNEL_ID:
            return False

        from src.core.user_core import get_or_create_user_by_telegram
        internal_user, _ = await get_or_create_user_by_telegram(tg_id, username, full_name)
        internal_user_id = internal_user.id

        try:
            channel_id = int(REQUIRED_CHANNEL_ID) if REQUIRED_CHANNEL_ID.lstrip('-').isdigit() else REQUIRED_CHANNEL_ID
            member = await bot.get_chat_member(chat_id=channel_id, user_id=tg_id)
            
            is_member = member.status not in ['left', 'kicked', 'banned']
            
            if is_member:
                # Update DB and process rewards if any
                await self.quota_manager.update_channel_membership(internal_user_id, True)
                await self.check_channel_reward(tg_id, username, full_name, bot, internal_user_id)
                await self.refresh_user_group(internal_user_id, is_member=True)
            else:
                await self.quota_manager.update_channel_membership(internal_user_id, False)
                await self.refresh_user_group(internal_user_id, is_member=False)
                
            return is_member
        except Exception as e:
            from src.logger import logger
            logger.warning(f"Manual channel sync failed for user {tg_id}: {e}")
            return False

    async def ensure_user(self, tg_id: int, username: str, full_name: str, language_code: str = None) -> bool:
        """Ensure user info is up to date in DB. Returns True if user was newly created."""
        from src.core.user_core import get_or_create_user_by_telegram
        internal_user, is_new = await get_or_create_user_by_telegram(tg_id, username, full_name, language_code)
        
        # Sync language_code to Redis Cache
        if internal_user.language_code:
            from src.services.redis_client import redis_client
            if redis_client and redis_client.redis:
                await redis_client.redis.set(f"allbot:user_lang:{internal_user.id}", internal_user.language_code)

        await self.quota_manager.ensure_user(internal_user.id, username=username, full_name=full_name)
        await self.refresh_user_group(internal_user.id)
        return is_new

    async def refresh_user_group(self, user_id: int, is_member: bool = None) -> str:
        """
        Calculate and update user group based on stats.
        Tiers:
        - 元婴期 (Nascent Soul): Invited > 100, Checked in > 300, Total generations > 1000
        - 金丹期 (Golden Core): Invited > 10, Checked in > 30, Total generations > 100
        - 筑基期 (Foundation): Invited > 1, Checked in > 3, Total generations > 10
        - 练气期 (Qi Refining): Joined channel
        - 凡人 (Mortal): Started bot, not joined channel
        """
        stats = await self.quota_manager.get_user_stats(user_id)
        
        # Use provided is_member or fall back to DB value
        is_channel_member = is_member if is_member is not None else (stats.get("is_channel_member") or False)
        
        group = "凡人"
        
        # Check for Nascent Soul criteria
        if (stats["invitation_count"] > 100 and 
            stats["checkin_count"] > 300 and 
            stats["generation_count"] > 1000):
            group = "元婴期"
        # Check for Golden Core criteria
        elif (stats["invitation_count"] > 10 and 
            stats["checkin_count"] > 30 and 
            stats["generation_count"] > 100):
            group = "金丹期"
        # Check for Foundation criteria
        elif (stats["invitation_count"] > 1 and 
            stats["checkin_count"] > 3 and 
            stats["generation_count"] > 10):
            group = "筑基期"
        elif is_channel_member:
            group = "练气期"
        
        await self.quota_manager.update_user_group(user_id, group)
        return group

    async def get_user_detailed_stats(self, tg_id: int) -> dict:
        """Get comprehensive stats for a user profile"""
        from src.core.user_core import get_or_create_user_by_telegram
        internal_user, _ = await get_or_create_user_by_telegram(tg_id)
        internal_user_id = internal_user.id

        stats = await self.quota_manager.get_user_stats(internal_user_id)
        group = await self.get_user_group(internal_user_id)
        identity = await self.get_user_identity(internal_user_id)
        priority = await self.calculate_user_priority(internal_user_id)
        credits = await self.quota_manager.get_credits(internal_user_id)
        
        # 获取邀请人的充值数据
        invitation_recharge_stats = await self.get_invitation_recharge_stats(internal_user_id)
        
        return {
            "group": group,
            "identity": identity,
            "identity_expire_at": stats.get("identity_expire_at"),
            "priority": priority,
            "credits": credits,
            "invitations": stats.get("invitation_count", 0),
            "checkins": stats.get("checkin_count", 0),
            "generations": stats.get("generation_count", 0),
            "total_contributions": stats.get("total_contributions", 0),
            "approved_contributions": stats.get("approved_contributions", 0),
            "invitation_recharge": invitation_recharge_stats
        }

    async def get_invitation_recharge_stats(self, user_id: int) -> dict:
        """
        聚合查询邀请的道友充值情况：
        - 已有 X 位道友完成 X 次充值
        - 累积充值 TON
        - 累积充值 RMB
        - 累积贡献 Stars
        - 预估分成 commission_usdt
        """
        import json
        import random
        from src.services.redis_client import redis_client

        # 1. 尝试读取轻量级缓存 (60-120s TTL)
        cache_key = f"allbot:stats:invitation_recharge:{user_id}"
        if redis_client and redis_client.redis:
            try:
                cached_data = await redis_client.redis.get(cache_key)
                if cached_data:
                    return json.loads(cached_data)
            except Exception:
                pass

        async with AsyncSessionLocal() as session:
            from decimal import Decimal

            from sqlalchemy import and_, select

            from src.database.models import Order, Referral
            from src.exchange_rates import get_exchange_rates
            from src.constants import COMMISSION_RATE

            # 联表查询：查找被该用户邀请且支付成功的订单
            stmt = (
                select(
                    Order.telegram_id,
                    Order.final_price,
                    Order.order_id,
                    Order.created_at
                )
                .join(Referral, Referral.invitee_id == Order.telegram_id)
                .where(
                    and_(
                        Referral.inviter_id == user_id,
                        Order.status == "SUCCESS",
                        Order.final_price > 0
                    )
                )
                .order_by(Order.created_at.asc())
            )
            result = await session.execute(stmt)
            rows = result.all()

            recharged_invitees = set()
            total_ton = Decimal('0.0')
            total_rmb = Decimal('0.0')
            total_stars = 0
            
            # 首单累计用于分成计算
            first_ton = Decimal('0.0')
            first_rmb = Decimal('0.0')
            first_stars = 0

            total_count = len(rows)

            for tg_id, price, order_id, _created_at in rows:
                is_first_order = tg_id not in recharged_invitees
                recharged_invitees.add(tg_id)
                
                # 人民币订单以 RMB_ 开头，Stars订单以 XTR_ 开头
                if order_id and str(order_id).startswith("RMB_"):
                    total_rmb += price
                    if is_first_order:
                        first_rmb += price
                elif order_id and str(order_id).startswith("XTR_"):
                    total_stars += int(price)
                    if is_first_order:
                        first_stars += int(price)
                else:
                    # 根据价格区分支付方式 (Stars 价格通常为整数且较大，如 200, 500)
                    if price >= 100:
                        total_stars += int(price)
                        if is_first_order:
                            first_stars += int(price)
                    else:
                        total_ton += price
                        if is_first_order:
                            first_ton += price

            # 计算汇率折算
            rates = await get_exchange_rates()
            commission_usdt = (
                float(first_ton) * rates.get("ton_to_usdt", 0) +
                float(first_rmb) * rates.get("rmb_to_usdt", 0) +
                float(first_stars) * rates.get("stars_to_usdt", 0)
            ) * COMMISSION_RATE

            result_dict = {
                "recharged_invitees_count": len(recharged_invitees),
                "total_recharge_count": total_count,
                "total_ton": float(total_ton),
                "total_rmb": float(total_rmb),
                "total_stars": total_stars,
                "commission_usdt": round(commission_usdt, 2)
            }
            
            # 写入短缓存
            if redis_client and redis_client.redis:
                try:
                    ttl = random.randint(60, 120)
                    await redis_client.redis.setex(cache_key, ttl, json.dumps(result_dict))
                except Exception:
                    pass

            return result_dict

    async def get_user_credits(self, tg_id: int, username: str, full_name: str) -> int:
        """Get current credits for a user"""
        from src.core.user_core import get_or_create_user_by_telegram
        internal_user, _ = await get_or_create_user_by_telegram(tg_id, username, full_name)
        return await self.quota_manager.get_credits(internal_user.id)

    async def get_user_group(self, user_id: int) -> str:
        """Get user group (修为) from DB"""
        async with AsyncSessionLocal() as session:
            from sqlalchemy import select

            from src.database.models import User
            stmt = select(User.user_group).where(User.id == user_id)
            result = await session.execute(stmt)
            group = result.scalar() or "凡人"
            
            # Migration: map old names to new names if they exist in DB
            mapping = {
                "游客": "凡人",
                "青铜用户": "练气期",
                "白银用户": "筑基期"
            }
            return mapping.get(group, group)
            
    async def get_user_identity(self, user_id: int) -> str:
        """Get effective user identity (身份) from DB"""
        async with AsyncSessionLocal() as session:
            from datetime import datetime

            from sqlalchemy import select

            from src.database.models import User
            stmt = select(User.current_identity, User.identity_expire_at).where(User.id == user_id)
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
        
    async def perform_checkin(self, tg_id: int, username: str, full_name: str) -> tuple[bool, int, str, int, int]:
        """
        Perform daily check-in for user.
        Returns (success, current_credits, error_message, total_checkins, reward)
        """
        from src.core.user_core import get_or_create_user_by_telegram
        internal_user, _ = await get_or_create_user_by_telegram(tg_id, username, full_name)
        internal_user_id = internal_user.id
        
        # Check if user is a Mortal
        user_group = await self.get_user_group(internal_user_id)
        if user_group == "凡人":
            invite_link = CHANNEL_INVITE_LINK or "https://t.me/AiVisionAV"
            msg = (
                "🚫 **凡人无法签到**\n\n"
                "道友目前尚处于凡人境界，请先 **拜入宗门** 踏入 **练气期** 即可解锁每日签到功能！\n\n"
                f"👉 [点击即刻拜入宗门]({invite_link})"
            )
            return False, 0, msg, 0, 0

        # Calculate reward based on identity and group
        identity = await self.get_user_identity(internal_user_id)
        reward = 10
        
        # Apply group base reward
        if user_group == "元婴期":
            reward = 20
        elif user_group == "金丹期":
            reward = 15
        elif user_group == "筑基期":
            reward = 12
        elif user_group == "练气期":
            reward = 10
            
        # Identity adds bonus reward on top of base reward
        if identity == "内门弟子":
            reward += 30
        elif identity == "核心弟子":
            reward += 40
        elif identity == "真传弟子":
            reward += 50

        success = await self.quota_manager.checkin(
            internal_user_id, 
            username=username, 
            full_name=full_name,
            reward=reward
        )
        if success:
            await self.refresh_user_group(internal_user_id)
        
        current_credits = await self.get_user_credits(tg_id, username, full_name)
        stats = await self.quota_manager.get_user_stats(internal_user_id)
        total_checkins = stats.get("checkin_count", 0)
        
        return success, current_credits, "", total_checkins, reward

    async def process_referral(self, tg_id: int, username: str, full_name: str, inviter_tg_id: int) -> tuple[bool, str]:
        """
        Process referral reward.
        Returns (success, message)
        """
        from src.core.user_core import get_or_create_user_by_telegram
        inviter_internal, _ = await get_or_create_user_by_telegram(inviter_tg_id)
        if not inviter_internal:
            return False, "invalid_inviter"
        inviter_internal_id = inviter_internal.id

        new_internal, created = await get_or_create_user_by_telegram(tg_id, username, full_name)
        new_internal_id = new_internal.id
        
        # Check if inviter is a Mortal
        inviter_group = await self.get_user_group(inviter_internal_id)
        if inviter_group == "凡人":
            return False, "visitor_limit"

        success = await self.quota_manager.process_referral(inviter_internal_id, new_internal_id, new_username=username, _new_full_name=full_name)
        if success:
            await self.refresh_user_group(inviter_internal_id)
            return True, "success"
        return False, "already_invited"

    async def get_referral_count(self, user_id: int) -> int:
        """Get referral count"""
        return await self.quota_manager.get_referral_count(user_id)

    async def record_contribution(self, tg_id: int, file_path: str, file_type: str):
        """Record template contribution in DB"""
        from src.core.user_core import get_or_create_user_by_telegram
        internal_user, _ = await get_or_create_user_by_telegram(tg_id)
        await self.quota_manager.add_template_contribution(internal_user.id, file_path, file_type)

    async def check_web_access(self, user_id: int) -> bool:
        """
        Check if user has sufficient identity or group to access the web UI.
        """
        from src.constants import (
            WEB_ACCESS_ALLOWED_GROUPS,
            WEB_ACCESS_ALLOWED_IDENTITIES,
        )
        
        group = await self.get_user_group(user_id)
        identity = await self.get_user_identity(user_id)
        
        is_allowed_identity = identity in WEB_ACCESS_ALLOWED_IDENTITIES
        is_allowed_group = group in WEB_ACCESS_ALLOWED_GROUPS
        
        return is_allowed_identity or is_allowed_group

# Singleton instance
permission_service = PermissionService()
