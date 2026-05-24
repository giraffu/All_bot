import logging
from datetime import datetime
from decimal import Decimal

from sqlalchemy import and_, case, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.affiliate_core import invalidate_invitation_recharge_cache
from src.core.billing_core import calculate_membership_settlement
from src.database.models import AffiliateRedeem, AffiliateTransaction, User
from src.quota import QuotaManager
from src.services.affiliate_redeem_rules import (
    AFFILIATE_MEMBERSHIP_REDEEM_OPTIONS,
    AFFILIATE_REDEEM_ROUNDING_MODE,
    AFFILIATE_REDEEM_SUCCESS,
    AFFILIATE_REDEEM_TYPE_CREDITS,
    AFFILIATE_REDEEM_TYPE_MEMBERSHIP,
    REDEEM_USDT_QUANT,
    build_exchange_rate_snapshot,
    calculate_redeem_credits,
    get_affiliate_credits_redeem_package,
    get_membership_option as _get_membership_option,
    is_affiliate_membership_redeem_enabled,
    is_membership_settlement_v2_enabled,
    list_affiliate_credits_redeem_packages,
    normalize_redeem_amount_usdt,
)
from src.services.affiliate_redeem_results import (
    AffiliateCreditsRedeemResult,
    AffiliateMembershipRedeemResult,
    build_membership_snapshot,
    build_redeem_option_key,
    existing_redeem_matches_request,
    get_redeem_available_balance_snapshot,
    get_redeem_current_credits_snapshot,
    serialize_datetime,
    to_credits_redeem_result,
    to_membership_redeem_result,
)
from src.services.membership_settlement_service import (
    MembershipSettlementAuditSource,
    apply_membership_settlement_in_session,
)

quota_manager = QuotaManager()
logger = logging.getLogger(__name__)

__all__ = [
    "AFFILIATE_MEMBERSHIP_REDEEM_OPTIONS",
    "AffiliateCreditsRedeemResult",
    "AffiliateMembershipRedeemResult",
    "AffiliateRedeemConflictError",
    "AffiliateRedeemError",
    "AffiliateRedeemInsufficientBalanceError",
    "calculate_redeem_credits",
    "invalidate_affiliate_redeem_cache_after_commit",
    "is_affiliate_membership_redeem_enabled",
    "is_membership_settlement_v2_enabled",
    "list_affiliate_credits_redeem_packages",
    "normalize_redeem_amount_usdt",
    "query_affiliate_available_balance",
    "redeem_affiliate_balance_to_credits",
    "redeem_affiliate_balance_to_membership",
]


class AffiliateRedeemError(RuntimeError):
    """Base error for affiliate redeem flow."""


class AffiliateRedeemConflictError(AffiliateRedeemError):
    """Raised when the same idempotency key is reused with different parameters."""


class AffiliateRedeemInsufficientBalanceError(AffiliateRedeemError):
    """Raised when available affiliate balance is not enough for the redeem."""

    def __init__(self, *, available_balance_usdt: Decimal, requested_amount_usdt: Decimal):
        self.available_balance_usdt = available_balance_usdt
        self.requested_amount_usdt = requested_amount_usdt
        super().__init__("insufficient affiliate balance")

async def query_affiliate_available_balance(
    session: AsyncSession, user_id: int
) -> Decimal:
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
    ).where(AffiliateTransaction.user_id == user_id)
    balance = (await session.execute(stmt)).scalar_one()
    return Decimal(str(balance or 0)).quantize(REDEEM_USDT_QUANT)

async def invalidate_affiliate_redeem_cache_after_commit(user_id: int) -> None:
    try:
        await invalidate_invitation_recharge_cache(user_id)
    except Exception:
        logger.warning(
            "Failed to invalidate affiliate recharge cache after redeem commit for user %s",
            user_id,
            exc_info=True,
        )


async def _run_affiliate_redeem_transaction(
    session: AsyncSession,
    *,
    user_id: int,
    redeem_runner,
):
    owns_transaction = not session.in_transaction()

    if not owns_transaction:
        redeem_result, should_invalidate_cache = await redeem_runner()
    else:
        async with session.begin():
            redeem_result, should_invalidate_cache = await redeem_runner()

    if owns_transaction and should_invalidate_cache:
        await invalidate_affiliate_redeem_cache_after_commit(user_id)

    return redeem_result


async def _redeem_affiliate_balance_to_credits_in_transaction(
    session: AsyncSession,
    *,
    user_id: int,
    amount_usdt: Decimal,
    idempotency_key: str,
    credits_granted: int,
    exchange_rate_snapshot: str,
) -> tuple[AffiliateCreditsRedeemResult, dict | None, bool]:
    user = (
        await session.execute(select(User).where(User.id == user_id).with_for_update())
    ).scalar_one_or_none()
    if not user:
        raise ValueError(f"user {user_id} not found")

    existing_redeem = (
        await session.execute(
            select(AffiliateRedeem)
            .where(
                AffiliateRedeem.user_id == user_id,
                AffiliateRedeem.idempotency_key == idempotency_key,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if existing_redeem:
        if not existing_redeem_matches_request(
            existing_redeem, amount_usdt, credits_granted
        ):
            raise AffiliateRedeemConflictError(
                "idempotency_key already used with different redeem parameters"
            )

        current_available_balance_usdt = await query_affiliate_available_balance(
            session, user_id
        )
        return (
            to_credits_redeem_result(
                redeem=existing_redeem,
                available_balance_usdt=get_redeem_available_balance_snapshot(
                    existing_redeem, current_available_balance_usdt
                ),
                current_credits=get_redeem_current_credits_snapshot(
                    existing_redeem,
                    fallback_current_credits=int(user.credits or 0),
                ),
            ),
            None,
            False,
        )

    available_balance_usdt = await query_affiliate_available_balance(session, user_id)
    if available_balance_usdt < amount_usdt:
        raise AffiliateRedeemInsufficientBalanceError(
            available_balance_usdt=available_balance_usdt,
            requested_amount_usdt=amount_usdt,
        )

    redeem = AffiliateRedeem(
        user_id=user_id,
        redeem_type=AFFILIATE_REDEEM_TYPE_CREDITS,
        redeem_option_key=build_redeem_option_key(amount_usdt),
        requested_amount_usdt=amount_usdt,
        amount_usdt=amount_usdt,
        credits_granted=credits_granted,
        exchange_rate_snapshot=exchange_rate_snapshot,
        rounding_mode=AFFILIATE_REDEEM_ROUNDING_MODE,
        status=AFFILIATE_REDEEM_SUCCESS,
        idempotency_key=idempotency_key,
        details={
            "package_type": "fixed_usdt_package",
            "requested_amount_usdt": f"{amount_usdt:.4f}",
            "credits_granted": credits_granted,
            "exchange_rate_snapshot": exchange_rate_snapshot,
        },
    )
    session.add(redeem)
    await session.flush()

    ledger_stmt = insert(AffiliateTransaction).values(
        user_id=user_id,
        amount_usdt=amount_usdt,
        transaction_type="CREDITS_REDEEM",
        direction="OUT",
        reference_type="AFFILIATE_REDEEM",
        reference_id=str(redeem.id),
        idempotency_key=f"affiliate:redeem:credits:{redeem.id}",
        status="SUCCESS",
        details={
            "redeem_id": redeem.id,
            "amount_usdt": f"{amount_usdt:.4f}",
            "credits_granted": credits_granted,
            "exchange_rate_snapshot": exchange_rate_snapshot,
            "rounding_mode": AFFILIATE_REDEEM_ROUNDING_MODE,
        },
    )
    ledger_stmt = ledger_stmt.on_conflict_do_nothing(
        index_elements=["idempotency_key"]
    ).returning(AffiliateTransaction.id)
    ledger_id = (await session.execute(ledger_stmt)).scalar_one_or_none()
    if ledger_id is None:
        raise AffiliateRedeemError("failed to persist affiliate redeem ledger transaction")

    credit_change = await quota_manager.add_credits(
        user_id=user_id,
        credits=credits_granted,
        task_type="affiliate_credits_redeem",
        session=session,
        extra_info={
            "redeem_id": redeem.id,
            "amount_usdt": f"{amount_usdt:.4f}",
            "exchange_rate_snapshot": exchange_rate_snapshot,
            "rounding_mode": AFFILIATE_REDEEM_ROUNDING_MODE,
        },
    )

    available_after_redeem = (available_balance_usdt - amount_usdt).quantize(
        REDEEM_USDT_QUANT
    )
    redeem.details = {
        **(redeem.details or {}),
        "current_credits": credit_change.new_balance,
        "available_balance_usdt": f"{available_after_redeem:.4f}",
    }
    await session.flush()
    return (
        to_credits_redeem_result(
            redeem=redeem,
            available_balance_usdt=available_after_redeem,
            current_credits=credit_change.new_balance,
        ),
        {
            "user_id": user_id,
            "username": user.username,
            "redeem_id": redeem.id,
            "credit_change": credits_granted,
            "current_balance": credit_change.new_balance,
            "amount_usdt": amount_usdt,
        },
        True,
    )


async def redeem_affiliate_balance_to_credits(
    session: AsyncSession,
    *,
    user_id: int,
    amount_usdt: Decimal,
    idempotency_key: str,
) -> AffiliateCreditsRedeemResult:
    amount_usdt, credits_granted = get_affiliate_credits_redeem_package(amount_usdt)
    exchange_rate_snapshot = build_exchange_rate_snapshot(amount_usdt, credits_granted)

    async def _run_credits_redeem():
        redeem_result, _audit_payload, should_invalidate_cache = (
            await _redeem_affiliate_balance_to_credits_in_transaction(
                session,
                user_id=user_id,
                amount_usdt=amount_usdt,
                idempotency_key=idempotency_key,
                credits_granted=credits_granted,
                exchange_rate_snapshot=exchange_rate_snapshot,
            )
        )
        return redeem_result, should_invalidate_cache

    return await _run_affiliate_redeem_transaction(
        session,
        user_id=user_id,
        redeem_runner=_run_credits_redeem,
    )


async def _redeem_affiliate_balance_to_membership_in_transaction(
    session: AsyncSession,
    *,
    user_id: int,
    option_key: str,
    idempotency_key: str,
) -> tuple[AffiliateMembershipRedeemResult, bool]:
    user = (
        await session.execute(select(User).where(User.id == user_id).with_for_update())
    ).scalar_one_or_none()
    if not user:
        raise ValueError(f"user {user_id} not found")

    existing_redeem = (
        await session.execute(
            select(AffiliateRedeem)
            .where(
                AffiliateRedeem.user_id == user_id,
                AffiliateRedeem.idempotency_key == idempotency_key,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if existing_redeem:
        if existing_redeem.redeem_type != AFFILIATE_REDEEM_TYPE_MEMBERSHIP:
            raise AffiliateRedeemConflictError(
                "idempotency_key already used with different redeem type"
            )
        existing_option_key = (
            existing_redeem.details.get("redeem_option_key")
            if isinstance(existing_redeem.details, dict)
            else None
        ) or existing_redeem.redeem_option_key
        if existing_option_key != option_key:
            raise AffiliateRedeemConflictError(
                "idempotency_key already used with different membership option"
            )
        current_available_balance_usdt = await query_affiliate_available_balance(
            session, user_id
        )
        return (
            to_membership_redeem_result(
                redeem=existing_redeem,
                user=user,
                fallback_available_balance_usdt=current_available_balance_usdt,
            ),
            False,
        )

    option = _get_membership_option(option_key)
    if not option.get("is_enabled", False):
        raise ValueError("membership redeem option is disabled")

    available_balance_usdt = await query_affiliate_available_balance(session, user_id)
    amount_usdt = Decimal(str(option["redeem_amount_usdt"])).quantize(REDEEM_USDT_QUANT)
    if available_balance_usdt < amount_usdt:
        raise AffiliateRedeemInsufficientBalanceError(
            available_balance_usdt=available_balance_usdt,
            requested_amount_usdt=amount_usdt,
        )

    settlement_result = calculate_membership_settlement(
        current_identity=user.current_identity,
        current_expire_at=user.identity_expire_at,
        target_identity=option["target_identity"],
        duration_days=int(option["duration_days"]),
        reward_credits=int(option["reward_credits"]),
        grant_reward_credits=bool(option["grant_reward_credits"]),
        now=datetime.now(),
    )
    snapshot = build_membership_snapshot(option_key, option)

    redeem = AffiliateRedeem(
        user_id=user_id,
        redeem_type=AFFILIATE_REDEEM_TYPE_MEMBERSHIP,
        redeem_option_key=option_key,
        requested_amount_usdt=amount_usdt,
        amount_usdt=amount_usdt,
        credits_granted=settlement_result.credits_to_grant,
        target_plan_id=int(option["plan_id"]),
        target_identity=option["target_identity"],
        duration_days=int(option["duration_days"]),
        grant_reward_credits=bool(option["grant_reward_credits"]),
        settlement_reason=settlement_result.settlement_reason,
        exchange_rate_snapshot=None,
        rounding_mode=None,
        status=AFFILIATE_REDEEM_SUCCESS,
        idempotency_key=idempotency_key,
        details=snapshot,
    )
    session.add(redeem)
    await session.flush()

    await _create_membership_redeem_ledger_entry(
        session,
        user_id=user_id,
        redeem=redeem,
        option_key=option_key,
        option=option,
        amount_usdt=amount_usdt,
    )

    applied_snapshot = await _apply_affiliate_membership_settlement(
        session,
        user=user,
        redeem=redeem,
        option_key=option_key,
        snapshot=snapshot,
        settlement_result=settlement_result,
    )

    available_after_redeem = (available_balance_usdt - amount_usdt).quantize(
        REDEEM_USDT_QUANT
    )
    full_snapshot = {
        **applied_snapshot,
        "requested_option_key": option_key,
        "redeem_option_key": option_key,
        "target_plan_id": int(option["plan_id"]),
        "target_plan_name": option["plan_name"],
        "target_display_name": option["display_name"],
        "target_identity": option["target_identity"],
        "duration_days": int(option["duration_days"]),
        "reward_credits": int(option["reward_credits"]),
        "grant_reward_credits": bool(option["grant_reward_credits"]),
        "credits_granted": settlement_result.credits_to_grant,
        "amount_usdt": f"{amount_usdt:.4f}",
        "available_balance_usdt": f"{available_after_redeem:.4f}",
        "current_credits": int(applied_snapshot["current_credits"]),
        "final_identity": settlement_result.final_identity,
        "final_expire_at": serialize_datetime(settlement_result.final_expire_at),
        "converted_days": settlement_result.converted_days,
        "settlement_reason": settlement_result.settlement_reason,
    }
    redeem.details = full_snapshot
    await session.flush()

    return (
        to_membership_redeem_result(
            redeem=redeem,
            user=user,
            fallback_available_balance_usdt=available_after_redeem,
        ),
        True,
    )


async def _create_membership_redeem_ledger_entry(
    session: AsyncSession,
    *,
    user_id: int,
    redeem: AffiliateRedeem,
    option_key: str,
    option: dict,
    amount_usdt: Decimal,
) -> None:
    ledger_stmt = (
        insert(AffiliateTransaction)
        .values(
            user_id=user_id,
            amount_usdt=amount_usdt,
            transaction_type="MEMBERSHIP_REDEEM",
            direction="OUT",
            reference_type="AFFILIATE_REDEEM",
            reference_id=str(redeem.id),
            idempotency_key=f"affiliate:redeem:membership:{redeem.id}",
            status="SUCCESS",
            details={
                "redeem_id": redeem.id,
                "option_key": option_key,
                "amount_usdt": f"{amount_usdt:.4f}",
                "target_identity": option["target_identity"],
                "duration_days": int(option["duration_days"]),
            },
        )
        .on_conflict_do_nothing(index_elements=["idempotency_key"])
        .returning(AffiliateTransaction.id)
    )
    ledger_id = (await session.execute(ledger_stmt)).scalar_one_or_none()
    if ledger_id is None:
        raise AffiliateRedeemError(
            "failed to persist affiliate membership redeem ledger transaction"
        )


async def _apply_affiliate_membership_settlement(
    session: AsyncSession,
    *,
    user: User,
    redeem: AffiliateRedeem,
    option_key: str,
    snapshot: dict,
    settlement_result,
) -> dict:
    return await apply_membership_settlement_in_session(
        locked_user=user,
        settlement_snapshot=snapshot,
        settlement_result=settlement_result,
        audit_source=MembershipSettlementAuditSource(
            source="affiliate_membership_redeem",
            source_channel="AFFILIATE",
            source_order_id=str(redeem.id),
            option_key=option_key,
        ),
        session=session,
    )


async def redeem_affiliate_balance_to_membership(
    session: AsyncSession,
    *,
    user_id: int,
    option_key: str,
    idempotency_key: str,
) -> AffiliateMembershipRedeemResult:
    async def _run_membership_redeem():
        return await _redeem_affiliate_balance_to_membership_in_transaction(
            session,
            user_id=user_id,
            option_key=option_key,
            idempotency_key=idempotency_key,
        )

    return await _run_affiliate_redeem_transaction(
        session,
        user_id=user_id,
        redeem_runner=_run_membership_redeem,
    )
