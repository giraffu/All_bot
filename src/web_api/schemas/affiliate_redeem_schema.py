from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


class AffiliateCreditsRedeemRequest(BaseModel):
    amount_usdt: Decimal = Field(gt=0, max_digits=10)
    idempotency_key: str = Field(min_length=1, max_length=128)

    @field_validator("amount_usdt")
    @classmethod
    def normalize_amount_usdt(cls, value: Decimal) -> Decimal:
        normalized = Decimal(str(value)).quantize(Decimal("0.0001"))
        if normalized <= 0:
            raise ValueError("兑换金额必须大于 0")
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
