from __future__ import annotations

from datetime import date

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from dashboard.backend.services.stats_service_utils import (
    build_finance_hourly_distribution,
    build_hourly_distribution,
    day_bounds,
    get_hour_expr,
    trailing_start_date,
)
from src.database.models import History, MembershipPlan, Order


async def load_finance_hourly_stats_impl(*, db: AsyncSession, target_date: date) -> dict:
    start_date, end_date = day_bounds(target_date)
    dialect = db.bind.dialect.name
    order_paid_expr = func.coalesce(Order.paid_at, Order.created_at)
    hour_expr = get_hour_expr(order_paid_expr, dialect)
    order_stmt = (
        select(
            hour_expr.label("hour"),
            func.coalesce(func.sum(MembershipPlan.reward_credits), 0).label("recharged_credits"),
            func.coalesce(
                func.sum(case((MembershipPlan.identity_name.like("%内门%"), 1), else_=0)),
                0,
            ).label("inner_disciples"),
            func.coalesce(
                func.sum(case((MembershipPlan.identity_name.like("%核心%"), 1), else_=0)),
                0,
            ).label("core_disciples"),
            func.coalesce(
                func.sum(case((MembershipPlan.identity_name.like("%真传%"), 1), else_=0)),
                0,
            ).label("true_disciples"),
        )
        .join(MembershipPlan, Order.plan_id == MembershipPlan.id)
        .where(
            Order.status == "SUCCESS",
            order_paid_expr >= start_date,
            order_paid_expr < end_date,
        )
        .group_by(hour_expr)
    )
    rows = await db.execute(order_stmt)
    return build_finance_hourly_distribution(rows)


async def load_cumulative_finance_hourly_stats_impl(*, db: AsyncSession, days: int) -> dict:
    start_date = trailing_start_date(days)
    dialect = db.bind.dialect.name
    order_paid_expr = func.coalesce(Order.paid_at, Order.created_at)
    hour_expr = get_hour_expr(order_paid_expr, dialect)
    order_stmt = (
        select(
            hour_expr.label("hour"),
            func.coalesce(func.sum(MembershipPlan.reward_credits), 0).label("recharged_credits"),
            func.coalesce(
                func.sum(case((MembershipPlan.identity_name.like("%内门%"), 1), else_=0)),
                0,
            ).label("inner_disciples"),
            func.coalesce(
                func.sum(case((MembershipPlan.identity_name.like("%核心%"), 1), else_=0)),
                0,
            ).label("core_disciples"),
            func.coalesce(
                func.sum(case((MembershipPlan.identity_name.like("%真传%"), 1), else_=0)),
                0,
            ).label("true_disciples"),
        )
        .join(MembershipPlan, Order.plan_id == MembershipPlan.id)
        .where(Order.status == "SUCCESS", order_paid_expr >= start_date)
        .group_by(hour_expr)
    )
    rows = await db.execute(order_stmt)
    return build_finance_hourly_distribution(rows)


async def load_hourly_generation_stats_impl(
    *, db: AsyncSession, target_date: date
) -> dict[str, int]:
    start_date, end_date = day_bounds(target_date)
    dialect = db.bind.dialect.name
    hour_expr = get_hour_expr(History.created_at, dialect)
    hourly_stmt = (
        select(hour_expr.label("hour"), func.count().label("count"))
        .where(History.created_at >= start_date, History.created_at < end_date)
        .group_by(hour_expr)
        .order_by(hour_expr)
    )
    rows = await db.execute(hourly_stmt)
    return build_hourly_distribution(rows)


async def load_cumulative_hourly_generation_stats_impl(
    *, db: AsyncSession, days: int
) -> dict[str, int]:
    start_date = trailing_start_date(days)
    dialect = db.bind.dialect.name
    hour_expr = get_hour_expr(History.created_at, dialect)
    hourly_stmt = (
        select(hour_expr.label("hour"), func.count().label("count"))
        .where(History.created_at >= start_date)
        .group_by(hour_expr)
        .order_by(hour_expr)
    )
    rows = await db.execute(hourly_stmt)
    return build_hourly_distribution(rows)


async def load_type_distribution_stats_impl(
    *, db: AsyncSession, target_date: date
) -> dict[str, int]:
    start_date, end_date = day_bounds(target_date)
    rows = await db.execute(
        select(History.type, func.count().label("count"))
        .where(History.created_at >= start_date, History.created_at < end_date)
        .group_by(History.type)
    )
    return {row.type or "unknown": row.count for row in rows}


async def load_cumulative_type_distribution_stats_impl(
    *, db: AsyncSession, days: int
) -> dict[str, int]:
    start_date = trailing_start_date(days)
    rows = await db.execute(
        select(History.type, func.count().label("count"))
        .where(History.created_at >= start_date)
        .group_by(History.type)
    )
    return {row.type or "unknown": row.count for row in rows}
