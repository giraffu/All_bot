from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services import rmb_payment_provider_service as provider_service


def test_selects_alipay_direct_only_for_enabled_allowlisted_alipay_user(monkeypatch):
    monkeypatch.setenv("ALIPAY_DIRECT_ENABLED", "true")
    user = SimpleNamespace(alipay_direct_enabled=True)

    assert (
        provider_service.select_rmb_payment_provider(user=user, pay_type="alipay")
        == provider_service.ALIPAY_DIRECT
    )
    assert (
        provider_service.select_rmb_payment_provider(user=user, pay_type="wxpay")
        == provider_service.HUANYUY
    )


@pytest.mark.parametrize(
    ("global_value", "allowlisted"),
    [("false", True), ("true", False), (None, True)],
)
def test_selects_huanyuy_when_direct_route_is_not_fully_enabled(
    monkeypatch, global_value, allowlisted
):
    if global_value is None:
        monkeypatch.delenv("ALIPAY_DIRECT_ENABLED", raising=False)
    else:
        monkeypatch.setenv("ALIPAY_DIRECT_ENABLED", global_value)

    assert (
        provider_service.select_rmb_payment_provider(
            user=SimpleNamespace(alipay_direct_enabled=allowlisted),
            pay_type="alipay",
        )
        == provider_service.HUANYUY
    )


@pytest.mark.asyncio
async def test_direct_provider_wraps_desktop_and_mobile_in_the_same_checkout(monkeypatch):
    direct = SimpleNamespace(config=SimpleNamespace())
    checkout = AsyncMock(
        side_effect=[
            {"code": 1, "data": {"payurl": "https://web.example/pay/alipay/one"}},
            {"code": 1, "data": {"payurl": "https://web.example/pay/alipay/two"}},
        ]
    )
    monkeypatch.setattr(provider_service, "get_alipay_direct_service", lambda: direct)
    monkeypatch.setattr(
        provider_service,
        "create_alipay_checkout_payment",
        checkout,
    )

    await provider_service.create_rmb_payment_url(
        provider=provider_service.ALIPAY_DIRECT,
        out_trade_no="ORDER-1",
        public_order_id="bo_1",
        plan_name="Plan",
        amount="0.01",
        pay_type="alipay",
        client_type="desktop",
        return_url="https://web.example/billing",
    )
    await provider_service.create_rmb_payment_url(
        provider=provider_service.ALIPAY_DIRECT,
        out_trade_no="ORDER-2",
        public_order_id="bo_2",
        plan_name="Plan",
        amount="0.01",
        pay_type="alipay",
        client_type="mobile",
        return_url="https://web.example/billing",
    )

    assert checkout.await_count == 2
    assert checkout.await_args_list[0].kwargs == {
        "alipay_service": direct,
        "out_trade_no": "ORDER-1",
        "public_order_id": "bo_1",
        "subject": "Plan",
        "amount": "0.01",
    }
    assert checkout.await_args_list[1].kwargs["public_order_id"] == "bo_2"


def test_mobile_user_agent_detection_is_conservative():
    assert provider_service.detect_rmb_client_type("Mozilla/5.0 (iPhone)") == "mobile"
    assert provider_service.detect_rmb_client_type("Mozilla/5.0 (Linux; Android 14)") == "mobile"
    assert provider_service.detect_rmb_client_type("Mozilla/5.0 (X11; Linux x86_64)") == "desktop"
