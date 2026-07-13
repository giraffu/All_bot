from decimal import Decimal

import pytest

from src.services.affiliate_redeem_service import (
    calculate_redeem_credits,
    normalize_redeem_amount_usdt,
)


def test_normalize_redeem_amount_usdt_keeps_four_decimals():
    assert normalize_redeem_amount_usdt(Decimal("1.23456")) == Decimal("1.2346")


def test_affiliate_redeem_request_rejects_non_package_amount():
    from src.web_api.schemas.affiliate_redeem_schema import AffiliateCreditsRedeemRequest

    with pytest.raises(ValueError, match="固定套餐"):
        AffiliateCreditsRedeemRequest(
            amount_usdt=Decimal("1.23456"),
            idempotency_key="idem-invalid-package",
        )


def test_calculate_redeem_credits_uses_fixed_packages():
    assert calculate_redeem_credits(Decimal("1.0000")) == 130
    assert calculate_redeem_credits(Decimal("3.0000")) == 390
    assert calculate_redeem_credits(Decimal("6.0000")) == 780
    assert calculate_redeem_credits(Decimal("10.0000")) == 1800
    assert calculate_redeem_credits(Decimal("15.0000")) == 2700
    assert calculate_redeem_credits(Decimal("20.0000")) == 4000


def test_calculate_redeem_credits_rejects_unsupported_package():
    with pytest.raises(ValueError, match="固定套餐"):
        calculate_redeem_credits(Decimal("2.0000"))
