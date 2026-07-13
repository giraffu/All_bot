from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from src.services.affiliate_redeem_service import get_affiliate_credits_redeem_package


class AffiliateCreditsRedeemRequest(BaseModel):
    amount_usdt: Decimal = Field(gt=0, max_digits=10)
    idempotency_key: str = Field(min_length=1, max_length=128)

    @field_validator("amount_usdt")
    @classmethod
    def normalize_amount_usdt(cls, value: Decimal) -> Decimal:
        normalized = Decimal(str(value)).quantize(Decimal("0.0001"))
        if normalized <= 0:
            raise ValueError("兑换金额必须大于 0")
        get_affiliate_credits_redeem_package(normalized)
        return normalized


class AffiliateCreditsRedeemResponse(BaseModel):
    redeem_id: int
    redeem_type: str
    amount_usdt: float
    credits_granted: int
    status: str
    idempotency_key: str
    available_balance_usdt: float
    current_credits: int
    exchange_rate_snapshot: str
    rounding_mode: str


class AffiliateMembershipRedeemRequest(BaseModel):
    option_key: str = Field(min_length=1, max_length=64)
    idempotency_key: str = Field(min_length=1, max_length=128)


class AffiliateMembershipRedeemResponse(BaseModel):
    redeem_id: int
    redeem_type: str
    option_key: str
    target_plan_id: int
    target_identity: str
    duration_days: int
    amount_usdt: str
    credits_granted: int
    status: str
    idempotency_key: str
    available_balance_usdt: str
    current_identity: str
    identity_expire_at: str | None
    current_credits: int
    converted_days: int
    settlement_reason: str
