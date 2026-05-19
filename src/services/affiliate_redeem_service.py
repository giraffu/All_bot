import logging
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import and_, case, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.affiliate_core import invalidate_invitation_recharge_cache
from src.database.models import AffiliateRedeem, AffiliateTransaction, User
from src.quota import QuotaManager
REDEEM_USDT_QUANT = Decimal("0.0001")
REDEEM_CREDITS_QUANT = Decimal("1")
AFFILIATE_REDEEM_RATE = Decimal("90")
AFFILIATE_REDEEM_RATE_SNAPSHOT = "1.0000 USDT = 90 credits"
AFFILIATE_REDEEM_ROUNDING_MODE = "ROUND_HALF_UP"
AFFILIATE_REDEEM_TYPE_CREDITS = "CREDITS"
AFFILIATE_REDEEM_OPTION_FLEXIBLE_USDT = "FLEXIBLE_USDT"
AFFILIATE_REDEEM_SUCCESS = "SUCCESS"

quota_manager = QuotaManager()
logger = logging.getLogger(__name__)


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


@dataclass(frozen=True)
class AffiliateCreditsRedeemResult:
    redeem_id: int
    redeem_type: str
    amount_usdt: Decimal
    credits_granted: int
    status: str
    idempotency_key: str
    available_balance_usdt: Decimal
    current_credits: int
    exchange_rate_snapshot: str
    rounding_mode: str


def normalize_redeem_amount_usdt(amount_usdt: Decimal) -> Decimal:
    normalized = Decimal(str(amount_usdt)).quantize(REDEEM_USDT_QUANT)
    if normalized <= 0:
        raise ValueError("amount_usdt must be positive")
    return normalized


def calculate_redeem_credits(amount_usdt: Decimal) -> int:
    credits = (amount_usdt * AFFILIATE_REDEEM_RATE).quantize(
        REDEEM_CREDITS_QUANT, rounding=ROUND_HALF_UP
    )
    credits_int = int(credits)
    if credits_int <= 0:
        raise ValueError("redeem amount is too small to grant credits")
    return credits_int


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


def _build_redeem_option_key(amount_usdt: Decimal) -> str:
    return f"{AFFILIATE_REDEEM_OPTION_FLEXIBLE_USDT}:{amount_usdt:.4f}"


def _existing_redeem_matches_request(
    redeem: AffiliateRedeem, amount_usdt: Decimal, credits_granted: int
) -> bool:
    return (
        redeem.redeem_type == AFFILIATE_REDEEM_TYPE_CREDITS
        and Decimal(str(redeem.requested_amount_usdt)).quantize(REDEEM_USDT_QUANT)
        == amount_usdt
        and Decimal(str(redeem.amount_usdt)).quantize(REDEEM_USDT_QUANT) == amount_usdt
        and int(redeem.credits_granted) == credits_granted
    )


def _to_result(
    *,
    redeem: AffiliateRedeem,
    available_balance_usdt: Decimal,
    current_credits: int,
) -> AffiliateCreditsRedeemResult:
    return AffiliateCreditsRedeemResult(
        redeem_id=int(redeem.id),
        redeem_type=redeem.redeem_type,
        amount_usdt=Decimal(str(redeem.amount_usdt)).quantize(REDEEM_USDT_QUANT),
        credits_granted=int(redeem.credits_granted),
        status=redeem.status,
        idempotency_key=redeem.idempotency_key,
        available_balance_usdt=available_balance_usdt.quantize(REDEEM_USDT_QUANT),
        current_credits=current_credits,
        exchange_rate_snapshot=redeem.exchange_rate_snapshot,
        rounding_mode=redeem.rounding_mode,
    )


def _get_redeem_current_credits_snapshot(
    redeem: AffiliateRedeem, fallback_current_credits: int
) -> int:
    details = redeem.details if isinstance(redeem.details, dict) else {}
    snapshot = details.get("current_credits")
    if snapshot is None:
        return fallback_current_credits
    return int(snapshot)


def _get_redeem_available_balance_snapshot(
    redeem: AffiliateRedeem, fallback_available_balance_usdt: Decimal
) -> Decimal:
    details = redeem.details if isinstance(redeem.details, dict) else {}
    snapshot = details.get("available_balance_usdt")
    if snapshot is None:
        return fallback_available_balance_usdt.quantize(REDEEM_USDT_QUANT)
    return Decimal(str(snapshot)).quantize(REDEEM_USDT_QUANT)


async def invalidate_affiliate_redeem_cache_after_commit(user_id: int) -> None:
    try:
        await invalidate_invitation_recharge_cache(user_id)
    except Exception:
        logger.warning(
            "Failed to invalidate affiliate recharge cache after redeem commit for user %s",
            user_id,
            exc_info=True,
        )


async def _redeem_affiliate_balance_to_credits_in_transaction(
    session: AsyncSession,
    *,
    user_id: int,
    amount_usdt: Decimal,
    idempotency_key: str,
    credits_granted: int,
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
        if not _existing_redeem_matches_request(
            existing_redeem, amount_usdt, credits_granted
        ):
            raise AffiliateRedeemConflictError(
                "idempotency_key already used with different redeem parameters"
            )

        current_available_balance_usdt = await query_affiliate_available_balance(
            session, user_id
        )
        return (
            _to_result(
                redeem=existing_redeem,
                available_balance_usdt=_get_redeem_available_balance_snapshot(
                    existing_redeem, current_available_balance_usdt
                ),
                current_credits=_get_redeem_current_credits_snapshot(
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
        redeem_option_key=_build_redeem_option_key(amount_usdt),
        requested_amount_usdt=amount_usdt,
        amount_usdt=amount_usdt,
        credits_granted=credits_granted,
        exchange_rate_snapshot=AFFILIATE_REDEEM_RATE_SNAPSHOT,
        rounding_mode=AFFILIATE_REDEEM_ROUNDING_MODE,
        status=AFFILIATE_REDEEM_SUCCESS,
        idempotency_key=idempotency_key,
        details={
            "rate": str(AFFILIATE_REDEEM_RATE),
            "requested_amount_usdt": f"{amount_usdt:.4f}",
            "credits_granted": credits_granted,
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
            "exchange_rate_snapshot": AFFILIATE_REDEEM_RATE_SNAPSHOT,
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
            "exchange_rate_snapshot": AFFILIATE_REDEEM_RATE_SNAPSHOT,
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
        _to_result(
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
    amount_usdt = normalize_redeem_amount_usdt(amount_usdt)
    credits_granted = calculate_redeem_credits(amount_usdt)

    should_invalidate_cache = False
    owns_transaction = not session.in_transaction()

    # Reuse an already-open request transaction (e.g. opened by auth dependency),
    # otherwise create an explicit write transaction boundary here.
    if not owns_transaction:
        redeem_result, _, should_invalidate_cache = (
            await _redeem_affiliate_balance_to_credits_in_transaction(
                session,
                user_id=user_id,
                amount_usdt=amount_usdt,
                idempotency_key=idempotency_key,
                credits_granted=credits_granted,
            )
        )
    else:
        async with session.begin():
            redeem_result, _, should_invalidate_cache = (
                await _redeem_affiliate_balance_to_credits_in_transaction(
                    session,
                    user_id=user_id,
                    amount_usdt=amount_usdt,
                    idempotency_key=idempotency_key,
                    credits_granted=credits_granted,
                )
            )

    if owns_transaction and should_invalidate_cache:
        await invalidate_affiliate_redeem_cache_after_commit(user_id)

    return redeem_result
