from decimal import Decimal

import pytest

from src.services.affiliate_redeem_rules import (
    normalize_usdt_payout_address,
    normalize_usdt_redeem_amount,
)


def test_usdt_redeem_amount_accepts_minimum_and_quantizes_four_decimals():
    assert normalize_usdt_redeem_amount(Decimal("5")) == Decimal("5.0000")
    assert normalize_usdt_redeem_amount(Decimal("5.12344")) == Decimal("5.1234")


@pytest.mark.parametrize("amount", ["0", "4.9999", "-1"])
def test_usdt_redeem_amount_rejects_values_below_minimum(amount):
    with pytest.raises(ValueError, match="5.0000"):
        normalize_usdt_redeem_amount(Decimal(amount))


def test_usdt_payout_address_is_normalized_to_non_bounceable_mainnet():
    assert (
        normalize_usdt_payout_address(
            "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs"
        )
        == "UQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_p0p"
    )


@pytest.mark.parametrize("address", ["", "not-a-ton-address"])
def test_usdt_payout_address_rejects_invalid_value(address):
    with pytest.raises(ValueError, match="TON"):
        normalize_usdt_payout_address(address)
