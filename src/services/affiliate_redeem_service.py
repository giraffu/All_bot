import logging
import os
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import and_, case, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from config import BOT_TYPE
from src.core.affiliate_core import invalidate_invitation_recharge_cache
from src.core.billing_core import calculate_membership_settlement
from src.database.models import AffiliateRedeem, AffiliateTransaction, User
from src.quota import QuotaManager
from src.services.membership_settlement_service import (
    MembershipSettlementAuditSource,
    apply_membership_settlement_in_session,
)

REDEEM_USDT_QUANT = Decimal("0.0001")
REDEEM_CREDITS_QUANT = Decimal("1")
AFFILIATE_REDEEM_ROUNDING_MODE = "FIXED_PACKAGE"
AFFILIATE_MEMBERSHIP_REDEEM_RMB_TO_USDT_RATE = Decimal("6.8")
AFFILIATE_REDEEM_TYPE_CREDITS = "CREDITS"
AFFILIATE_REDEEM_TYPE_MEMBERSHIP = "MEMBERSHIP"
AFFILIATE_REDEEM_OPTION_FLEXIBLE_USDT = "FLEXIBLE_USDT"
AFFILIATE_REDEEM_SUCCESS = "SUCCESS"
AFFILIATE_MEMBERSHIP_REDEEM_ENABLED_ENV = "AFFILIATE_MEMBERSHIP_REDEEM_ENABLED"
MEMBERSHIP_SETTLEMENT_V2_ENABLED_ENV = "MEMBERSHIP_SETTLEMENT_V2_ENABLED"
AFFILIATE_CREDITS_REDEEM_PACKAGES = (
    {"amount_usdt": Decimal("1.0000"), "credits": 130},
    {"amount_usdt": Decimal("3.0000"), "credits": 390},
    {"amount_usdt": Decimal("6.0000"), "credits": 780},
    {"amount_usdt": Decimal("10.0000"), "credits": 1800},
    {"amount_usdt": Decimal("15.0000"), "credits": 2700},
    {"amount_usdt": Decimal("20.0000"), "credits": 4000},
)
AFFILIATE_CREDITS_REDEEM_PACKAGE_MAP = {
    package["amount_usdt"]: int(package["credits"])
    for package in AFFILIATE_CREDITS_REDEEM_PACKAGES
}
AFFILIATE_CREDITS_REDEEM_ALLOWED_AMOUNTS_TEXT = "1、3、6、10、15、20 USDT"


def _convert_membership_rmb_price_to_usdt(amount_rmb: str) -> Decimal:
    return (Decimal(amount_rmb) / AFFILIATE_MEMBERSHIP_REDEEM_RMB_TO_USDT_RATE).quantize(
        REDEEM_USDT_QUANT,
        rounding=ROUND_HALF_UP,
    )


AFFILIATE_MEMBERSHIP_REDEEM_OPTIONS = {
    "inner_30d": {
        "schema_version": "affiliate_membership_redeem_v2",
        "plan_id": 1,
        "plan_name": "内门弟子月卡",
        "display_name": "内门弟子 30 天",
        "target_identity": "内门弟子",
        "duration_days": 30,
        "redeem_amount_usdt": _convert_membership_rmb_price_to_usdt("30"),
        "reward_credits": 400,
        "grant_reward_credits": True,
        "allow_pure_credit_plan": False,
        "is_enabled": True,
    },
    "core_30d": {
        "schema_version": "affiliate_membership_redeem_v2",
        "plan_id": 2,
        "plan_name": "核心弟子月卡",
        "display_name": "核心弟子 30 天",
        "target_identity": "核心弟子",
        "duration_days": 30,
        "redeem_amount_usdt": _convert_membership_rmb_price_to_usdt("70"),
        "reward_credits": 1200,
        "grant_reward_credits": True,
        "allow_pure_credit_plan": False,
        "is_enabled": True,
    },
    "true_30d": {
        "schema_version": "affiliate_membership_redeem_v2",
        "plan_id": 3,
        "plan_name": "真传弟子月卡",
        "display_name": "真传弟子 30 天",
        "target_identity": "真传弟子",
        "duration_days": 30,
        "redeem_amount_usdt": _convert_membership_rmb_price_to_usdt("120"),
        "reward_credits": 3000,
        "grant_reward_credits": True,
        "allow_pure_credit_plan": False,
        "is_enabled": True,
    },
}

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


@dataclass(frozen=True)
class AffiliateMembershipRedeemResult:
    redeem_id: int
    redeem_type: str
    option_key: str
    target_plan_id: int
    target_identity: str
    duration_days: int
    amount_usdt: Decimal
    credits_granted: int
    status: str
    idempotency_key: str
    available_balance_usdt: Decimal
    current_identity: str
    identity_expire_at: str | None
    current_credits: int
    converted_days: int
    settlement_reason: str


def _is_feature_enabled(name: str) -> bool:
    if BOT_TYPE == "TEST":
        test_value = os.getenv(f"{name}_TEST")
        if test_value not in (None, ""):
            return test_value.strip().lower() in {"1", "true", "yes", "on"}
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def is_membership_settlement_v2_enabled() -> bool:
    return _is_feature_enabled(MEMBERSHIP_SETTLEMENT_V2_ENABLED_ENV)


def is_affiliate_membership_redeem_enabled() -> bool:
    return _is_feature_enabled(AFFILIATE_MEMBERSHIP_REDEEM_ENABLED_ENV)


def normalize_redeem_amount_usdt(amount_usdt: Decimal) -> Decimal:
    normalized = Decimal(str(amount_usdt)).quantize(REDEEM_USDT_QUANT)
    if normalized <= 0:
        raise ValueError("amount_usdt must be positive")
    return normalized


def build_exchange_rate_snapshot(amount_usdt: Decimal, credits_granted: int) -> str:
    return f"{amount_usdt:.4f} USDT = {credits_granted} credits"


def get_affiliate_credits_redeem_package(amount_usdt: Decimal) -> tuple[Decimal, int]:
    normalized = normalize_redeem_amount_usdt(amount_usdt)
    credits = AFFILIATE_CREDITS_REDEEM_PACKAGE_MAP.get(normalized)
    if credits is None:
        raise ValueError(
            f"返佣兑灵石仅支持固定套餐：{AFFILIATE_CREDITS_REDEEM_ALLOWED_AMOUNTS_TEXT}"
        )
    return normalized, credits


def calculate_redeem_credits(amount_usdt: Decimal) -> int:
    _, credits = get_affiliate_credits_redeem_package(amount_usdt)
    return credits


def list_affiliate_credits_redeem_packages() -> tuple[dict, ...]:
    return tuple(
        {
            "amount_usdt": Decimal(str(package["amount_usdt"])).quantize(REDEEM_USDT_QUANT),
            "credits": int(package["credits"]),
        }
        for package in AFFILIATE_CREDITS_REDEEM_PACKAGES
    )


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


def _serialize_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _get_membership_option(option_key: str) -> dict:
    option = AFFILIATE_MEMBERSHIP_REDEEM_OPTIONS.get(option_key)
    if option is None:
        raise ValueError("unsupported membership redeem option")
    return option


def _build_membership_snapshot(option_key: str, option: dict) -> dict:
    return {
        "schema_version": option["schema_version"],
        "requested_option_key": option_key,
        "redeem_option_key": option_key,
        "target_plan_id": int(option["plan_id"]),
        "target_plan_name": option["plan_name"],
        "target_display_name": option["display_name"],
        "target_identity": option["target_identity"],
        "duration_days": int(option["duration_days"]),
        "reward_credits": int(option["reward_credits"]),
        "grant_reward_credits": bool(option["grant_reward_credits"]),
        "credits_granted": 0,
        "amount_usdt": f"{Decimal(str(option['redeem_amount_usdt'])).quantize(REDEEM_USDT_QUANT):.4f}",
        "converted_days": 0,
        "settlement_reason": "",
        "allow_pure_credit_plan": bool(option["allow_pure_credit_plan"]),
    }


def _to_membership_result(
    *,
    redeem: AffiliateRedeem,
    user: User,
    fallback_available_balance_usdt: Decimal,
) -> AffiliateMembershipRedeemResult:
    details = redeem.details if isinstance(redeem.details, dict) else {}
    amount_usdt = Decimal(
        str(details.get("amount_usdt", redeem.amount_usdt))
    ).quantize(REDEEM_USDT_QUANT)
    available_balance_usdt = Decimal(
        str(details.get("available_balance_usdt", fallback_available_balance_usdt))
    ).quantize(REDEEM_USDT_QUANT)
    current_credits = int(details.get("current_credits", int(user.credits or 0)))
    return AffiliateMembershipRedeemResult(
        redeem_id=int(redeem.id),
        redeem_type=redeem.redeem_type,
        option_key=str(details.get("redeem_option_key", redeem.redeem_option_key)),
        target_plan_id=int(details.get("target_plan_id", redeem.target_plan_id or 0)),
        target_identity=str(details.get("target_identity", redeem.target_identity or "")),
        duration_days=int(details.get("duration_days", redeem.duration_days or 0)),
        amount_usdt=amount_usdt,
        credits_granted=int(details.get("credits_granted", redeem.credits_granted)),
        status=redeem.status,
        idempotency_key=redeem.idempotency_key,
        available_balance_usdt=available_balance_usdt,
        current_identity=str(details.get("final_identity", user.current_identity or "")),
        identity_expire_at=details.get(
            "final_expire_at", _serialize_datetime(user.identity_expire_at)
        ),
        current_credits=current_credits,
        converted_days=int(details.get("converted_days", 0)),
        settlement_reason=str(details.get("settlement_reason", redeem.settlement_reason or "")),
    )


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
    amount_usdt, credits_granted = get_affiliate_credits_redeem_package(amount_usdt)
    exchange_rate_snapshot = build_exchange_rate_snapshot(amount_usdt, credits_granted)

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
                exchange_rate_snapshot=exchange_rate_snapshot,
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
                    exchange_rate_snapshot=exchange_rate_snapshot,
                )
            )

    if owns_transaction and should_invalidate_cache:
        await invalidate_affiliate_redeem_cache_after_commit(user_id)

    return redeem_result


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
            _to_membership_result(
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
    snapshot = _build_membership_snapshot(option_key, option)

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

    applied_snapshot = await apply_membership_settlement_in_session(
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
        "final_expire_at": _serialize_datetime(settlement_result.final_expire_at),
        "converted_days": settlement_result.converted_days,
        "settlement_reason": settlement_result.settlement_reason,
    }
    redeem.details = full_snapshot
    await session.flush()

    return (
        _to_membership_result(
            redeem=redeem,
            user=user,
            fallback_available_balance_usdt=available_after_redeem,
        ),
        True,
    )


async def redeem_affiliate_balance_to_membership(
    session: AsyncSession,
    *,
    user_id: int,
    option_key: str,
    idempotency_key: str,
) -> AffiliateMembershipRedeemResult:
    should_invalidate_cache = False
    owns_transaction = not session.in_transaction()

    if not owns_transaction:
        redeem_result, should_invalidate_cache = (
            await _redeem_affiliate_balance_to_membership_in_transaction(
                session,
                user_id=user_id,
                option_key=option_key,
                idempotency_key=idempotency_key,
            )
        )
    else:
        async with session.begin():
            redeem_result, should_invalidate_cache = (
                await _redeem_affiliate_balance_to_membership_in_transaction(
                    session,
                    user_id=user_id,
                    option_key=option_key,
                    idempotency_key=idempotency_key,
                )
            )

    if owns_transaction and should_invalidate_cache:
        await invalidate_affiliate_redeem_cache_after_commit(user_id)

    return redeem_result
