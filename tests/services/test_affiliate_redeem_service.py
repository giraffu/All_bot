from decimal import Decimal

import pytest

from src.services.affiliate_redeem_service import (
    calculate_redeem_credits,
    normalize_redeem_amount_usdt,
)


def test_normalize_redeem_amount_usdt_keeps_four_decimals():
    assert normalize_redeem_amount_usdt(Decimal("1.23456")) == Decimal("1.2346")


def test_affiliate_redeem_request_accepts_extra_decimals_and_normalizes():
    from src.web_api.schemas.affiliate_redeem_schema import AffiliateCreditsRedeemRequest

    payload = AffiliateCreditsRedeemRequest(
        amount_usdt=Decimal("1.23456"),
        idempotency_key="idem-normalized",
    )

    assert payload.amount_usdt == Decimal("1.2346")


def test_calculate_redeem_credits_uses_round_half_up():
    assert calculate_redeem_credits(Decimal("1.0056")) == 91


def test_calculate_redeem_credits_rejects_tiny_amount():
    with pytest.raises(ValueError, match="too small"):
        calculate_redeem_credits(Decimal("0.0001"))
