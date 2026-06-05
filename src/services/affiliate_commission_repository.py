from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from src.database.models import AffiliateTransaction, Order, Referral, User


async def lock_affiliate_balance_owner(session, inviter_id: int):
    inviter = (
        await session.execute(select(User).where(User.id == inviter_id).with_for_update())
    ).scalar_one_or_none()
    if inviter is None:
        raise ValueError(f"affiliate inviter user not found: inviter_id={inviter_id}")
    return inviter


async def get_referral_for_invitee(session, invitee_id: int):
    return (
        await session.execute(
            select(Referral).where(Referral.invitee_id == invitee_id).with_for_update()
        )
    ).scalar_one_or_none()


async def get_existing_successful_paid_order_id(
    *,
    session,
    internal_user_id: int,
    exclude_order_id: int,
    valid_payment_channels,
):
    return (
        await session.execute(
            select(Order.id)
            .where(
                Order.internal_user_id == internal_user_id,
                Order.status == "SUCCESS",
                Order.payment_channel.in_(valid_payment_channels),
                Order.final_price > 0,
                Order.paid_at.is_not(None),
                Order.id != exclude_order_id,
            )
            .limit(1)
        )
    ).scalar_one_or_none()


async def insert_affiliate_commission_transaction(
    *,
    session,
    user_id: int,
    amount_usdt,
    reference_id: str,
    idempotency_key: str,
    details: dict,
) -> bool:
    stmt = insert(AffiliateTransaction).values(
        user_id=user_id,
        amount_usdt=amount_usdt,
        transaction_type="COMMISSION_ACCRUAL",
        direction="IN",
        reference_type="ORDER",
        reference_id=reference_id,
        idempotency_key=idempotency_key,
        status="SUCCESS",
        details=details,
    )
    stmt = stmt.on_conflict_do_nothing(
        index_elements=["idempotency_key"]
    ).returning(AffiliateTransaction.id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None
