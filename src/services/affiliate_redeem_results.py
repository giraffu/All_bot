from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from src.database.models import AffiliateRedeem, User
from src.services.affiliate_redeem_rules import (
    AFFILIATE_REDEEM_OPTION_FLEXIBLE_USDT,
    AFFILIATE_REDEEM_TYPE_CREDITS,
    REDEEM_USDT_QUANT,
)


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


def build_redeem_option_key(amount_usdt: Decimal) -> str:
    return f"{AFFILIATE_REDEEM_OPTION_FLEXIBLE_USDT}:{amount_usdt:.4f}"


def existing_redeem_matches_request(
    redeem: AffiliateRedeem, amount_usdt: Decimal, credits_granted: int
) -> bool:
    return (
        redeem.redeem_type == AFFILIATE_REDEEM_TYPE_CREDITS
        and Decimal(str(redeem.requested_amount_usdt)).quantize(REDEEM_USDT_QUANT)
        == amount_usdt
        and Decimal(str(redeem.amount_usdt)).quantize(REDEEM_USDT_QUANT) == amount_usdt
        and int(redeem.credits_granted) == credits_granted
    )


def to_credits_redeem_result(
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


def get_redeem_current_credits_snapshot(
    redeem: AffiliateRedeem, fallback_current_credits: int
) -> int:
    details = redeem.details if isinstance(redeem.details, dict) else {}
    snapshot = details.get("current_credits")
    if snapshot is None:
        return fallback_current_credits
    return int(snapshot)


def get_redeem_available_balance_snapshot(
    redeem: AffiliateRedeem, fallback_available_balance_usdt: Decimal
) -> Decimal:
    details = redeem.details if isinstance(redeem.details, dict) else {}
    snapshot = details.get("available_balance_usdt")
    if snapshot is None:
        return fallback_available_balance_usdt.quantize(REDEEM_USDT_QUANT)
    return Decimal(str(snapshot)).quantize(REDEEM_USDT_QUANT)


def serialize_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def build_membership_snapshot(option_key: str, option: dict) -> dict:
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


def to_membership_redeem_result(
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
            "final_expire_at", serialize_datetime(user.identity_expire_at)
        ),
        current_credits=current_credits,
        converted_days=int(details.get("converted_days", 0)),
        settlement_reason=str(details.get("settlement_reason", redeem.settlement_reason or "")),
    )
