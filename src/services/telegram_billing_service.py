from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select

from src.database.core import AsyncSessionLocal
from src.database.models import Order, RMBPaymentReconciliationJob
from src.services.membership_plan_catalog import (
    build_visible_membership_plan_lookup_stmt,
    build_visible_membership_plans_stmt,
)
from src.services.order_v2_service import (
    build_order_settlement_snapshot,
    generate_business_order_id,
    get_order_public_id,
)
from src.services.rmb_payment_provider_service import ALIPAY_DIRECT


async def list_visible_membership_plans(*, is_rmb: bool, is_subscription: bool):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            build_visible_membership_plans_stmt(
                is_rmb=is_rmb,
                is_subscription=is_subscription,
            )
        )
        return result.scalars().all()


async def get_visible_membership_plan(plan_id: int):
    async with AsyncSessionLocal() as session:
        result = await session.execute(build_visible_membership_plan_lookup_stmt(plan_id))
        return result.scalar_one_or_none()


async def create_rmb_pending_order(
    *,
    internal_user_id: int,
    plan,
    out_trade_no: str,
    payment_provider: str,
):
    async with AsyncSessionLocal() as session:
        new_order = Order(
            order_id=out_trade_no,
            business_order_id=generate_business_order_id(),
            internal_user_id=internal_user_id,
            plan_id=plan.id,
            original_price=plan.price_rmb,
            final_price=plan.price_rmb,
            settlement_schema_version="order_plan_v1",
            settlement_snapshot=build_order_settlement_snapshot(plan),
            status="PENDING",
            payment_channel="RMB",
            payment_provider=payment_provider,
            tx_hash=out_trade_no,
        )
        session.add(new_order)
        await session.flush()
        session.add(
            RMBPaymentReconciliationJob(
                order_id=new_order.id,
                status="pending",
                next_attempt_at=datetime.now() + timedelta(seconds=60),
            )
        )
        await session.commit()
        return new_order, get_order_public_id(new_order)


async def fail_rmb_payment_creation(*, order_id: int) -> None:
    async with AsyncSessionLocal() as session:
        order = await session.get(Order, order_id)
        if (
            order is None
            or order.status != "PENDING"
            or order.payment_provider != ALIPAY_DIRECT
        ):
            return
        order.status = "FAILED"
        job_result = await session.execute(
            select(RMBPaymentReconciliationJob).where(
                RMBPaymentReconciliationJob.order_id == order.id
            )
        )
        job = job_result.scalar_one_or_none()
        if job is not None:
            job.status = "completed"
            job.last_outcome = "payment_url_creation_failed"
            job.completed_at = datetime.now()
        await session.commit()


async def create_stars_pending_order(
    *,
    internal_user_id: int,
    plan,
    payload: str,
):
    async with AsyncSessionLocal() as session:
        business_order_id = generate_business_order_id()
        pending_order = Order(
            order_id=payload[:64],
            business_order_id=business_order_id,
            internal_user_id=internal_user_id,
            plan_id=plan.id,
            original_price=plan.price_stars,
            final_price=plan.price_stars,
            settlement_schema_version="order_plan_v1",
            settlement_snapshot=build_order_settlement_snapshot(plan),
            status="PENDING",
            payment_channel="XTR",
            created_at=datetime.now(),
        )
        session.add(pending_order)
        await session.commit()
        return business_order_id
