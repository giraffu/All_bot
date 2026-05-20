import argparse
import asyncio
import logging
import sys
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from typing import Literal

from sqlalchemy import String, and_, cast, literal, or_, select


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.affiliate_core import (  # noqa: E402
    invalidate_invitation_recharge_cache,
    record_affiliate_commission_transaction,
)
from src.database.core import AsyncSessionLocal  # noqa: E402
from src.database.models import AffiliateTransaction, Order, Referral  # noqa: E402

CandidateStatus = Literal["should_insert", "already_exists", "missing_referral"]
logger = logging.getLogger(__name__)


@dataclass
class BackfillCandidate:
    order_pk: int
    order_id: str
    invitee_user_id: int
    inviter_id: int | None
    referral_id: int | None
    commission_usdt: Decimal
    status: CandidateStatus


@dataclass
class BackfillSummary:
    mode: Literal["dry-run", "apply"]
    candidate_orders: int
    should_insert: int
    already_exists: int
    missing_referral: int
    error: int
    inserted: int
    skipped_during_apply: int
    inviter_count: int
    amount_total: Decimal

    def to_dict(self) -> dict:
        payload = asdict(self)
        if self.mode == "dry-run":
            payload.pop("inserted", None)
            payload.pop("skipped_during_apply", None)
        payload["amount_total"] = float(self.amount_total)
        return payload


def _classify_candidate(
    order: Order,
    referral: Referral | None,
    has_existing_transaction: bool,
) -> BackfillCandidate:
    if referral is None:
        status: CandidateStatus = "missing_referral"
    elif has_existing_transaction:
        status = "already_exists"
    else:
        status = "should_insert"

    return BackfillCandidate(
        order_pk=order.id,
        order_id=str(order.order_id or ""),
        invitee_user_id=order.telegram_id,
        inviter_id=referral.inviter_id if referral else None,
        referral_id=referral.id if referral else None,
        commission_usdt=Decimal(str(order.commission_usdt or 0)),
        status=status,
    )


def _affiliate_commission_reference_predicate(order_id_expr):
    return and_(
        AffiliateTransaction.reference_type == "ORDER",
        AffiliateTransaction.reference_id == cast(order_id_expr, String),
        AffiliateTransaction.direction == "IN",
        AffiliateTransaction.transaction_type == "COMMISSION_ACCRUAL",
    )


def _affiliate_commission_exists_expr(order_id_expr):
    idempotency_key_expr = literal("affiliate:commission:order:") + cast(
        order_id_expr, String
    )
    return or_(
        AffiliateTransaction.idempotency_key == idempotency_key_expr,
        _affiliate_commission_reference_predicate(order_id_expr),
    )


def _is_backfill_replayable_order(order: Order) -> bool:
    return (
        order.status == "SUCCESS"
        and Decimal(str(order.commission_usdt or 0)) > 0
    )


async def _affiliate_commission_exists_for_order(session, order_pk: int) -> bool:
    existing_tx_id = (
        await session.execute(
            select(AffiliateTransaction.id)
            .where(_affiliate_commission_exists_expr(literal(order_pk)))
            .limit(1)
        )
    ).scalar_one_or_none()
    return existing_tx_id is not None


async def collect_backfill_candidates(
    session,
    *,
    user_id: int | None = None,
    order_pk: int | None = None,
    business_order_id: str | None = None,
    order_filter: str | None = None,
    limit: int | None = None,
) -> list[BackfillCandidate]:
    # Deprecated compatibility path: numeric --order-id is ambiguous, so fail closed.
    if order_filter is not None:
        if order_pk is not None or business_order_id is not None:
            raise ValueError(
                "order_filter cannot be combined with order_pk/business_order_id"
            )
        try:
            int(order_filter)
        except (TypeError, ValueError):
            business_order_id = order_filter
        else:
            raise ValueError(
                "numeric --order-id is ambiguous; use --order-pk or --business-order-id"
            )

    existing_transaction_id = (
        select(AffiliateTransaction.id)
        .where(_affiliate_commission_exists_expr(Order.id))
        .limit(1)
        .scalar_subquery()
    )
    stmt = (
        select(Order, Referral, existing_transaction_id)
        .outerjoin(Referral, Referral.invitee_id == Order.telegram_id)
        .where(
            Order.status == "SUCCESS",
            Order.commission_usdt > 0,
        )
        .order_by(Order.id.asc())
    )
    if user_id is not None:
        stmt = stmt.where(Referral.inviter_id == user_id)
    if order_pk is not None:
        stmt = stmt.where(Order.id == order_pk)
    if business_order_id is not None:
        stmt = stmt.where(
            or_(
                Order.business_order_id == business_order_id,
                Order.order_id == business_order_id,
            )
        )
    if limit is not None:
        stmt = stmt.limit(limit)

    rows = (await session.execute(stmt)).all()
    return [
        _classify_candidate(order, referral, existing_tx_id is not None)
        for order, referral, existing_tx_id in rows
    ]


def summarize_backfill_candidates(
    candidates: list[BackfillCandidate],
    *,
    mode: Literal["dry-run", "apply"],
    error_count: int = 0,
    inserted_count: int = 0,
    skipped_during_apply_count: int = 0,
) -> BackfillSummary:
    should_insert_candidates = [
        candidate for candidate in candidates if candidate.status == "should_insert"
    ]
    return BackfillSummary(
        mode=mode,
        candidate_orders=len(candidates),
        should_insert=len(should_insert_candidates),
        already_exists=sum(
            1 for candidate in candidates if candidate.status == "already_exists"
        ),
        missing_referral=sum(
            1 for candidate in candidates if candidate.status == "missing_referral"
        ),
        error=error_count,
        inserted=inserted_count,
        skipped_during_apply=skipped_during_apply_count,
        inviter_count=len(
            {
                candidate.inviter_id
                for candidate in should_insert_candidates
                if candidate.inviter_id is not None
            }
        ),
        amount_total=sum(
            (candidate.commission_usdt for candidate in should_insert_candidates),
            Decimal("0"),
        ),
    )


async def apply_backfill_candidate(session, candidate: BackfillCandidate) -> bool:
    if candidate.status != "should_insert" or candidate.referral_id is None:
        return False

    order = await session.get(Order, candidate.order_pk)
    referral = await session.get(Referral, candidate.referral_id)
    if order is None:
        raise ValueError(f"order not found: {candidate.order_pk}")
    if referral is None:
        raise ValueError(f"referral not found: {candidate.referral_id}")
    if not _is_backfill_replayable_order(order):
        return False
    if await _affiliate_commission_exists_for_order(session, order.id):
        return False

    return await record_affiliate_commission_transaction(
        session,
        order,
        referral,
        source="backfill_script",
    )


async def backfill_affiliate_transactions(
    *,
    apply: bool,
    user_id: int | None = None,
    order_pk: int | None = None,
    business_order_id: str | None = None,
    order_filter: str | None = None,
    limit: int | None = None,
) -> BackfillSummary:
    async with AsyncSessionLocal() as session:
        candidates = await collect_backfill_candidates(
            session,
            user_id=user_id,
            order_pk=order_pk,
            business_order_id=business_order_id,
            order_filter=order_filter,
            limit=limit,
        )

    if not apply:
        return summarize_backfill_candidates(candidates, mode="dry-run")

    error_count = 0
    inserted_count = 0
    skipped_during_apply_count = 0
    touched_inviter_ids: set[int] = set()
    for candidate in candidates:
        if candidate.status != "should_insert":
            continue
        try:
            async with AsyncSessionLocal() as session:
                inserted = await apply_backfill_candidate(session, candidate)
                await session.commit()
            if inserted:
                inserted_count += 1
            else:
                skipped_during_apply_count += 1
            if inserted and candidate.inviter_id is not None:
                touched_inviter_ids.add(candidate.inviter_id)
        except Exception:
            error_count += 1
            logger.exception(
                "backfill apply failed for order_pk=%s order_id=%s inviter_id=%s",
                candidate.order_pk,
                candidate.order_id,
                candidate.inviter_id,
            )

    for inviter_id in sorted(touched_inviter_ids):
        await invalidate_invitation_recharge_cache(inviter_id)

    return summarize_backfill_candidates(
        candidates,
        mode="apply",
        error_count=error_count,
        inserted_count=inserted_count,
        skipped_during_apply_count=skipped_during_apply_count,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill affiliate commission ledger transactions."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Only summarize changes.")
    mode.add_argument("--apply", action="store_true", help="Execute backfill writes.")
    parser.add_argument(
        "--user-id",
        type=int,
        help="Limit to a specific inviter user id.",
    )
    parser.add_argument(
        "--order-pk",
        type=int,
        help="Limit to a specific orders.id primary key.",
    )
    parser.add_argument(
        "--business-order-id",
        help="Limit to a specific business order_id.",
    )
    parser.add_argument(
        "--order-id",
        dest="order_filter",
        help="Deprecated: non-numeric business order_id only. Numeric values must use --order-pk.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit the number of candidate rows scanned.",
    )
    return parser.parse_args()


async def _main() -> None:
    args = parse_args()
    summary = await backfill_affiliate_transactions(
        apply=args.apply,
        user_id=args.user_id,
        order_pk=args.order_pk,
        business_order_id=args.business_order_id,
        order_filter=args.order_filter,
        limit=args.limit,
    )
    print(summary.to_dict())


if __name__ == "__main__":
    asyncio.run(_main())
