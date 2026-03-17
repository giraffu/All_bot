from telegram import Update
from telegram.ext import ContextTypes
from config import REQUIRED_CHANNEL_ID, CHANNEL_INVITE_LINK
from src.quota import QuotaManager
from src.database.core import AsyncSessionLocal
from src.utils import robust_send_message
from src.constants import DYNAMIC_PRIORITY_RULES

class PermissionService:
    def __init__(self):
        self.quota_manager = QuotaManager()

    async def calculate_user_priority(self, user_id: int) -> int:
        """
        Calculate dynamic priority based on user group and daily usage.
        Rules defined in DYNAMIC_PRIORITY_RULES.
        """
        group = await self.get_user_group(user_id)
        usage = await self.quota_manager.get_daily_usage(user_id)
        
        rules = DYNAMIC_PRIORITY_RULES.get(group, [])
        for limit, priority in rules:
            if usage < limit:
                return priority
        
        # If no rule matched (usage exceeded all limits), or empty rules (Mortal), return 0
        return 0

    async def check_access(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """
        Check if the user has access to the bot.
        Priority: Channel Subscription > Credits
        """
        user = update.effective_user
        if not user:
            return False

        # Ensure user exists in DB whenever they interact
        await self.quota_manager.ensure_user(user.id, username=user.username, full_name=user.full_name)
        
        # 1. Check Channel Subscription (If configured, this acts as the primary gatekeeper)
        if REQUIRED_CHANNEL_ID:
            try:
                # chat_id can be string (if username) or int
                channel_id = int(REQUIRED_CHANNEL_ID) if REQUIRED_CHANNEL_ID.lstrip('-').isdigit() else REQUIRED_CHANNEL_ID
                member = await context.bot.get_chat_member(chat_id=channel_id, user_id=user.id)
                
                # If subscribed, allow access!
                if member.status not in ['left', 'kicked', 'banned']:
                    await self.check_channel_reward(user, context)
                    # Ensure is_channel_member is updated in DB
                    await self.quota_manager.update_channel_membership(user.id, True)
                    await self.quota_manager.process_channel_reward(user.id)
                    await self.refresh_user_group(user.id, is_member=True)
                    return True
                else:
                    # Sync "left" status to DB if it was previously True
                    stats = await self.quota_manager.get_user_stats(user.id)
                    if stats.get("is_channel_member"):
                        await self.quota_manager.update_channel_membership(user.id, False)
                        await self.refresh_user_group(user.id, is_member=False)
                
            except Exception as e:
                print(f"⚠️ Channel check failed: {e}")
                # If check fails, fall through to credits check
                pass

        # 2. Check if user has credits (Mortal check)
        # If user has credits, they can use features even if not in channel
        credits = await self.quota_manager.get_credits(user.id)
        if credits > 0:
            # Even if API check failed, if they have credits, let them pass.
            # BUT, we might want to retry updating their group if they are actually a member in DB
            stats = await self.quota_manager.get_user_stats(user.id)
            if stats.get("is_channel_member"):
                 await self.refresh_user_group(user.id, is_member=True)
            return True

        # Default: Access Denied (Must join channel or get credits)
        # Final safety check: if API failed but we suspect they might be a member (e.g. from DB or just retry),
        # we can't really do much without credits.
        # However, user mentioned they are in channel but DB says False (Mortal).
        # This block is reached if:
        # 1. Channel check returned 'left/kicked' OR Channel check FAILED (exception)
        # 2. AND Credits <= 0
        
        # If the channel check FAILED (exception), we might be blocking a valid user who has 0 credits.
        # But we can't let them in without verifying.
        # The user says "I am in channel", so check must be returning 'left' or failing.
        
        invite_link = CHANNEL_INVITE_LINK or "https://t.me/AiVisionAV"
        msg = (
            "⛩️ **尚未拜入宗门**\n\n"
            "欲求长生，必先寻得仙缘。您需要先加入我们的 **官方宗门** 才能开始修炼。\n\n"
            f"👉 [点击即刻拜入宗门]({invite_link})"
        )
        await robust_send_message(context.bot, update.effective_chat.id, msg, parse_mode="Markdown")
        return False

    async def check_channel_reward(self, user, context: ContextTypes.DEFAULT_TYPE):
        """Check and award channel join reward (20 credits)"""
        try:
            inviter_id = await self.quota_manager.process_channel_reward(user.id)
            if inviter_id:
                try:
                    await robust_send_message(
                        context.bot,
                        chat_id=inviter_id,
                        text=f"🎉 **宗门进阶奖励！**\n\n道友 {user.full_name} 已成功拜入宗门。\n获得额外奖励：`20` 灵石。",
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    print(f"Failed to notify inviter {inviter_id}: {e}")
        except Exception as e:
            print(f"Failed to check channel reward: {e}")

    async def check_quota(self, update: Update, context: ContextTypes.DEFAULT_TYPE, cost: int = 1) -> bool:
        """
        Check if user has sufficient credits.
        Returns True if credits are available.
        """
        user = update.effective_user
        user_id = user.id
        
        if not await self.quota_manager.check_credits(user_id, cost):
            current = await self.quota_manager.get_credits(user_id, username=user.username, full_name=user.full_name)
            msg = f"🚫 **灵石不足**\n\n道友当前余额: `{current}` 灵石\n本次修炼需要: `{cost}` 灵石\n请联系管理员获取更多灵石。"
            await robust_send_message(context.bot, update.effective_chat.id, msg, parse_mode="Markdown")
            return False
            
        return True

    async def increment_quota(self, user_id: int, cost: int = 1, username: str = None, task_type: str = "generation"):
        """Deduct credits from user"""
        await self.quota_manager.deduct_credits(user_id, cost, username=username, task_type=task_type)
        # We'll refresh the group separately after the task is logged to ensure counts are accurate.

    async def is_user_exists(self, user_id: int) -> bool:
        """Check if user exists"""
        return await self.quota_manager.is_user_exists(user_id)

    async def sync_channel_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """
        Force sync channel membership status from Telegram API to Database.
        Returns True if user is a member, False otherwise.
        """
        user = update.effective_user
        if not user or not REQUIRED_CHANNEL_ID:
            return False

        try:
            channel_id = int(REQUIRED_CHANNEL_ID) if REQUIRED_CHANNEL_ID.lstrip('-').isdigit() else REQUIRED_CHANNEL_ID
            member = await context.bot.get_chat_member(chat_id=channel_id, user_id=user.id)
            
            is_member = member.status not in ['left', 'kicked', 'banned']
            
            if is_member:
                # Update DB and process rewards if any
                await self.quota_manager.update_channel_membership(user.id, True)
                await self.check_channel_reward(user, context)
                await self.refresh_user_group(user.id, is_member=True)
            else:
                await self.quota_manager.update_channel_membership(user.id, False)
                await self.refresh_user_group(user.id, is_member=False)
                
            return is_member
        except Exception as e:
            from src.logger import logger
            logger.warning(f"Manual channel sync failed for user {user.id}: {e}")
            return False

    async def ensure_user(self, update: Update):
        """Ensure user info is up to date in DB"""
        user = update.effective_user
        if user:
            await self.quota_manager.ensure_user(user.id, username=user.username, full_name=user.full_name)
            await self.refresh_user_group(user.id)

    async def refresh_user_group(self, user_id: int, is_member: bool = None) -> str:
        """
        Calculate and update user group based on stats.
        Tiers:
        - 金丹期 (Golden Core): Invited > 10, Checked in > 30, Total generations > 100
        - 筑基期 (Foundation): Invited > 1, Checked in > 3, Total generations > 10
        - 练气期 (Qi Refining): Joined channel
        - 凡人 (Mortal): Started bot, not joined channel
        """
        stats = await self.quota_manager.get_user_stats(user_id)
        
        # Use provided is_member or fall back to DB value
        is_channel_member = is_member if is_member is not None else (stats.get("is_channel_member") or False)
        
        group = "凡人"
        
        # Check for Golden Core criteria
        if (stats["invitation_count"] > 10 and 
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

    async def get_user_detailed_stats(self, user_id: int) -> dict:
        """Get comprehensive stats for a user profile"""
        stats = await self.quota_manager.get_user_stats(user_id)
        group = await self.get_user_group(user_id)
        credits = await self.quota_manager.get_credits(user_id)
        
        return {
            "group": group,
            "credits": credits,
            "invitations": stats.get("invitation_count", 0),
            "checkins": stats.get("checkin_count", 0),
            "generations": stats.get("generation_count", 0),
            "total_contributions": stats.get("total_contributions", 0),
            "approved_contributions": stats.get("approved_contributions", 0)
        }

    async def get_user_credits(self, update: Update) -> int:
        """Get current credits for a user"""
        user = update.effective_user
        return await self.quota_manager.get_credits(user.id, username=user.username, full_name=user.full_name)

    async def get_user_group(self, user_id: int) -> str:
        """Get user group from DB"""
        async with AsyncSessionLocal() as session:
            from src.database.models import User
            from sqlalchemy import select
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
        
    async def perform_checkin(self, update: Update) -> tuple[bool, int, str, int]:
        """
        Perform daily check-in for user.
        Returns (success, current_credits, error_message, total_checkins)
        """
        user = update.effective_user
        
        # Check if user is a Mortal
        user_group = await self.get_user_group(user.id)
        if user_group == "凡人":
            invite_link = CHANNEL_INVITE_LINK or "https://t.me/AiVisionAV"
            msg = (
                "🚫 **凡人无法签到**\n\n"
                "道友目前尚处于凡人境界，请先 **拜入宗门** 踏入 **练气期** 即可解锁每日签到功能！\n\n"
                f"👉 [点击即刻拜入宗门]({invite_link})"
            )
            return False, 0, msg, 0

        success = await self.quota_manager.checkin(user.id, username=user.username, full_name=user.full_name, reward=20)
        if success:
            await self.refresh_user_group(user.id)
        
        current_credits = await self.get_user_credits(update)
        stats = await self.quota_manager.get_user_stats(user.id)
        total_checkins = stats.get("checkin_count", 0)
        
        return success, current_credits, "", total_checkins

    async def process_referral(self, update: Update, inviter_id: int) -> tuple[bool, str]:
        """
        Process referral reward.
        Returns (success, message)
        """
        user = update.effective_user
        
        # Check if inviter is a Mortal
        inviter_group = await self.get_user_group(inviter_id)
        if inviter_group == "凡人":
            return False, "visitor_limit"

        success = await self.quota_manager.process_referral(inviter_id, user.id, new_username=user.username, new_full_name=user.full_name)
        if success:
            await self.refresh_user_group(inviter_id)
            return True, "success"
        return False, "already_invited"

    async def get_referral_count(self, user_id: int) -> int:
        """Get referral count"""
        return await self.quota_manager.get_referral_count(user_id)

    async def record_contribution(self, user_id: int, file_path: str, file_type: str):
        """Record template contribution in DB"""
        await self.quota_manager.add_template_contribution(user_id, file_path, file_type)

# Singleton instance
permission_service = PermissionService()
