import argparse
import asyncio
import hashlib
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from sqlalchemy import and_, case, func, select, update
from sqlalchemy.dialects.postgresql import insert


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.constants import COMMISSION_RATE  # noqa: E402
from src.database.core import AsyncSessionLocal  # noqa: E402
from src.database.models import (  # noqa: E402
    AffiliateTransaction,
    MembershipPlan,
    Order,
    Referral,
    User,
)

MONEY_QUANT = Decimal("0.01")
COMMISSION_QUANT = Decimal("0.0001")
CHANNEL_RATE = {
    "RMB": Decimal("1") / Decimal("6.7"),
    "TON": Decimal("1.4"),
    "XTR": Decimal("0.013"),
}


@dataclass
class SeedSummary:
    inviter_user_id: int
    invitees_total: int
    referrals_created: int
    orders_created: int
    commission_records_inserted: int
    commission_amount_inserted_usdt: Decimal
    available_balance_usdt: Decimal


def _normalize_batch_tag(raw: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_]+", "_", raw.strip().lower())
    return cleaned[:24] if cleaned else "seed_batch"


def _deterministic_telegram_id(batch_tag: str, index: int) -> int:
    digest = hashlib.sha1(f"{batch_tag}:{index}".encode("utf-8")).hexdigest()
    # Place generated IDs in a high range to avoid normal user collisions.
    return 9_000_000_000 + (int(digest[:8], 16) % 900_000_000)


def _deterministic_tx_hash(batch_tag: str, index: int) -> str:
    digest = hashlib.sha1(f"tx:{batch_tag}:{index}".encode("utf-8")).hexdigest()
    return f"seedtx_{batch_tag}_{digest[:24]}"


async def _get_seed_plan(session, plan_id: int | None) -> MembershipPlan:
    if plan_id is not None:
        plan = await session.get(MembershipPlan, plan_id)
        if plan is None:
            raise ValueError(f"plan_id={plan_id} does not exist")
        return plan

    stmt = (
        select(MembershipPlan)
        .where(MembershipPlan.is_active.is_(True))
        .order_by(MembershipPlan.id.asc())
        .limit(1)
    )
    plan = (await session.execute(stmt)).scalar_one_or_none()
    if plan is not None:
        return plan

    inserted_plan_id = (
        await session.execute(
            insert(MembershipPlan)
            .values(
                name="测试返佣月卡",
                identity_name="内门弟子",
                price_ton=Decimal("9.90"),
                price_stars=990,
                price_rmb=Decimal("199.00"),
                reward_credits=1200,
                duration_days=30,
                is_active=True,
            )
            .returning(MembershipPlan.id)
        )
    ).scalar_one()
    plan = await session.get(MembershipPlan, inserted_plan_id)
    if plan is None:
        raise RuntimeError(f"failed to load inserted seed plan id={inserted_plan_id}")
    return plan


async def _get_or_create_invitee(
    session,
    *,
    inviter_id: int,
    batch_tag: str,
    index: int,
) -> tuple[User, bool]:
    username = f"seed_invitee_{batch_tag}_{index:03d}"
    telegram_id = _deterministic_telegram_id(batch_tag, index)

    existing = (
        await session.execute(
            select(User).where(
                (User.username == username) | (User.telegram_id == telegram_id)
            )
        )
    ).scalar_one_or_none()
    if existing:
        if existing.invited_by != inviter_id:
            await session.execute(
                update(User)
                .where(User.id == existing.id)
                .values(invited_by=inviter_id)
            )
            existing.invited_by = inviter_id
        return existing, False

    inserted_id = (
        await session.execute(
            insert(User)
            .values(
                telegram_id=telegram_id,
                username=username,
                full_name=f"Seed Invitee {index:03d}",
                language_code="zh-hans",
                credits=0,
                current_identity="外门弟子",
                invited_by=inviter_id,
                is_channel_member=True,
                created_at=datetime.now(),
            )
            .returning(User.id)
        )
    ).scalar_one()
    invitee = await session.get(User, inserted_id)
    if invitee is None:
        raise RuntimeError(f"failed to load inserted invitee user id={inserted_id}")
    return invitee, True


async def _ensure_referral(
    session,
    *,
    inviter_id: int,
    invitee_id: int,
) -> bool:
    existing = (
        await session.execute(
            select(Referral).where(Referral.invitee_id == invitee_id).with_for_update()
        )
    ).scalar_one_or_none()
    if existing:
        if existing.inviter_id != inviter_id:
            raise ValueError(
                f"invitee_id={invitee_id} already bound to inviter_id={existing.inviter_id}, "
                f"cannot rebind to inviter_id={inviter_id}"
            )
        return False

    session.add(Referral(inviter_id=inviter_id, invitee_id=invitee_id))
    await session.flush()
    return True


def _calculate_commission(final_price: Decimal, payment_channel: str) -> Decimal:
    rate = CHANNEL_RATE[payment_channel]
    return (final_price * rate * Decimal(str(COMMISSION_RATE))).quantize(
        COMMISSION_QUANT, rounding=ROUND_HALF_UP
    )


async def _get_or_create_paid_order(
    session,
    *,
    invitee: User,
    plan: MembershipPlan,
    payment_channel: str,
    final_price: Decimal,
    commission_usdt: Decimal,
    batch_tag: str,
    index: int,
) -> tuple[Order, bool]:
    order_id = f"SEED:{batch_tag}:{index:03d}"
    tx_hash = _deterministic_tx_hash(batch_tag, index)

    existing = (
        await session.execute(
            select(Order).where((Order.order_id == order_id) | (Order.tx_hash == tx_hash))
        )
    ).scalar_one_or_none()
    if existing:
        return existing, False

    inserted_order_id = (
        await session.execute(
            insert(Order)
            .values(
                order_id=order_id,
                internal_user_id=invitee.id,
                plan_id=plan.id,
                original_price=final_price,
                final_price=final_price,
                status="SUCCESS",
                tx_hash=tx_hash,
                commission_usdt=commission_usdt,
                payment_channel=payment_channel,
                paid_at=datetime.now(),
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
            .returning(Order.id)
        )
    ).scalar_one()
    order = await session.get(Order, inserted_order_id)
    if order is None:
        raise RuntimeError(f"failed to load inserted order id={inserted_order_id}")
    return order, True


async def _ensure_commission_transaction(
    session,
    *,
    inviter_id: int,
    invitee_id: int,
    order: Order,
    commission_usdt: Decimal,
    batch_tag: str,
) -> bool:
    stmt = insert(AffiliateTransaction).values(
        user_id=inviter_id,
        amount_usdt=commission_usdt,
        transaction_type="COMMISSION_ACCRUAL",
        direction="IN",
        reference_type="ORDER",
        reference_id=str(order.id),
        idempotency_key=f"affiliate:commission:order:{order.id}",
        status="SUCCESS",
        details={
            "order_pk": order.id,
            "order_id": str(order.order_id or ""),
            "tx_hash": order.tx_hash,
            "invitee_user_id": invitee_id,
            "inviter_id": inviter_id,
            "payment_channel": order.payment_channel,
            "commission_usdt": str(commission_usdt),
            "source": "seed_affiliate_test_data",
            "batch_tag": batch_tag,
        },
    )
    stmt = stmt.on_conflict_do_nothing(index_elements=["idempotency_key"]).returning(
        AffiliateTransaction.id
    )
    inserted_id = (await session.execute(stmt)).scalar_one_or_none()
    return inserted_id is not None


async def _query_available_balance(session, inviter_id: int) -> Decimal:
    stmt = select(
        func.coalesce(
            func.sum(
                case(
                    (
                        and_(
                            AffiliateTransaction.direction == "IN",
                            AffiliateTransaction.status == "SUCCESS",
                        ),
                        AffiliateTransaction.amount_usdt,
                    ),
                    (
                        and_(
                            AffiliateTransaction.direction == "OUT",
                            AffiliateTransaction.status == "SUCCESS",
                        ),
                        -AffiliateTransaction.amount_usdt,
                    ),
                    else_=0,
                )
            ),
            0,
        )
    ).where(AffiliateTransaction.user_id == inviter_id)
    balance = (await session.execute(stmt)).scalar_one()
    return Decimal(str(balance or 0)).quantize(COMMISSION_QUANT)


async def seed_affiliate_data(
    *,
    inviter_user_id: int,
    invitee_count: int,
    payment_channel: str,
    final_price: Decimal,
    batch_tag: str,
    plan_id: int | None,
) -> SeedSummary:
    if invitee_count <= 0:
        raise ValueError("invitee_count must be > 0")

    payment_channel = payment_channel.upper()
    if payment_channel not in CHANNEL_RATE:
        raise ValueError(f"unsupported payment_channel={payment_channel}")

    final_price = Decimal(str(final_price)).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
    if final_price <= 0:
        raise ValueError("final_price must be > 0")

    referrals_created = 0
    orders_created = 0
    commission_inserted = 0
    commission_amount_inserted_usdt = Decimal("0")

    async with AsyncSessionLocal() as session:
        inviter = await session.get(User, inviter_user_id)
        if inviter is None:
            raise ValueError(f"inviter_user_id={inviter_user_id} not found")

        plan = await _get_seed_plan(session, plan_id)
        commission_per_order = _calculate_commission(final_price, payment_channel)
        if commission_per_order <= 0:
            raise ValueError(
                f"calculated commission <= 0, final_price={final_price}, payment_channel={payment_channel}"
            )

        for idx in range(1, invitee_count + 1):
            invitee, _ = await _get_or_create_invitee(
                session,
                inviter_id=inviter_user_id,
                batch_tag=batch_tag,
                index=idx,
            )
            referral_created = await _ensure_referral(
                session,
                inviter_id=inviter_user_id,
                invitee_id=invitee.id,
            )
            if referral_created:
                referrals_created += 1

            order, created = await _get_or_create_paid_order(
                session,
                invitee=invitee,
                plan=plan,
                payment_channel=payment_channel,
                final_price=final_price,
                commission_usdt=commission_per_order,
                batch_tag=batch_tag,
                index=idx,
            )
            if created:
                orders_created += 1

            inserted = await _ensure_commission_transaction(
                session,
                inviter_id=inviter_user_id,
                invitee_id=invitee.id,
                order=order,
                commission_usdt=commission_per_order,
                batch_tag=batch_tag,
            )
            if inserted:
                commission_inserted += 1
                commission_amount_inserted_usdt += commission_per_order

        await session.commit()

    async with AsyncSessionLocal() as session:
        available_balance = await _query_available_balance(session, inviter_user_id)

    return SeedSummary(
        inviter_user_id=inviter_user_id,
        invitees_total=invitee_count,
        referrals_created=referrals_created,
        orders_created=orders_created,
        commission_records_inserted=commission_inserted,
        commission_amount_inserted_usdt=commission_amount_inserted_usdt.quantize(
            COMMISSION_QUANT
        ),
        available_balance_usdt=available_balance,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Seed test affiliate data: create virtual invitees with successful paid orders "
            "and commission ledger entries for a target inviter user."
        )
    )
    parser.add_argument("--inviter-user-id", type=int, required=True, help="Target inviter user ID.")
    parser.add_argument(
        "--invitee-count",
        type=int,
        default=30,
        help="How many virtual invitees to generate. Default: 30.",
    )
    parser.add_argument(
        "--payment-channel",
        type=str,
        default="RMB",
        choices=["RMB", "TON", "XTR", "rmb", "ton", "xtr"],
        help="Payment channel used to compute commission rate. Default: RMB.",
    )
    parser.add_argument(
        "--final-price",
        type=Decimal,
        default=Decimal("199.00"),
        help="Paid amount per invitee order under selected channel. Default: 199.00.",
    )
    parser.add_argument(
        "--batch-tag",
        type=str,
        default=datetime.now().strftime("seed_%Y%m%d"),
        help="Tag to make generated seed data deterministic and replay-safe.",
    )
    parser.add_argument(
        "--plan-id",
        type=int,
        default=None,
        help="Optional membership plan ID for generated paid orders.",
    )
    return parser.parse_args()


async def _main() -> None:
    args = _parse_args()
    batch_tag = _normalize_batch_tag(args.batch_tag)
    summary = await seed_affiliate_data(
        inviter_user_id=args.inviter_user_id,
        invitee_count=args.invitee_count,
        payment_channel=args.payment_channel,
        final_price=args.final_price,
        batch_tag=batch_tag,
        plan_id=args.plan_id,
    )
    print("=== Seed Affiliate Test Data Summary ===")
    print(f"inviter_user_id: {summary.inviter_user_id}")
    print(f"invitees_total: {summary.invitees_total}")
    print(f"referrals_created: {summary.referrals_created}")
    print(f"orders_created: {summary.orders_created}")
    print(f"commission_records_inserted: {summary.commission_records_inserted}")
    print(f"commission_amount_inserted_usdt: {summary.commission_amount_inserted_usdt}")
    print(f"available_balance_usdt: {summary.available_balance_usdt}")


if __name__ == "__main__":
    asyncio.run(_main())
