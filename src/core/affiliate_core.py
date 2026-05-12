from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.constants import COMMISSION_RATE
from src.database.models import Order, Referral
from src.exchange_rates import get_exchange_rates

VALID_PAYMENT_CHANNELS = {"RMB", "TON", "XTR"}
ZERO_COMMISSION = Decimal("0.0000")
COMMISSION_QUANT = Decimal("0.0001")


def _zero_commission() -> Decimal:
    return ZERO_COMMISSION


async def invalidate_invitation_recharge_cache(inviter_id: int | None) -> None:
    if inviter_id is None:
        return

    from src.services.redis_client import redis_client

    if redis_client and redis_client.redis:
        try:
            await redis_client.redis.delete(
                f"allbot:stats:invitation_recharge:{inviter_id}"
            )
        except Exception:
            pass


async def calculate_and_set_commission_for_paid_order(
    session: AsyncSession, order: Order
) -> None:
    if order.id is None:
        await session.flush()

    if (
        order.status != "SUCCESS"
        or order.payment_channel not in VALID_PAYMENT_CHANNELS
        or order.paid_at is None
        or Decimal(str(order.final_price)) <= 0
    ):
        order.commission_usdt = _zero_commission()
        return

    referral = (
        await session.execute(
            select(Referral).where(Referral.invitee_id == order.telegram_id)
        )
    ).scalar_one_or_none()
    if not referral:
        order.commission_usdt = _zero_commission()
        return

    earlier_paid_order = (
        await session.execute(
            select(Order.id)
            .where(
                Order.telegram_id == order.telegram_id,
                Order.status == "SUCCESS",
                Order.final_price > 0,
                Order.paid_at.is_not(None),
                Order.id != order.id,
                or_(
                    Order.paid_at < order.paid_at,
                    and_(Order.paid_at == order.paid_at, Order.id < order.id),
                ),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if earlier_paid_order:
        order.commission_usdt = _zero_commission()
        await invalidate_invitation_recharge_cache(referral.inviter_id)
        return

    rates = await get_exchange_rates()
    channel_rate_map = {
        "RMB": Decimal(str(rates.get("rmb_to_usdt", 0))),
        "TON": Decimal(str(rates.get("ton_to_usdt", 0))),
        "XTR": Decimal(str(rates.get("stars_to_usdt", 0))),
    }
    exchange_rate = channel_rate_map.get(order.payment_channel)
    if exchange_rate is None:
        order.commission_usdt = _zero_commission()
        return

    commission = (
        Decimal(str(order.final_price))
        * exchange_rate
        * Decimal(str(COMMISSION_RATE))
    ).quantize(COMMISSION_QUANT, rounding=ROUND_HALF_UP)
    order.commission_usdt = commission
    await invalidate_invitation_recharge_cache(referral.inviter_id)
