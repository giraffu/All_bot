from decimal import Decimal, ROUND_HALF_UP
import logging

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.constants import COMMISSION_RATE
from src.core.billing_core import get_default_billing_core_providers
from src.database.models import AffiliateTransaction, Order, Referral, User
from src.exchange_rates import get_exchange_rates

logger = logging.getLogger(__name__)

# Affiliate first-order commission intentionally follows "first successful commit wins"
# so out-of-order payment callbacks cannot create duplicate positive commissions.
VALID_PAYMENT_CHANNELS = {"RMB", "TON", "XTR"}
ZERO_COMMISSION = Decimal("0.0000")
COMMISSION_QUANT = Decimal("0.0001")


class AffiliateCommissionConfigurationError(RuntimeError):
    """Raised when commission cannot be safely calculated for an eligible order."""


def _zero_commission() -> Decimal:
    return ZERO_COMMISSION


def _is_commission_eligible_paid_order(order: Order) -> bool:
    return (
        order.status == "SUCCESS"
        and order.payment_channel in VALID_PAYMENT_CHANNELS
        and order.paid_at is not None
        and Decimal(str(order.final_price)) > 0
    )


async def invalidate_invitation_recharge_cache(inviter_id: int | None) -> None:
    if inviter_id is None:
        return

    redis_client = get_default_billing_core_providers().get_redis_client_func()

    if redis_client and redis_client.redis:
        try:
            await redis_client.redis.delete(
                f"allbot:stats:invitation_recharge:{inviter_id}"
            )
        except Exception as exc:
            logger.warning(
                "failed to invalidate invitation recharge cache for inviter_id=%s: %s",
                inviter_id,
                exc,
            )


async def lock_affiliate_balance_owner(
    session: AsyncSession, inviter_id: int
) -> User:
    """
    Serialize affiliate balance mutations on the inviter's user row.

    Redeems already lock `users` via `FOR UPDATE`, so commission accrual must
    use the same row-level lock to avoid stale balance reads under concurrency.
    """
    inviter = (
        await session.execute(select(User).where(User.id == inviter_id).with_for_update())
    ).scalar_one_or_none()
    if inviter is None:
        raise ValueError(f"affiliate inviter user not found: inviter_id={inviter_id}")
    return inviter


async def calculate_and_set_commission_for_paid_order(
    session: AsyncSession, order: Order
) -> Referral | None:
    if order.id is None:
        await session.flush()

    if not _is_commission_eligible_paid_order(order):
        order.commission_usdt = _zero_commission()
        return None

    referral = (
        await session.execute(
            select(Referral)
            .where(Referral.invitee_id == order.internal_user_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if not referral:
        order.commission_usdt = _zero_commission()
        return None

    await lock_affiliate_balance_owner(session, referral.inviter_id)

    existing_successful_paid_order = (
        await session.execute(
            select(Order.id)
            .where(
                Order.internal_user_id == order.internal_user_id,
                Order.status == "SUCCESS",
                Order.payment_channel.in_(VALID_PAYMENT_CHANNELS),
                Order.final_price > 0,
                Order.paid_at.is_not(None),
                Order.id != order.id,
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing_successful_paid_order:
        order.commission_usdt = _zero_commission()
        return referral

    rates = await get_exchange_rates()
    channel_rate_map = {
        "RMB": Decimal(str(rates.get("rmb_to_usdt", 0))),
        "TON": Decimal(str(rates.get("ton_to_usdt", 0))),
        "XTR": Decimal(str(rates.get("stars_to_usdt", 0))),
    }
    exchange_rate = channel_rate_map.get(order.payment_channel)
    if exchange_rate is None or exchange_rate <= 0:
        raise AffiliateCommissionConfigurationError(
            "missing or non-positive exchange rate for affiliate commission "
            f"calculation: payment_channel={order.payment_channel}, "
            f"exchange_rate={exchange_rate}"
        )

    commission = (
        Decimal(str(order.final_price))
        * exchange_rate
        * Decimal(str(COMMISSION_RATE))
    ).quantize(COMMISSION_QUANT, rounding=ROUND_HALF_UP)
    order.commission_usdt = commission
    return referral


async def record_affiliate_commission_transaction(
    session: AsyncSession,
    order: Order,
    referral: Referral,
    *,
    source: str = "payment_success",
) -> bool:
    if order.id is None:
        await session.flush()

    commission_amount = Decimal(str(order.commission_usdt or 0))
    if order.status != "SUCCESS" or commission_amount <= 0:
        return False
    if referral.invitee_id != order.internal_user_id:
        raise ValueError(
            "referral invitee mismatch for affiliate commission transaction: "
            f"order.internal_user_id={order.internal_user_id}, "
            f"referral.invitee_id={referral.invitee_id}"
        )

    stmt = insert(AffiliateTransaction).values(
        user_id=referral.inviter_id,
        amount_usdt=commission_amount,
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
            "invitee_user_id": order.internal_user_id,
            "inviter_id": referral.inviter_id,
            "payment_channel": order.payment_channel,
            "commission_usdt": str(commission_amount),
            "source": source,
        },
    )
    stmt = stmt.on_conflict_do_nothing(
        index_elements=["idempotency_key"]
    ).returning(AffiliateTransaction.id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None
