from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from typing import Optional, List
import logging
from src.database.core import get_db
from src.database.models import MembershipPlan, Order, User
from dashboard.backend.schemas import MembershipPlanResponse, MembershipPlanCreate, MembershipPlanUpdate, OrderListResponse

router = APIRouter(prefix="/api", tags=["plans"])
logger = logging.getLogger("dashboard.plans")

@router.get("/plans", response_model=List[MembershipPlanResponse])
async def get_membership_plans(db: AsyncSession = Depends(get_db)):
    """Get all membership plans"""
    try:
        stmt = select(MembershipPlan).order_by(MembershipPlan.price_ton)
        result = await db.execute(stmt)
        plans = result.scalars().all()
        return plans
    except Exception as e:
        logger.error(f"Error getting plans: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/plans", response_model=MembershipPlanResponse)
async def create_membership_plan(plan: MembershipPlanCreate, db: AsyncSession = Depends(get_db)):
    """Create a new membership plan"""
    try:
        new_plan = MembershipPlan(**plan.dict())
        db.add(new_plan)
        await db.commit()
        await db.refresh(new_plan)
        return new_plan
    except Exception as e:
        logger.error(f"Error creating plan: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/plans/{plan_id}", response_model=MembershipPlanResponse)
async def update_membership_plan(plan_id: int, plan_update: MembershipPlanUpdate, db: AsyncSession = Depends(get_db)):
    """Update a membership plan"""
    try:
        stmt = select(MembershipPlan).where(MembershipPlan.id == plan_id)
        result = await db.execute(stmt)
        db_plan = result.scalar_one_or_none()
        if not db_plan:
            raise HTTPException(status_code=404, detail="Plan not found")
        
        update_data = plan_update.dict(exclude_unset=True)
        for key, value in update_data.items():
            setattr(db_plan, key, value)
            
        await db.commit()
        await db.refresh(db_plan)
        return db_plan
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating plan: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/plans/{plan_id}")
async def delete_membership_plan(plan_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a membership plan"""
    try:
        stmt = select(MembershipPlan).where(MembershipPlan.id == plan_id)
        result = await db.execute(stmt)
        db_plan = result.scalar_one_or_none()
        if not db_plan:
            raise HTTPException(status_code=404, detail="Plan not found")
        
        await db.delete(db_plan)
        await db.commit()
        return {"status": "ok", "message": "Plan deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting plan: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/orders", response_model=OrderListResponse)
async def get_orders(
    page: int = 1, 
    page_size: int = 20, 
    status: Optional[str] = None,
    telegram_id: Optional[int] = None,
    username: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Get orders with pagination and optional filters"""
    try:
        offset = (page - 1) * page_size
        
        count_stmt = select(func.count(Order.id))
        if username:
            count_stmt = count_stmt.outerjoin(User, Order.telegram_id == User.id)
            
        stmt = (
            select(Order, User.username, MembershipPlan.name.label("plan_name"))
            .outerjoin(User, Order.telegram_id == User.id)
            .outerjoin(MembershipPlan, Order.plan_id == MembershipPlan.id)
            .order_by(desc(Order.created_at))
        )
        
        if status and status != "ALL":
            count_stmt = count_stmt.where(Order.status == status)
            stmt = stmt.where(Order.status == status)
            
        if telegram_id:
            count_stmt = count_stmt.where(Order.telegram_id == telegram_id)
            stmt = stmt.where(Order.telegram_id == telegram_id)
            
        if username:
            count_stmt = count_stmt.where(User.username.ilike(f"%{username}%"))
            stmt = stmt.where(User.username.ilike(f"%{username}%"))
            
        count_result = await db.execute(count_stmt)
        total = count_result.scalar() or 0

        
        stmt = stmt.offset(offset).limit(page_size)
        result = await db.execute(stmt)
        
        items = []
        for row in result:
            order = row[0]
            username = row[1]
            plan_name = row[2]
            
            order_dict = {c.name: getattr(order, c.name) for c in order.__table__.columns}
            order_dict["username"] = username
            order_dict["plan_name"] = plan_name
            items.append(order_dict)
            
        return {"items": items, "total": total}
    except Exception as e:
        logger.error(f"Error getting orders: {e}")
        raise HTTPException(status_code=500, detail=str(e))
