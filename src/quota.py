from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Optional

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .constants import GENERATION_TASK_TYPES
from .database.core import AsyncSessionLocal
from .database.models import (
    CheckinHistory,
    Referral,
    TemplateContribution,
    User,
    UserLog,
)
from .services.log_service import LogService
from src.core.exceptions import InsufficientCreditsError
from src.logger import logger


@dataclass(frozen=True)
class CreditChangeResult:
    old_balance: int
    new_balance: int
    username: str | None


@dataclass(frozen=True)
class CreditTransferResult:
    from_user: CreditChangeResult
    to_user: CreditChangeResult


AuditMode = Literal["auto", "skip"]


class QuotaManager:
    def __init__(self):
        pass

    async def get_daily_usage(self, user_id: int) -> int:
        """Get number of generation tasks performed by user today"""
        async with AsyncSessionLocal() as session:
            from datetime import timedelta, timezone

            beijing_tz = timezone(timedelta(hours=8))
            today = datetime.now(beijing_tz).date()
            # Convert date to datetime for comparison if needed, but SQLAlchemy handles date comparison usually.
            # However, UserLog.created_at is DateTime. So we should compare >= today midnight.
            today_start = datetime.combine(today, datetime.min.time())

            stmt = select(func.count(UserLog.id)).where(
                UserLog.user_id == user_id,
                UserLog.operation_type.in_(GENERATION_TASK_TYPES),
                UserLog.created_at >= today_start,
            )
            result = await session.execute(stmt)
            return result.scalar() or 0

    async def is_user_exists(self, telegram_id: int) -> bool:
        """Check if user exists without creating"""
        from sqlalchemy import or_

        async with AsyncSessionLocal() as session:
            stmt = select(User).where(
                or_(User.telegram_id == telegram_id, User.id == telegram_id)
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none() is not None

    async def ensure_user(
        self, internal_user_id: int, username: str = None, full_name: str = None
    ) -> User:
        """Ensure user exists by internal ID"""
        async with AsyncSessionLocal() as session:
            stmt = select(User).where(User.id == internal_user_id)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()
            if user:
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

    async def get_credits(
        self, user_id: int, username: str = None, full_name: str = None
    ) -> int:
        """Get user credits. Initialize with 6 if new user."""
        user = await self.ensure_user(user_id, username, full_name)
        return user.credits

    async def check_credits(self, user_id: int, cost: int) -> bool:
        """Check if user has enough credits"""
        current = await self.get_credits(user_id)
        return current >= cost

    async def _get_user_for_update(
        self, session: AsyncSession, user_id: int
    ) -> User | None:
        stmt = select(User).where(User.id == user_id).with_for_update()
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_users_for_update(
        self, session: AsyncSession, user_ids: list[int]
    ) -> dict[int, User]:
        if not user_ids:
            return {}
        stmt = (
            select(User)
            .where(User.id.in_(sorted(set(user_ids))))
            .order_by(User.id)
            .with_for_update()
        )
        result = await session.execute(stmt)
        return {user.id: user for user in result.scalars().all()}

    async def _apply_credit_delta(
        self, session: AsyncSession, user_id: int, credit_delta: int
    ) -> tuple[User, CreditChangeResult]:
        user = await self._get_user_for_update(session, user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")

        old_balance = int(user.credits or 0)
        if credit_delta < 0:
            required_credits = -credit_delta
            if old_balance < required_credits:
                raise InsufficientCreditsError(
                    current=old_balance, cost=required_credits
                )

        user.credits = old_balance + credit_delta
        user.last_activity = datetime.now()
        await session.flush()

        return user, CreditChangeResult(
            old_balance=old_balance,
            new_balance=int(user.credits or 0),
            username=user.username,
        )

    async def _log_credit_change(
        self,
        *,
        user_id: int,
        task_type: str,
        result: CreditChangeResult,
        username: str = None,
        extra_info: Optional[dict[str, Any]] = None,
        session: AsyncSession | None = None,
        audit_mode: AuditMode = "auto",
    ) -> None:
        if audit_mode == "skip":
            return

        credit_change = result.new_balance - result.old_balance
        if credit_change == 0:
            return

        log_extra = {"old_balance": result.old_balance}
        if extra_info:
            log_extra.update(extra_info)

        await LogService.log_action(
            user_id=user_id,
            username=username or result.username,
            operation_type=task_type,
            credit_change=credit_change,
            current_balance=result.new_balance,
            extra_info=log_extra,
            session=session,
        )

    async def adjust_credits(
        self,
        user_id: int,
        credit_delta: int,
        username: str = None,
        task_type: str = "generation",
        session: AsyncSession | None = None,
        extra_info: Optional[dict[str, Any]] = None,
        audit_mode: AuditMode = "auto",
    ) -> CreditChangeResult:
        """
        Atomically apply a credit delta.

        Positive values increase credits, negative values deduct credits.
        When a session is passed, the caller owns the surrounding transaction.
        """
        if session is not None:
            _, result = await self._apply_credit_delta(session, user_id, credit_delta)
            await self._log_credit_change(
                user_id=user_id,
                username=username,
                task_type=task_type,
                result=result,
                extra_info=extra_info,
                session=session,
                audit_mode=audit_mode,
            )
            return result

        async with AsyncSessionLocal() as managed_session:
            try:
                _, result = await self._apply_credit_delta(
                    managed_session, user_id, credit_delta
                )
                await self._log_credit_change(
                    user_id=user_id,
                    username=username,
                    task_type=task_type,
                    result=result,
                    extra_info=extra_info,
                    session=managed_session,
                    audit_mode=audit_mode,
                )
                await managed_session.commit()
            except Exception:
                await managed_session.rollback()
                raise
        return result

    async def deduct_credits(
        self,
        user_id: int,
        cost: int,
        username: str = None,
        task_type: str = "generation",
        session: AsyncSession | None = None,
        extra_info: Optional[dict[str, Any]] = None,
        audit_mode: AuditMode = "auto",
    ) -> CreditChangeResult:
        """Deduct credits from user with a locked, atomic balance check."""
        if cost < 0:
            raise ValueError("cost must be non-negative; refunds must use add_credits()")

        return await self.adjust_credits(
            user_id=user_id,
            credit_delta=-cost,
            username=username,
            task_type=task_type,
            session=session,
            extra_info=extra_info,
            audit_mode=audit_mode,
        )

    async def add_credits(
        self,
        user_id: int,
        credits: int,
        username: str = None,
        task_type: str = "credit_adjustment",
        session: AsyncSession | None = None,
        extra_info: Optional[dict[str, Any]] = None,
        audit_mode: AuditMode = "auto",
    ) -> CreditChangeResult:
        """Increase credits using the same transaction-safe primitive."""
        if credits < 0:
            raise ValueError("credits must be non-negative")

        return await self.adjust_credits(
            user_id=user_id,
            credit_delta=credits,
            username=username,
            task_type=task_type,
            session=session,
            extra_info=extra_info,
            audit_mode=audit_mode,
        )

    async def _transfer_credits_in_session(
        self,
        *,
        session: AsyncSession,
        from_user_id: int,
        to_user_id: int,
        amount: int,
        from_username: str = None,
        to_username: str = None,
        debit_task_type: str,
        credit_task_type: str,
        extra_info: Optional[dict[str, Any]] = None,
        audit_mode: AuditMode = "auto",
    ) -> CreditTransferResult:
        users = await self._get_users_for_update(
            session,
            [from_user_id, to_user_id],
        )
        from_user = users.get(from_user_id)
        to_user = users.get(to_user_id)
        if not from_user:
            raise ValueError(f"User {from_user_id} not found")
        if not to_user:
            raise ValueError(f"User {to_user_id} not found")

        from_old_balance = int(from_user.credits or 0)
        if from_old_balance < amount:
            raise InsufficientCreditsError(current=from_old_balance, cost=amount)

        to_old_balance = int(to_user.credits or 0)
        from_user.credits = from_old_balance - amount
        to_user.credits = to_old_balance + amount
        now = datetime.now()
        from_user.last_activity = now
        to_user.last_activity = now
        await session.flush()

        from_result = CreditChangeResult(
            old_balance=from_old_balance,
            new_balance=int(from_user.credits or 0),
            username=from_user.username,
        )
        to_result = CreditChangeResult(
            old_balance=to_old_balance,
            new_balance=int(to_user.credits or 0),
            username=to_user.username,
        )

        await self._log_credit_change(
            user_id=from_user_id,
            username=from_username,
            task_type=debit_task_type,
            result=from_result,
            extra_info=extra_info,
            session=session,
            audit_mode=audit_mode,
        )
        await self._log_credit_change(
            user_id=to_user_id,
            username=to_username,
            task_type=credit_task_type,
            result=to_result,
            extra_info=extra_info,
            session=session,
            audit_mode=audit_mode,
        )
        return CreditTransferResult(from_user=from_result, to_user=to_result)

    async def transfer_credits(
        self,
        *,
        from_user_id: int,
        to_user_id: int,
        amount: int,
        from_username: str = None,
        to_username: str = None,
        debit_task_type: str = "credit_transfer_out",
        credit_task_type: str = "credit_transfer_in",
        session: AsyncSession | None = None,
        extra_info: Optional[dict[str, Any]] = None,
        audit_mode: AuditMode = "auto",
    ) -> CreditTransferResult:
        """Atomically transfer credits between two users with audit logs."""
        if amount <= 0:
            raise ValueError("amount must be positive")
        if from_user_id == to_user_id:
            raise ValueError("from_user_id and to_user_id must be different")

        if session is not None:
            return await self._transfer_credits_in_session(
                session=session,
                from_user_id=from_user_id,
                to_user_id=to_user_id,
                amount=amount,
                from_username=from_username,
                to_username=to_username,
                debit_task_type=debit_task_type,
                credit_task_type=credit_task_type,
                extra_info=extra_info,
                audit_mode=audit_mode,
            )

        async with AsyncSessionLocal() as managed_session:
            try:
                result = await self._transfer_credits_in_session(
                    session=managed_session,
                    from_user_id=from_user_id,
                    to_user_id=to_user_id,
                    amount=amount,
                    from_username=from_username,
                    to_username=to_username,
                    debit_task_type=debit_task_type,
                    credit_task_type=credit_task_type,
                    extra_info=extra_info,
                    audit_mode=audit_mode,
                )
                await managed_session.commit()
            except Exception:
                await managed_session.rollback()
                raise
        return result

    async def checkin(
        self,
        user_id: int,
        username: str = None,
        full_name: str = None,
        reward: int = 10,
    ) -> bool:
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
                user = User(
                    id=user_id, username=username, full_name=full_name, credits=6
                )
                session.add(user)
            else:
                # Update info
                if username:
                    user.username = username
                if full_name:
                    user.full_name = full_name

            from datetime import timedelta, timezone

            beijing_tz = timezone(timedelta(hours=8))
            today = datetime.now(beijing_tz).date()
            if user.last_checkin == today:
                await session.commit()  # Save potential info updates
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
                extra_info={"checkin_date": today.isoformat(), "reward": reward},
            )
            return True

    async def get_referral_count(self, user_id: int) -> int:
        """Get number of users invited by user_id"""
        async with AsyncSessionLocal() as session:
            # Count referrals where inviter_id == user_id
            # Wait, sqlalchemy func.count
            stmt = select(func.count(Referral.id)).where(Referral.inviter_id == user_id)
            result = await session.execute(stmt)
            return result.scalar() or 0

    async def process_referral(
        self,
        inviter_id: int,
        new_user_id: int,
        new_username: str = None,
        _new_full_name: str = None,
    ) -> bool:
        """
        Process a new referral.
        Returns True if successful (valid new user), False otherwise.
        """
        if inviter_id == new_user_id:
            return False

        async with AsyncSessionLocal() as session:
            # 1. Check if referral already exists
            stmt = select(Referral).where(Referral.invitee_id == new_user_id)
            result = await session.execute(stmt)
            if result.scalar_one_or_none():
                return False  # Already invited

            # 2. Update Invitee (already created by user_core)
            stmt = select(User).where(User.id == new_user_id)
            result = await session.execute(stmt)
            new_user = result.scalar_one_or_none()
            if not new_user:
                return False

            # If the user already has history or generated images, they are not really "new"
            # But we can simplify by just checking if they have an inviter
            if new_user.invited_by is not None:
                return False

            new_user.invited_by = inviter_id

            # 3. Create Referral
            stmt = select(User).where(User.id == inviter_id).with_for_update()
            result = await session.execute(stmt)
            inviter = result.scalar_one_or_none()
            if not inviter:
                return False

            referral = Referral(
                inviter_id=inviter_id,
                invitee_id=new_user_id,
                channel_reward_claimed=False,
            )
            session.add(referral)

            # 4. Reward Inviter
            inviter.credits += 5
            inviter.referral_count = (inviter.referral_count or 0) + 1

            try:
                await session.commit()
                logger.info(f"✅ Referral success: {inviter_id} invited {new_user_id}")
            except IntegrityError:
                await session.rollback()
                logger.warning(
                    f"⚠️ Referral race condition: user {new_user_id} already invited"
                )
                return False

            # Log for inviter
            await LogService.log_action(
                user_id=inviter_id,
                username=inviter.username,
                operation_type="referral_reward_initial",
                credit_change=5,
                current_balance=inviter.credits,
                extra_info={"invitee_id": new_user_id},
            )

            # Log for new user (welcome bonus)
            await LogService.log_action(
                user_id=new_user_id,
                username=new_username,
                operation_type="welcome_bonus",
                credit_change=6,
                current_balance=6,
                extra_info={"inviter_id": inviter_id},
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
                logger.info(
                    f"✅ Channel reward success: {referral.inviter_id} for {user_id}"
                )

                await LogService.log_action(
                    user_id=referral.inviter_id,
                    username=inviter.username,
                    operation_type="referral_reward_channel",
                    credit_change=10,
                    current_balance=inviter.credits,
                    extra_info={"invitee_id": user_id},
                )
                return referral.inviter_id

            return None

    async def update_channel_membership(self, user_id: int, is_member: bool):
        """Update user's channel membership status in DB"""
        async with AsyncSessionLocal() as session:
            stmt = (
                update(User)
                .where(User.id == user_id)
                .values(is_channel_member=is_member)
            )
            await session.execute(stmt)
            await session.commit()
            logger.info(f"🔄 Updated channel membership for {user_id}: {is_member}")

    async def add_template_contribution(
        self, user_id: int, file_path: str, file_type: str = "photo"
    ):
        """Record a template contribution to DB"""
        async with AsyncSessionLocal() as session:
            contribution = TemplateContribution(
                user_id=user_id, file_path=file_path, file_type=file_type
            )
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
                    extra_info={"file_path": file_path, "file_type": file_type},
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
                    "approved_contributions": 0,
                }

            return {
                "invitation_count": user.referral_count or 0,
                "checkin_count": user.checkin_count or 0,
                "generation_count": user.generation_count or 0,
                "is_channel_member": user.is_channel_member,
                "total_contributions": user.total_contributions or 0,
                "approved_contributions": user.approved_contributions or 0,
                "identity_expire_at": user.identity_expire_at,
            }

    async def update_user_group(self, user_id: int, group_name: str):
        """Update user's group name in DB"""
        async with AsyncSessionLocal() as session:
            stmt = update(User).where(User.id == user_id).values(user_group=group_name)
            await session.execute(stmt)
            await session.commit()
