from decimal import Decimal

from src.domain_config.membership_plans import CANONICAL_MEMBERSHIP_PLAN_ROWS


def test_membership_and_credit_plans_use_requested_usdt_ton_prices():
    prices_by_id = {
        int(plan["id"]): Decimal(str(plan["price_usdt"]))
        for plan in CANONICAL_MEMBERSHIP_PLAN_ROWS
    }

    assert prices_by_id == {
        1: Decimal("4.50"),
        2: Decimal("10.00"),
        3: Decimal("17.00"),
        5: Decimal("4.50"),
        6: Decimal("10.00"),
        7: Decimal("17.00"),
    }
