import json
import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, delete, desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from dashboard.backend.schemas import (
    AdminGiftRequest,
    UpdateCreditsRequest,
    UpdateIdentityRequest,
    UpdateGroupRequest,
    UpdateChannelMemberRequest,
)
from src.database.core import get_db
from src.database.models import (
    CheckinHistory,
    GalleryComment,
    History,
    MembershipPlan,
    Order,
    Referral,
    TemplateContribution,
    GalleryPost,
    User,
    UserLog,
)
from src.services.affiliate_redeem_service import is_membership_settlement_v2_enabled
from src.services.membership_settlement_service import (
    MembershipSettlementAuditSource,
    settle_membership_plan_in_session,
)
from src.services.storage import storage

router = APIRouter(prefix="/api/users", tags=["users"])
logger = logging.getLogger("dashboard.users")


@router.get("")
async def get_users(
    skip: int = 0,
    limit: int = 20,
    query: str = None,
    query_partial: bool = True,
    identity: str = None,
    user_group: str = None,
    username: str = None,
    username_partial: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Get paginated user list with basic info"""
    try:
        stmt = select(User)

        if query:
            if query_partial:
                stmt = stmt.where(
                    (User.full_name.ilike(f"%{query}%"))
                    | (User.username.ilike(f"%{query}%"))
                )
            else:
                stmt = stmt.where((User.full_name == query) | (User.username == query))
        if identity:
            if identity == "外门弟子":
                stmt = stmt.where(
                    (User.current_identity == identity)
                    | (User.current_identity.is_(None))
                )
            else:
                stmt = stmt.where(User.current_identity == identity)
        if user_group:
            if user_group == "凡人":
                stmt = stmt.where(
                    (User.user_group == user_group) | (User.user_group.is_(None))
                )
            else:
                stmt = stmt.where(User.user_group == user_group)
        if username:
            if username_partial:
                stmt = stmt.where(User.username.ilike(f"%{username}%"))
            else:
                stmt = stmt.where(User.username == username)

        # Get total count
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_result = await db.execute(count_stmt)
        total = total_result.scalar() or 0

        # Get paginated data
        stmt = (
            stmt.options(selectinload(User.inviter_user))
            .order_by(desc(User.created_at))
            .offset(skip)
            .limit(limit)
        )

        result = await db.execute(stmt)
        users = result.scalars().all()

        users_basic_info = []
        for user in users:
            user_dict = {c.name: getattr(user, c.name) for c in user.__table__.columns}
            user_dict["referral_count"] = user.referral_count or 0
            user_dict["last_activity"] = user.last_activity
            user_dict["generation_count"] = user.generation_count or 0
            user_dict["checkin_count"] = user.checkin_count or 0
            user_dict["current_identity"] = user.current_identity or "外门弟子"
            user_dict["identity_expire_at"] = user.identity_expire_at
            user_dict["total_contributions"] = int(user.total_contributions or 0)
            user_dict["approved_contributions"] = int(user.approved_contributions or 0)
            user_dict["channel_joined"] = (
                bool(user.is_channel_member)
                if hasattr(user, "is_channel_member")
                else False
            )

            if user.inviter_user:
                user_dict["inviter_info"] = {
                    "id": user.inviter_user.id,
                    "username": user.inviter_user.username,
                    "full_name": user.inviter_user.full_name,
                }
            else:
                user_dict["inviter_info"] = None

            users_basic_info.append(user_dict)

        return {"items": users_basic_info, "total": total}
    except Exception as e:
        logger.error(f"Error getting users: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{user_id}/stats")
async def get_user_stats(user_id: int, db: AsyncSession = Depends(get_db)):
    """Get detailed heavy stats for a specific user"""
    try:
        # Recharge stats
        recharge_stmt = (
            select(
                func.sum(
                    case((Order.payment_channel == "RMB", Order.final_price), else_=0)
                ).label("total_recharge_rmb"),
                func.sum(
                    case(
                        (
                            Order.payment_channel == "TON",
                            Order.final_price,
                        ),
                        else_=0,
                    )
                ).label("total_recharge_ton"),
                func.sum(
                    case(
                        (
                            Order.payment_channel == "XTR",
                            Order.final_price,
                        ),
                        else_=0,
                    )
                ).label("total_recharge_stars"),
            )
            .where(Order.status == "SUCCESS")
            .where(Order.tx_hash.notlike("manual_%"))
            .where(Order.telegram_id == user_id)
        )
        recharge_result = await db.execute(recharge_stmt)
        row = recharge_result.one_or_none()

        stats = {
            "total_recharge_ton": float(row.total_recharge_ton or 0) if row else 0.0,
            "total_recharge_stars": int(row.total_recharge_stars or 0) if row else 0,
            "total_recharge_rmb": float(row.total_recharge_rmb or 0) if row else 0.0,
        }

        return stats
    except Exception as e:
        logger.error(f"Error getting user stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{user_id}")
async def delete_user(user_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a user and all their associated data from the database"""
    try:
        stmt = select(User).where(User.id == user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        await db.execute(
            delete(CheckinHistory).where(CheckinHistory.user_id == user_id)
        )
        await db.execute(delete(History).where(History.user_id == user_id))
        await db.execute(
            delete(Referral).where(
                (Referral.inviter_id == user_id) | (Referral.invitee_id == user_id)
            )
        )
        await db.execute(
            delete(TemplateContribution).where(TemplateContribution.user_id == user_id)
        )
        comment_count_rows = (
            await db.execute(
                select(
                    GalleryComment.post_id,
                    func.count(GalleryComment.id).label("deleted_count"),
                )
                .where(
                    GalleryComment.user_id == user_id,
                    GalleryComment.is_active.is_(True),
                )
                .group_by(GalleryComment.post_id)
            )
        ).all()
        await db.execute(delete(GalleryComment).where(GalleryComment.user_id == user_id))
        for post_id, deleted_count in comment_count_rows:
            if not post_id or not deleted_count:
                continue
            await db.execute(
                update(GalleryPost)
                .where(GalleryPost.id == post_id)
                .values(
                    comments_count=func.greatest(
                        GalleryPost.comments_count - deleted_count, 0
                    )
                )
            )
        await db.delete(user)

        await db.commit()
        return {
            "message": f"User {user_id} and all associated data deleted successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deleting user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{user_id}/credits")
async def update_user_credits(
    user_id: int, request: UpdateCreditsRequest, db: AsyncSession = Depends(get_db)
):
    """Update user credits and checkin count"""
    try:
        stmt = select(User).where(User.id == user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        old_credits = user.credits
        user.credits = request.credits
        credit_change = request.credits - old_credits

        if request.checkin_count is not None:
            user.checkin_count = request.checkin_count

        await db.commit()

        if credit_change != 0:
            from src.services.log_service import LogService

            await LogService.log_action(
                user_id=user_id,
                username=user.username or user.full_name,
                operation_type="admin_update",
                credit_change=credit_change,
                current_balance=user.credits,
                extra_info={"source": "dashboard_admin_edit"},
            )

        return {
            "status": "ok",
            "credits": user.credits,
            "checkin_count": user.checkin_count,
        }
    except Exception as e:
        logger.error(f"Error updating user data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{user_id}/history")
async def clear_user_history(user_id: int, db: AsyncSession = Depends(get_db)):
    """Clear user history (database records and files)"""
    try:
        stmt = select(History).where(History.user_id == user_id)
        result = await db.execute(stmt)
        history_records = result.scalars().all()

        for record in history_records:
            if record.input_file:
                for f in record.input_file.split("|"):
                    if f.startswith("template:"):
                        continue
                    try:
                        storage.client.remove_object("bot-data", f)
                    except Exception as fe:
                        logger.warning(f"Failed to delete input file {f}: {fe}")

            if record.output_file:
                if "/" not in record.output_file:
                    try:
                        storage.client.remove_object("comfyui-temp", record.output_file)
                    except Exception as fe:
                        logger.warning(
                            f"Failed to delete output file {record.output_file}: {fe}"
                        )
                else:
                    try:
                        storage.client.remove_object("bot-data", record.output_file)
                    except Exception as fe:
                        logger.warning(
                            f"Failed to delete output file {record.output_file}: {fe}"
                        )

        await db.execute(delete(History).where(History.user_id == user_id))

        user_stmt = select(User).where(User.id == user_id)
        user_res = await db.execute(user_stmt)
        user = user_res.scalar_one_or_none()
        if user:
            user.generation_count = 0
            user.last_activity = None

        await db.commit()

        return {"status": "ok", "message": f"Cleared history for user {user_id}"}
    except Exception as e:
        logger.error(f"Error clearing history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{user_id}/gift")
async def admin_gift_plan(
    user_id: int, request: AdminGiftRequest, db: AsyncSession = Depends(get_db)
):
    """Manually gift a membership plan to a user"""
    try:
        stmt = select(User).where(User.id == user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        plan_stmt = select(MembershipPlan).where(MembershipPlan.id == request.plan_id)
        plan_result = await db.execute(plan_stmt)
        plan = plan_result.scalar_one_or_none()
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")

        order_id = f"GIFT:{user_id}:{plan.id}:{int(datetime.now().timestamp())}"
        tx_hash = f"manual_{uuid.uuid4().hex[:16]}"

        new_order = Order(
            order_id=order_id,
            telegram_id=user_id,
            plan_id=plan.id,
            original_price=0,
            final_price=0,
            status="SUCCESS",
            tx_hash=tx_hash,
            paid_at=datetime.now(),
        )
        db.add(new_order)
        if is_membership_settlement_v2_enabled():
            await db.flush()
            await settle_membership_plan_in_session(
                locked_user=user,
                plan=plan,
                audit_source=MembershipSettlementAuditSource(
                    source="admin_gift_plan",
                    source_channel="ADMIN_GIFT",
                    source_order_id=order_id,
                    source_tx_hash=tx_hash,
                ),
                session=db,
                now=datetime.now(),
                grant_reward_credits=True,
            )
        else:
            from src.core.billing_core import calculate_identity_conversion

            final_identity, new_expire_at = calculate_identity_conversion(
                current_identity=user.current_identity,
                current_expire_at=user.identity_expire_at,
                new_identity=plan.identity_name,
                duration_days=plan.duration_days,
            )
            user.credits += plan.reward_credits
            user.current_identity = final_identity
            user.identity_expire_at = new_expire_at

            extra_info = {
                "order_id": order_id,
                "plan_name": plan.name,
                "note": request.note,
                "is_gift": True,
            }
            log_entry = UserLog(
                user_id=user.id,
                username=user.username,
                operation_type="recharge",
                credit_change=plan.reward_credits,
                current_balance=user.credits,
                extra_info=json.dumps(extra_info, ensure_ascii=False),
            )
            db.add(log_entry)

        await db.commit()

        return {
            "status": "ok",
            "message": f"Successfully gifted plan {plan.name} to user {user.id}",
            "new_credits": user.credits,
            "new_identity": user.current_identity,
        }
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error gifting plan: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{user_id}/identity")
async def update_user_identity(
    user_id: int, request: UpdateIdentityRequest, db: AsyncSession = Depends(get_db)
):
    """Update user identity and expiration date with optional value conversion"""
    try:
        stmt = select(User).where(User.id == user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        old_identity = user.current_identity
        old_expire = user.identity_expire_at
        new_expire = request.expire_at

        # 自动折算逻辑
        if (
            request.convert
            and not request.expire_at
            and old_expire
            and old_expire > datetime.now()
            and old_identity != request.identity
        ):
            from src.core.billing_core import calculate_identity_manual_conversion

            new_expire = calculate_identity_manual_conversion(
                current_identity=old_identity,
                current_expire_at=old_expire,
                new_identity=request.identity,
            )
            logger.info(
                f"Admin manual convert for user {user_id}: {old_identity} -> {request.identity}"
            )

        user.current_identity = request.identity
        if new_expire:
            user.identity_expire_at = new_expire

        await db.commit()

        # Log the identity change
        from src.services.log_service import LogService

        await LogService.log_action(
            user_id=user_id,
            username=user.username or user.full_name,
            operation_type="admin_update_identity",
            credit_change=0,
            current_balance=user.credits,
            extra_info={
                "old_identity": old_identity,
                "new_identity": user.current_identity,
                "old_expire": str(old_expire) if old_expire else None,
                "new_expire": str(user.identity_expire_at)
                if user.identity_expire_at
                else None,
                "converted": request.convert,
                "source": "dashboard_admin_edit",
            },
        )

        return {
            "status": "ok",
            "id": user.id,
            "current_identity": user.current_identity,
            "identity_expire_at": user.identity_expire_at,
        }
    except Exception as e:
        logger.error(f"Error updating user identity: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{user_id}/group")
async def update_user_group(
    user_id: int, request: UpdateGroupRequest, db: AsyncSession = Depends(get_db)
):
    """Update user group (修为)"""
    try:
        stmt = select(User).where(User.id == user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        old_group = user.user_group
        user.user_group = request.user_group

        await db.commit()

        # Log the group change
        from src.services.log_service import LogService

        await LogService.log_action(
            user_id=user_id,
            username=user.username or user.full_name,
            operation_type="admin_update_group",
            credit_change=0,
            current_balance=user.credits,
            extra_info={
                "old_group": old_group,
                "new_group": user.user_group,
                "source": "dashboard_admin_edit",
            },
        )

        return {"status": "ok", "id": user.id, "user_group": user.user_group}
    except Exception as e:
        logger.error(f"Error updating user group: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{user_id}/channel_member")
async def update_user_channel_member(
    user_id: int,
    request: UpdateChannelMemberRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update user channel member status (已入宗门)"""
    try:
        stmt = select(User).where(User.id == user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        old_status = user.is_channel_member
        user.is_channel_member = request.is_channel_member

        await db.commit()

        # Log the change
        from src.services.log_service import LogService

        await LogService.log_action(
            user_id=user_id,
            username=user.username or user.full_name,
            operation_type="admin_update_channel_member",
            credit_change=0,
            current_balance=user.credits,
            extra_info={
                "old_status": old_status,
                "new_status": user.is_channel_member,
                "source": "dashboard_admin_edit",
            },
        )

        # 新增逻辑：如果是从 False 改为 True，则联动触发奖励和修为刷新
        if request.is_channel_member and not old_status:
            from src.services.permission_service import permission_service

            # 尝试发放邀请奖励
            await permission_service.check_channel_reward(
                tg_id=user.telegram_id or user.id,
                username=user.username,
                full_name=user.full_name,
                internal_user_id=user.id,
            )
            # 刷新修为境界（凡人 -> 练气期）
            await permission_service.refresh_user_group(user.id, is_member=True)

        return {
            "status": "ok",
            "id": user.id,
            "is_channel_member": user.is_channel_member,
        }
    except Exception as e:
        logger.error(f"Error updating user channel member status: {e}")
        raise HTTPException(status_code=500, detail=str(e))
