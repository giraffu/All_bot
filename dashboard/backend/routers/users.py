from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, delete, case
from sqlalchemy.orm import selectinload
import logging
import json
import uuid
import os
from datetime import datetime, timedelta
from typing import Optional
from src.database.core import get_db
from src.database.models import User, History, Referral, TemplateContribution, CheckinHistory, Order, UserLog, MembershipPlan
from dashboard.backend.schemas import UpdateCreditsRequest, AdminGiftRequest, UpdateIdentityRequest
from src.services.storage import storage

router = APIRouter(prefix="/api/users", tags=["users"])
logger = logging.getLogger("dashboard.users")

@router.get("")
async def get_users(skip: int = 0, limit: int = 100000, db: AsyncSession = Depends(get_db)):
    """Get user list with referral counts"""
    try:
        stmt = (
            select(User)
            .options(selectinload(User.inviter_user))
            .order_by(desc(User.created_at))
            .offset(skip)
            .limit(limit)
        )

        result = await db.execute(stmt)
        users = result.scalars().all()
        
        recharge_stmt = (
            select(
                Order.telegram_id, 
                func.sum(case((Order.final_price < 50, Order.final_price), else_=0)).label("total_recharge_ton"),
                func.sum(case((Order.final_price >= 50, Order.final_price), else_=0)).label("total_recharge_stars")
            )
            .where(Order.status == "SUCCESS")
            .where(Order.tx_hash.notlike("manual_%"))
            .group_by(Order.telegram_id)
        )
        recharge_result = await db.execute(recharge_stmt)
        recharge_dict = {}
        for row in recharge_result:
            recharge_dict[row.telegram_id] = {
                "ton": float(row.total_recharge_ton or 0),
                "stars": int(row.total_recharge_stars or 0)
            }
        
        users_with_counts = []
        
        for user in users:
            user_dict = {c.name: getattr(user, c.name) for c in user.__table__.columns}
            user_dict['temporary_ingot'] = 0 # Deprecated, keep for frontend compatibility until frontend is updated
            user_dict["referral_count"] = user.referral_count or 0
            user_dict["last_activity"] = user.last_activity
            user_dict["generation_count"] = user.generation_count or 0
            user_dict["checkin_count"] = user.checkin_count or 0
            user_dict["current_identity"] = user.current_identity or '外门弟子'
            user_dict["identity_expire_at"] = user.identity_expire_at
            user_dict["total_recharge_ton"] = recharge_dict.get(user.id, {}).get("ton", 0.0)
            user_dict["total_recharge_stars"] = recharge_dict.get(user.id, {}).get("stars", 0)
            user_dict["total_contributions"] = int(user.total_contributions or 0)
            user_dict["approved_contributions"] = int(user.approved_contributions or 0)
            user_dict["channel_joined"] = bool(user.is_channel_member) if hasattr(user, "is_channel_member") else False
            
            if user.inviter_user:
                user_dict["inviter_info"] = {
                    "id": user.inviter_user.id,
                    "username": user.inviter_user.username,
                    "full_name": user.inviter_user.full_name
                }
            else:
                user_dict["inviter_info"] = None
                
            users_with_counts.append(user_dict)
            
        return users_with_counts
    except Exception as e:
        logger.error(f"Error getting users: {e}")
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
            
        await db.execute(delete(CheckinHistory).where(CheckinHistory.user_id == user_id))
        await db.execute(delete(History).where(History.user_id == user_id))
        await db.execute(delete(Referral).where((Referral.inviter_id == user_id) | (Referral.invitee_id == user_id)))
        await db.execute(delete(TemplateContribution).where(TemplateContribution.user_id == user_id))
        await db.delete(user)
        
        await db.commit()
        return {"message": f"User {user_id} and all associated data deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deleting user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{user_id}/credits")
async def update_user_credits(user_id: int, request: UpdateCreditsRequest, db: AsyncSession = Depends(get_db)):
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
                extra_info={"source": "dashboard_admin_edit"}
            )
            
        return {
            "status": "ok", 
            "credits": user.credits, 
            "temporary_ingot": 0,
            "checkin_count": user.checkin_count
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
                for f in record.input_file.split('|'):
                    basename = os.path.basename(f)
                    obj_name = f"{user_id}/input_images/{basename}"
                    try:
                        storage.client.remove_object("bot-data", obj_name)
                    except Exception as fe:
                        logger.warning(f"Failed to delete input file {obj_name}: {fe}")
            
            if record.output_file:
                basename = os.path.basename(record.output_file)
                obj_name = f"{user_id}/output_images/{basename}"
                try:
                    storage.client.remove_object("bot-data", obj_name)
                except Exception as fe:
                    logger.warning(f"Failed to delete output file {obj_name}: {fe}")
        
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
async def admin_gift_plan(user_id: int, request: AdminGiftRequest, db: AsyncSession = Depends(get_db)):
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
            tx_hash=tx_hash
        )
        db.add(new_order)
        
        # 身份和有效期逻辑 (与自主充值保持一致)
        now = datetime.now()
        new_expire_at = user.identity_expire_at
        final_identity = plan.identity_name
        
        identity_priority = {
            "外门弟子": 0,
            "内门弟子": 1,
            "核心弟子": 2,
            "真传弟子": 3
        }
        identity_ratio = {
            "外门弟子": 1,
            "内门弟子": 2,
            "核心弟子": 5,
            "真传弟子": 10
        }
        
        current_priority = identity_priority.get(user.current_identity, 0)
        new_priority = identity_priority.get(plan.identity_name, 0)
        
        if new_expire_at and new_expire_at > now:
            if user.current_identity == plan.identity_name:
                # 同套餐续费
                new_expire_at += timedelta(days=plan.duration_days)
            elif new_priority > current_priority:
                # 升级：将旧身份残值折算为新身份天数
                import math
                remaining_days = (new_expire_at - now).total_seconds() / 86400.0
                old_ratio = identity_ratio.get(user.current_identity, 1)
                new_ratio = identity_ratio.get(plan.identity_name, 1)
                
                # 残值 = 剩余天数 * 旧比例，折算天数 = 残值 / 新比例
                converted_days = math.ceil((remaining_days * old_ratio) / new_ratio)
                new_expire_at = now + timedelta(days=plan.duration_days + converted_days)
            else:
                # 降级或同级：保留高等级身份，将新赠送的低等级套餐价值折算为高等级身份的天数
                final_identity = user.current_identity
                
                import math
                old_ratio = identity_ratio.get(user.current_identity, 1)
                new_ratio = identity_ratio.get(plan.identity_name, 1)
                
                # 新购价值 = 新套餐天数 * 新比例，折算天数 = 新购价值 / 旧比例
                extra_days = math.ceil((plan.duration_days * new_ratio) / old_ratio)
                new_expire_at += timedelta(days=extra_days)
        else:
            # 身份已过期或首次充值
            new_expire_at = now + timedelta(days=plan.duration_days)
            
        # 更新用户信息
        user.credits += plan.reward_credits
        user.current_identity = final_identity
        user.identity_expire_at = new_expire_at
        user.is_first_charge = False
            
        extra_info = {
            "order_id": order_id,
            "plan_name": plan.name,
            "note": request.note,
            "is_gift": True
        }
        log_entry = UserLog(
            user_id=user.id,
            username=user.username,
            operation_type="recharge",
            credit_change=plan.reward_credits,
            current_balance=user.credits,
            extra_info=json.dumps(extra_info, ensure_ascii=False)
        )
        db.add(log_entry)
        
        await db.commit()
        
        return {
            "status": "ok", 
            "message": f"Successfully gifted plan {plan.name} to user {user.id}",
            "new_credits": user.credits,
            "new_identity": user.current_identity
        }
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error gifting plan: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{user_id}/identity")
async def update_user_identity(user_id: int, request: UpdateIdentityRequest, db: AsyncSession = Depends(get_db)):
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
        if request.convert and not request.expire_at and old_expire and old_expire > datetime.now() and old_identity != request.identity:
            import math
            identity_ratio = {
                "外门弟子": 1,
                "内门弟子": 2,
                "核心弟子": 5,
                "真传弟子": 10
            }
            
            now = datetime.now()
            remaining_days = (old_expire - now).total_seconds() / 86400.0
            
            old_ratio = identity_ratio.get(old_identity, 1)
            new_ratio = identity_ratio.get(request.identity, 1)
            
            # 残值 = 剩余天数 * 旧比例，折算天数 = 残值 / 新比例
            converted_days = math.ceil((remaining_days * old_ratio) / new_ratio)
            
            new_expire = now + timedelta(days=converted_days)
            logger.info(f"Admin manual convert for user {user_id}: {old_identity}({remaining_days:.2f}d) -> {request.identity}({converted_days}d)")

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
                "new_expire": str(user.identity_expire_at) if user.identity_expire_at else None,
                "converted": request.convert,
                "source": "dashboard_admin_edit"
            }
        )
            
        return {
            "status": "ok", 
            "id": user.id,
            "current_identity": user.current_identity,
            "identity_expire_at": user.identity_expire_at
        }
    except Exception as e:
        logger.error(f"Error updating user identity: {e}")
        raise HTTPException(status_code=500, detail=str(e))
