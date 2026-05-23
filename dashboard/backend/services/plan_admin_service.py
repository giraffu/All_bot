import logging

from fastapi import HTTPException
from sqlalchemy import desc, func, select

from dashboard.backend.presenters.plan_admin_presenter import build_order_item_payload
from src.database.models import MembershipPlan, Order, User

logger = logging.getLogger("dashboard.plans")


async def get_membership_plans_payload(*, db, logger_override: logging.Logger | None = None):
    active_logger = logger_override or logger
    try:
        result = await db.execute(select(MembershipPlan).order_by(MembershipPlan.price_ton))
        return result.scalars().all()
    except Exception as exc:
        active_logger.error(f"Error getting plans: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


async def create_membership_plan_payload(*, plan, db, logger_override: logging.Logger | None = None):
    active_logger = logger_override or logger
    try:
        new_plan = MembershipPlan(**plan.dict())
        db.add(new_plan)
        await db.commit()
        await db.refresh(new_plan)
        return new_plan
    except Exception as exc:
        active_logger.error(f"Error creating plan: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


async def update_membership_plan_payload(
    *,
    plan_id: int,
    plan_update,
    db,
    logger_override: logging.Logger | None = None,
):
    active_logger = logger_override or logger
    try:
        result = await db.execute(select(MembershipPlan).where(MembershipPlan.id == plan_id))
        db_plan = result.scalar_one_or_none()
        if not db_plan:
            raise HTTPException(status_code=404, detail="Plan not found")

        for key, value in plan_update.dict(exclude_unset=True).items():
            setattr(db_plan, key, value)

        await db.commit()
        await db.refresh(db_plan)
        return db_plan
    except HTTPException:
        raise
    except Exception as exc:
        active_logger.error(f"Error updating plan: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


async def delete_membership_plan_payload(
    *,
    plan_id: int,
    db,
    logger_override: logging.Logger | None = None,
):
    active_logger = logger_override or logger
    try:
        result = await db.execute(select(MembershipPlan).where(MembershipPlan.id == plan_id))
        db_plan = result.scalar_one_or_none()
        if not db_plan:
            raise HTTPException(status_code=404, detail="Plan not found")

        await db.delete(db_plan)
        await db.commit()
        return {"status": "ok", "message": "Plan deleted"}
    except HTTPException:
        raise
    except Exception as exc:
        active_logger.error(f"Error deleting plan: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


async def get_orders_payload(
    *,
    page: int,
    page_size: int,
    status: str | None,
    telegram_id: int | None,
    username: str | None,
    db,
    logger_override: logging.Logger | None = None,
) -> dict:
    active_logger = logger_override or logger
    try:
        offset = (page - 1) * page_size
        stmt = (
            select(Order, User.username, MembershipPlan.name.label("plan_name"))
            .outerjoin(User, Order.telegram_id == User.id)
            .outerjoin(MembershipPlan, Order.plan_id == MembershipPlan.id)
            .order_by(desc(Order.created_at))
        )

        if status and status != "ALL":
            stmt = stmt.where(Order.status == status)
        if telegram_id:
            stmt = stmt.where(Order.telegram_id == telegram_id)
        if username:
            stmt = stmt.where(User.username.ilike(f"%{username}%"))

        total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
        result = await db.execute(stmt.offset(offset).limit(page_size))
        items = [
            build_order_item_payload(order=row[0], username=row[1], plan_name=row[2])
            for row in result
        ]
        return {"items": items, "total": total}
    except Exception as exc:
        active_logger.error(f"Error getting orders: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
