from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, delete
from sqlalchemy.orm import selectinload
import logging
import json
import uuid
import os
from datetime import datetime, timedelta
from typing import Optional
from src.database.core import get_db
from src.database.models import User, History, Referral, TemplateContribution, CheckinHistory, Order, UserLog, MembershipPlan
from dashboard.backend.schemas import UpdateCreditsRequest, AdminGiftRequest
from src.services.storage import storage

router = APIRouter(prefix="/api/users", tags=["users"])
logger = logging.getLogger("dashboard.users")

@router.get("")
async def get_users(skip: int = 0, limit: int = 10000, db: AsyncSession = Depends(get_db)):
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
            select(Order.telegram_id, func.sum(Order.final_price).label("total_recharge"))
            .where(Order.status == "SUCCESS")
            .group_by(Order.telegram_id)
        )
        recharge_result = await db.execute(recharge_stmt)
        recharge_dict = {row.telegram_id: float(row.total_recharge or 0) for row in recharge_result}
        
        users_with_counts = []
        
        for user in users:
            user_dict = {c.name: getattr(user, c.name) for c in user.__table__.columns}
            user_dict['temporary_ingot'] = getattr(user, 'temp_credits', 0)
            user_dict["referral_count"] = user.referral_count or 0
            user_dict["last_activity"] = user.last_activity
            user_dict["generation_count"] = user.generation_count or 0
            user_dict["checkin_count"] = user.checkin_count or 0
            user_dict["current_identity"] = user.current_identity or '外门弟子'
            user_dict["identity_expire_at"] = user.identity_expire_at
            user_dict["total_recharge"] = recharge_dict.get(user.id, 0.0)
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
    """Update user credits, temporary ingot and checkin count"""
    try:
        stmt = select(User).where(User.id == user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
            
        user.credits = request.credits
        if request.temporary_ingot is not None:
            user.temp_credits = request.temporary_ingot
            if hasattr(user, 'temporary_ingot'):
                user.temporary_ingot = request.temporary_ingot
        if request.checkin_count is not None:
            user.checkin_count = request.checkin_count
            
        await db.commit()
        return {
            "status": "ok", 
            "credits": user.credits, 
            "temporary_ingot": user.temp_credits,
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
        
        user.credits += plan.reward_credits
        user.current_identity = plan.identity_name
        user.is_first_charge = False
        
        if not user.identity_expire_at or user.identity_expire_at < datetime.now():
            user.identity_expire_at = datetime.now() + timedelta(days=plan.duration_days)
        else:
            user.identity_expire_at = user.identity_expire_at + timedelta(days=plan.duration_days)
            
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
