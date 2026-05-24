import logging
from typing import List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from dashboard.backend.schemas import (
    MembershipPlanCreate,
    MembershipPlanResponse,
    MembershipPlanUpdate,
    OrderListResponse,
)
from dashboard.backend.services.plan_admin_service import (
    create_membership_plan_payload,
    delete_membership_plan_payload,
    get_membership_plans_payload,
    get_orders_payload,
    update_membership_plan_payload,
)
from src.database.core import get_db

router = APIRouter(prefix="/api", tags=["plans"])
logger = logging.getLogger("dashboard.plans")


@router.get("/plans", response_model=List[MembershipPlanResponse])
async def get_membership_plans(db: AsyncSession = Depends(get_db)):
    """Get all membership plans"""
    return await get_membership_plans_payload(db=db, logger_override=logger)


@router.post("/plans", response_model=MembershipPlanResponse)
async def create_membership_plan(
    plan: MembershipPlanCreate, db: AsyncSession = Depends(get_db)
):
    """Create a new membership plan"""
    return await create_membership_plan_payload(plan=plan, db=db, logger_override=logger)


@router.put("/plans/{plan_id}", response_model=MembershipPlanResponse)
async def update_membership_plan(
    plan_id: int, plan_update: MembershipPlanUpdate, db: AsyncSession = Depends(get_db)
):
    """Update a membership plan"""
    return await update_membership_plan_payload(
        plan_id=plan_id,
        plan_update=plan_update,
        db=db,
        logger_override=logger,
    )


@router.delete("/plans/{plan_id}")
async def delete_membership_plan(plan_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a membership plan"""
    return await delete_membership_plan_payload(
        plan_id=plan_id,
        db=db,
        logger_override=logger,
    )


@router.get("/orders", response_model=OrderListResponse)
async def get_orders(
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    internal_user_id: Optional[int] = None,
    username: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Get orders with pagination and optional filters"""
    return await get_orders_payload(
        page=page,
        page_size=page_size,
        status=status,
        internal_user_id=internal_user_id,
        username=username,
        db=db,
        logger_override=logger,
    )
