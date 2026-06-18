from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from sqlalchemy import and_, or_, select

from src.database.models import Order, User


@dataclass(frozen=True)
class PaidGroupEligibilityDecision:
    eligible: bool
    reason: str
    telegram_id: int
    internal_user_id: int | None = None
    matched_order_id: int | None = None


def _eligible_order_condition(internal_user_id_column):
    return and_(
        Order.internal_user_id == internal_user_id_column,
        Order.status == "SUCCESS",
        or_(
            Order.paid_at.is_not(None),
            Order.tx_hash.like("manual\\_%", escape="\\"),
            Order.order_id.like("GIFT:%"),
        ),
    )


def build_paid_group_eligibility_stmt(telegram_id: int):
    matched_order_id = (
        select(Order.id)
        .where(_eligible_order_condition(User.id))
        .order_by(Order.created_at.desc(), Order.id.desc())
        .limit(1)
        .scalar_subquery()
    )

    return (
        select(
            User.id.label("internal_user_id"),
            User.telegram_id.label("telegram_id"),
            matched_order_id.label("matched_order_id"),
        )
        .where(User.telegram_id == int(telegram_id))
        .limit(1)
    )


def _row_value(row, name: str):
    if hasattr(row, name):
        return getattr(row, name)
    mapping = getattr(row, "_mapping", None)
    if mapping is not None:
        return mapping.get(name)
    return None


async def check_paid_group_eligibility(
    telegram_id: int,
    *,
    session_factory: Callable | None = None,
) -> PaidGroupEligibilityDecision:
    if not telegram_id:
        return PaidGroupEligibilityDecision(
            eligible=False,
            reason="invalid_telegram_id",
            telegram_id=int(telegram_id or 0),
        )

    if session_factory is None:
        from src.database.core import AsyncSessionLocal

        session_factory = AsyncSessionLocal

    async with session_factory() as session:
        result = await session.execute(build_paid_group_eligibility_stmt(telegram_id))
        row = result.first()

    if row is None:
        return PaidGroupEligibilityDecision(
            eligible=False,
            reason="user_not_found",
            telegram_id=int(telegram_id),
        )

    internal_user_id = _row_value(row, "internal_user_id")
    matched_order_id = _row_value(row, "matched_order_id")

    if matched_order_id is None:
        return PaidGroupEligibilityDecision(
            eligible=False,
            reason="no_successful_paid_or_gift_order",
            telegram_id=int(telegram_id),
            internal_user_id=int(internal_user_id),
        )

    return PaidGroupEligibilityDecision(
        eligible=True,
        reason="matched_successful_paid_or_gift_order",
        telegram_id=int(telegram_id),
        internal_user_id=int(internal_user_id),
        matched_order_id=int(matched_order_id),
    )

