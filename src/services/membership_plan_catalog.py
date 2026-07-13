from sqlalchemy import select

from src.database.models import MembershipPlan
from src.domain_config.membership_plans import (
    CANONICAL_CREDIT_PLAN_IDS,
    CANONICAL_MEMBERSHIP_PLAN_IDS,
    CANONICAL_SUBSCRIPTION_PLAN_IDS,
)


def build_visible_membership_plans_stmt(*, is_rmb: bool, is_subscription: bool | None):
    if is_subscription is None:
        plan_ids = CANONICAL_MEMBERSHIP_PLAN_IDS
    else:
        plan_ids = (
            CANONICAL_SUBSCRIPTION_PLAN_IDS
            if is_subscription
            else CANONICAL_CREDIT_PLAN_IDS
        )
    stmt = select(MembershipPlan).where(
        MembershipPlan.is_active.is_(True),
        MembershipPlan.id.in_(plan_ids),
    )

    if is_subscription is True:
        stmt = stmt.where(MembershipPlan.duration_days > 0)
    elif is_subscription is False:
        stmt = stmt.where(MembershipPlan.duration_days == 0)

    if is_rmb:
        stmt = stmt.where(MembershipPlan.price_rmb > 0).order_by(
            MembershipPlan.price_rmb.asc()
        )
    else:
        stmt = stmt.where(MembershipPlan.price_stars > 0).order_by(
            MembershipPlan.price_stars.asc()
        )

    return stmt


def build_visible_membership_plan_lookup_stmt(plan_id: int):
    return select(MembershipPlan).where(
        MembershipPlan.id == plan_id,
        MembershipPlan.is_active.is_(True),
        MembershipPlan.id.in_(CANONICAL_MEMBERSHIP_PLAN_IDS),
    )
