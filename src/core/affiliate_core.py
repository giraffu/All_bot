from decimal import Decimal, ROUND_HALF_UP
import logging

from src.affiliate_core_repository_bindings import (
    get_default_affiliate_core_repository_bindings,
)
from src.constants import COMMISSION_RATE
from src.core.billing_core import get_default_billing_core_providers
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


def _is_commission_eligible_paid_order(order) -> bool:
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


async def lock_affiliate_balance_owner(session, inviter_id: int):
    """
    Serialize affiliate balance mutations on the inviter's user row.

    Redeems already lock `users` via `FOR UPDATE`, so commission accrual must
    use the same row-level lock to avoid stale balance reads under concurrency.
    """
    return await (
        get_default_affiliate_core_repository_bindings().lock_affiliate_balance_owner_func
    )(session, inviter_id)


async def calculate_and_set_commission_for_paid_order(
    session,
    order,
    *,
    get_referral_for_invitee_func=None,
    lock_affiliate_balance_owner_func=None,
    get_existing_successful_paid_order_id_func=None,
):
    repository_bindings = get_default_affiliate_core_repository_bindings()
    get_referral_for_invitee_func = (
        get_referral_for_invitee_func
        or repository_bindings.get_referral_for_invitee_func
    )
    lock_affiliate_balance_owner_func = (
        lock_affiliate_balance_owner_func or lock_affiliate_balance_owner
    )
    get_existing_successful_paid_order_id_func = (
        get_existing_successful_paid_order_id_func
        or repository_bindings.get_existing_successful_paid_order_id_func
    )

    if order.id is None:
        await session.flush()

    if not _is_commission_eligible_paid_order(order):
        order.commission_usdt = _zero_commission()
        return None

    referral = await get_referral_for_invitee_func(session, order.internal_user_id)
    if not referral:
        order.commission_usdt = _zero_commission()
        return None

    await lock_affiliate_balance_owner_func(session, referral.inviter_id)

    existing_successful_paid_order = await get_existing_successful_paid_order_id_func(
        session=session,
        internal_user_id=order.internal_user_id,
        exclude_order_id=order.id,
        valid_payment_channels=VALID_PAYMENT_CHANNELS,
    )
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
    session,
    order,
    referral,
    *,
    source: str = "payment_success",
    insert_affiliate_commission_transaction_func=None,
) -> bool:
    if insert_affiliate_commission_transaction_func is None:
        insert_affiliate_commission_transaction_func = (
            get_default_affiliate_core_repository_bindings()
            .insert_affiliate_commission_transaction_func
        )

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

    return await insert_affiliate_commission_transaction_func(
        session=session,
        user_id=referral.inviter_id,
        amount_usdt=commission_amount,
        reference_id=str(order.id),
        idempotency_key=f"affiliate:commission:order:{order.id}",
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
