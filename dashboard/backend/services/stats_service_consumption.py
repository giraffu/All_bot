from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from dashboard.backend.services.stats_service_utils import date_key
from src.constants import GENERATION_TASK_TYPES, MODE_IMG2IMG_LORA, VIDEO_TASK_TYPES
from src.database.models import UserLog

GENERATION_CONSUMPTION_OPERATION_TYPES = tuple(
    dict.fromkeys(
        [
            *GENERATION_TASK_TYPES,
            *VIDEO_TASK_TYPES,
            MODE_IMG2IMG_LORA,
        ]
    )
)
REFUND_OPERATION_PATTERN = "refund%"


def build_generation_consumption_charge_filter():
    return and_(
        UserLog.credit_change < 0,
        UserLog.operation_type.in_(GENERATION_CONSUMPTION_OPERATION_TYPES),
    )


def build_generation_consumption_refund_filter():
    return and_(
        UserLog.credit_change > 0,
        UserLog.operation_type.like(REFUND_OPERATION_PATTERN),
    )


def build_generation_consumption_log_filter():
    return or_(
        build_generation_consumption_charge_filter(),
        build_generation_consumption_refund_filter(),
    )


def build_generation_consumption_value():
    return case(
        (build_generation_consumption_charge_filter(), -UserLog.credit_change),
        (build_generation_consumption_refund_filter(), -UserLog.credit_change),
        else_=0,
    )


def normalize_consumed_credit_total(value) -> int:
    return max(0, int(value or 0))


def build_consumed_credits_subquery():
    consumed_value = build_generation_consumption_value()
    return (
        select(UserLog.user_id, func.sum(consumed_value).label("consumed"))
        .where(build_generation_consumption_log_filter())
        .group_by(UserLog.user_id)
        .subquery()
    )


async def load_consumed_credit_total(
    db: AsyncSession,
    *,
    start_date: date | datetime | None = None,
    end_date: date | datetime | None = None,
) -> int:
    consumed_value = build_generation_consumption_value()
    stmt = (
        select(func.coalesce(func.sum(consumed_value), 0))
        .select_from(UserLog)
        .where(build_generation_consumption_log_filter())
    )
    if start_date is not None:
        stmt = stmt.where(UserLog.created_at >= start_date)
    if end_date is not None:
        stmt = stmt.where(UserLog.created_at < end_date)
    return normalize_consumed_credit_total((await db.execute(stmt)).scalar())


async def load_daily_consumed_credit_map(
    db: AsyncSession,
    *,
    start_date: date | datetime,
) -> dict[str, int]:
    consumed_value = build_generation_consumption_value()
    consumed_date = func.date(UserLog.created_at)
    stmt = (
        select(
            consumed_date.label("date"),
            func.coalesce(func.sum(consumed_value), 0).label("count"),
        )
        .select_from(UserLog)
        .where(
            build_generation_consumption_log_filter(),
            UserLog.created_at >= start_date,
        )
        .group_by(consumed_date)
        .order_by(consumed_date)
    )
    rows = await db.execute(stmt)
    return {
        date_key(row.date): normalize_consumed_credit_total(row.count)
        for row in rows
    }
