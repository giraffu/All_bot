from datetime import datetime
from sqlalchemy import select, update, func
from .database.core import AsyncSessionLocal
from .database.models import User, Referral, TemplateContribution, CheckinHistory, UserLog
from .services.log_service import LogService
from .constants import GENERATION_TASK_TYPES

from sqlalchemy.exc import IntegrityError

class QuotaManager:
    def __init__(self):
        pass

    async def get_daily_usage(self, user_id: int) -> int:
        """Get number of generation tasks performed by user today"""
        async with AsyncSessionLocal() as session:
            from datetime import timezone, timedelta
            beijing_tz = timezone(timedelta(hours=8))
            today = datetime.now(beijing_tz).date()
            # Convert date to datetime for comparison if needed, but SQLAlchemy handles date comparison usually.
            # However, UserLog.created_at is DateTime. So we should compare >= today midnight.
            today_start = datetime.combine(today, datetime.min.time())
            
            stmt = select(func.count(UserLog.id)).where(
                UserLog.user_id == user_id,
                UserLog.operation_type.in_(GENERATION_TASK_TYPES),
                UserLog.created_at >= today_start
            )
            result = await session.execute(stmt)
            return result.scalar() or 0

    async def is_user_exists(self, user_id: int) -> bool:
        """Check if user exists without creating"""
        async with AsyncSessionLocal() as session:
            stmt = select(User).where(User.id == user_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none() is not None

    async def ensure_user(self, user_id: int, username: str = None, full_name: str = None) -> User:
        """Ensure user exists and update their info"""
        async with AsyncSessionLocal() as session:
            stmt = select(User).where(User.id == user_id)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()
            
            if not user:
                user = User(id=user_id, username=username, full_name=full_name, credits=6)
                session.add(user)
                try:
                    await session.commit()
                except IntegrityError:
                    await session.rollback()
                    # User was created concurrently, fetch it
                    stmt = select(User).where(User.id == user_id)
                    result = await session.execute(stmt)
                    user = result.scalar_one_or_none()
                return user
            
            # Update info if provided
            updated = False
            if username and user.username != username:
                user.username = username
                updated = True
            if full_name and user.full_name != full_name:
                user.full_name = full_name
                updated = True
            
            if updated:
                await session.commit()
            
            return user

    async def get_credits(self, user_id: int, username: str = None, full_name: str = None) -> int:
        """Get user credits. Initialize with 6 if new user."""
        user = await self.ensure_user(user_id, username, full_name)
        return user.credits

    async def check_credits(self, user_id: int, cost: int) -> bool:
        """Check if user has enough credits"""
        current = await self.get_credits(user_id)
        return current >= cost

    async def deduct_credits(self, user_id: int, cost: int, username: str = None, task_type: str = "generation"):
        """Deduct credits from user"""
        async with AsyncSessionLocal() as session:
            # We fetch again to ensure atomic update in transaction (though logic here is simplified)
            # Better: UPDATE users SET credits = credits - cost WHERE id = user_id AND credits >= cost
            # But for now, let's keep it simple.
            stmt = select(User).where(User.id == user_id)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()
            
            if user:
                old_balance = user.credits
                
                if cost < 0:
                    # If cost is negative, it's a refund or addition. Refund to permanent credits to be safe.
                    user.credits = user.credits - cost # -cost is positive
                else:
                    # Deduct from credits
                    user.credits = max(0, user.credits - cost)
                
                new_balance = user.credits
                await session.commit()

                # Log action
                if cost != 0:
                    await LogService.log_action(
                        user_id=user_id,
                        username=username or user.username,
                        operation_type=task_type,
                        credit_change=-cost,
                        current_balance=new_balance,
                        extra_info={"old_balance": old_balance}
                    )

    async def checkin(self, user_id: int, username: str = None, full_name: str = None, reward: int = 10) -> bool:
        """
        Perform daily check-in.
        Returns True if successful, False if already checked in today.
        """
        async with AsyncSessionLocal() as session:
            # We use ensure_user but inside this session to be atomic-ish
            stmt = select(User).where(User.id == user_id).with_for_update()
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()
            
            if not user:
                user = User(id=user_id, username=username, full_name=full_name, credits=6)
                session.add(user)
            else:
                # Update info
                if username:
                    user.username = username
                if full_name:
                    user.full_name = full_name
            
            from datetime import timezone, timedelta
            beijing_tz = timezone(timedelta(hours=8))
            today = datetime.now(beijing_tz).date()
            if user.last_checkin == today:
                await session.commit() # Save potential info updates
                return False
            
            user.last_checkin = today
            user.credits += reward
            user.checkin_count = (user.checkin_count or 0) + 1
            user.last_activity = datetime.now()

            # Record checkin history
            checkin_record = CheckinHistory(user_id=user_id, checkin_date=today)
            session.add(checkin_record)

            new_balance = user.credits
            await session.commit()
            
            await LogService.log_action(
                user_id=user_id,
                username=username or user.username,
                operation_type="checkin",
                credit_change=reward,
                current_balance=new_balance,
                extra_info={"checkin_date": today.isoformat(), "reward": reward}
            )
            return True



    async def get_referral_count(self, user_id: int) -> int:
        """Get number of users invited by user_id"""
        async with AsyncSessionLocal() as session:
            # Count referrals where inviter_id == user_id
            # Wait, sqlalchemy func.count
            from sqlalchemy import func
            stmt = select(func.count(Referral.id)).where(Referral.inviter_id == user_id)
            result = await session.execute(stmt)
            return result.scalar() or 0

    async def process_referral(self, inviter_id: int, new_user_id: int, new_username: str = None, new_full_name: str = None) -> bool:
        """
        Process a new referral.
        Returns True if successful (valid new user), False otherwise.
        """
        if inviter_id == new_user_id:
            return False

        async with AsyncSessionLocal() as session:
            # 1. Check if new_user already exists (has credits/record)
            stmt = select(User).where(User.id == new_user_id)
            result = await session.execute(stmt)
            if result.scalar_one_or_none():
                return False # Already exists
            
            # 2. Check if referral already exists (redundant if user check passes, but safe)
            stmt = select(Referral).where(Referral.invitee_id == new_user_id)
            result = await session.execute(stmt)
            if result.scalar_one_or_none():
                return False

            # 3. Create User (Invitee)
            new_user = User(id=new_user_id, username=new_username, full_name=new_full_name, credits=6, invited_by=inviter_id, last_activity=datetime.now())
            session.add(new_user)
            
            # 4. Create Referral
            # Ensure inviter exists and lock the row for update to prevent concurrent modification issues
            stmt = select(User).where(User.id == inviter_id).with_for_update()
            result = await session.execute(stmt)
            inviter = result.scalar_one_or_none()
            if not inviter:
                inviter = User(id=inviter_id, credits=6)
                session.add(inviter)
            
            referral = Referral(inviter_id=inviter_id, invitee_id=new_user_id, channel_reward_claimed=False)
            session.add(referral)
            
            # 5. Reward Inviter
            inviter.credits += 5
            inviter.referral_count = (inviter.referral_count or 0) + 1
            
            try:
                await session.commit()
                print(f"✅ Referral success: {inviter_id} invited {new_user_id}")
            except IntegrityError:
                await session.rollback()
                print(f"⚠️ Referral race condition: user {new_user_id} already exists")
                return False

            # Log for inviter
            await LogService.log_action(
                user_id=inviter_id,
                username=inviter.username,
                operation_type="referral_reward_initial",
                credit_change=5,
                current_balance=inviter.credits,
                extra_info={"invitee_id": new_user_id}
            )
            
            # Log for new user (welcome bonus)
            await LogService.log_action(
                user_id=new_user_id,
                username=new_username,
                operation_type="welcome_bonus",
                credit_change=6,
                current_balance=6,
                extra_info={"inviter_id": inviter_id}
            )
            return True

    async def process_channel_reward(self, user_id: int) -> int | None:
        """
        Check and award channel join reward (10 credits) to the inviter.
        Also marks the user as a channel member.
        Returns inviter_id if reward was given, None otherwise.
        """
        async with AsyncSessionLocal() as session:
            # Update user's channel membership status
            stmt = select(User).where(User.id == user_id)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()
            if user and not user.is_channel_member:
                user.is_channel_member = True
                await session.commit()
                # Re-fetch or continue with the same session? session is still open.

            # Find referral record
            stmt = select(Referral).where(Referral.invitee_id == user_id)
            result = await session.execute(stmt)
            referral = result.scalar_one_or_none()
            
            if not referral:
                return None
                
            if referral.channel_reward_claimed:
                return None
                
            # Award to inviter
            inviter_stmt = select(User).where(User.id == referral.inviter_id)
            inviter_res = await session.execute(inviter_stmt)
            inviter = inviter_res.scalar_one_or_none()
            
            if inviter:
                inviter.credits += 10
                referral.channel_reward_claimed = True
                await session.commit()
                print(f"✅ Channel reward success: {referral.inviter_id} for {user_id}")

                await LogService.log_action(
                    user_id=referral.inviter_id,
                    username=inviter.username,
                    operation_type="referral_reward_channel",
                    credit_change=10,
                    current_balance=inviter.credits,
                    extra_info={"invitee_id": user_id}
                )
                return referral.inviter_id
            
            return None

    async def update_channel_membership(self, user_id: int, is_member: bool):
        """Update user's channel membership status in DB"""
        async with AsyncSessionLocal() as session:
            stmt = update(User).where(User.id == user_id).values(is_channel_member=is_member)
            await session.execute(stmt)
            await session.commit()
            print(f"🔄 Updated channel membership for {user_id}: {is_member}")

    async def add_template_contribution(self, user_id: int, file_path: str, file_type: str = 'photo'):
        """Record a template contribution to DB"""
        async with AsyncSessionLocal() as session:
            contribution = TemplateContribution(user_id=user_id, file_path=file_path, file_type=file_type)
            session.add(contribution)
            
            # Increment user's total contributions count
            user_stmt = select(User).where(User.id == user_id)
            user_result = await session.execute(user_stmt)
            user = user_result.scalar_one_or_none()
            if user:
                user.total_contributions = (user.total_contributions or 0) + 1
                user.last_activity = datetime.now()
                
            await session.commit()
            
            if user:
                await LogService.log_action(
                    user_id=user_id,
                    username=user.username,
                    operation_type="template_submission",
                    credit_change=0,
                    current_balance=user.credits,
                    extra_info={"file_path": file_path, "file_type": file_type}
                )

    async def get_user_stats(self, user_id: int) -> dict:
        """Get invitation, checkin and generation counts for a user"""
        async with AsyncSessionLocal() as session:
            stmt = select(User).where(User.id == user_id)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()
            
            if not user:
                return {
                    "invitation_count": 0,
                    "checkin_count": 0,
                    "generation_count": 0,
                    "is_channel_member": False,
                    "total_contributions": 0,
                    "approved_contributions": 0
                }

            return {
                "invitation_count": user.referral_count or 0,
                "checkin_count": user.checkin_count or 0,
                "generation_count": user.generation_count or 0,
                "is_channel_member": user.is_channel_member,
                "total_contributions": user.total_contributions or 0,
                "approved_contributions": user.approved_contributions or 0,
                "identity_expire_at": user.identity_expire_at
            }

    async def update_user_group(self, user_id: int, group_name: str):
        """Update user's group name in DB"""
        async with AsyncSessionLocal() as session:
            stmt = update(User).where(User.id == user_id).values(user_group=group_name)
            await session.execute(stmt)
            await session.commit()
