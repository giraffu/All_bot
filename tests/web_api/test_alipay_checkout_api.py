from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from unittest.mock import ANY, AsyncMock

from src.services.alipay_checkout_service import AlipayCheckoutSession
from src.web_api.routers import payment as payment_router
from src.web_api.services.alipay_checkout_api_service import (
    get_alipay_checkout_launch_url,
    get_alipay_checkout_payload,
)


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _FakeDb:
    def __init__(self, order):
        self.order = order

    async def execute(self, _stmt):
        return _ScalarResult(self.order)


def _session():
    return AlipayCheckoutSession(
        public_order_id="bo_public_1",
        out_trade_no="RMB_100_1_123",
        subject="内门弟子（30天）",
        amount="30.00",
        pay_url="https://openapi.alipay.test/gateway.do?signed=value",
        created_at="2026-08-25T12:40:17+00:00",
    )


def _order(**overrides):
    values = {
        "business_order_id": "bo_public_1",
        "order_id": "RMB_100_1_123",
        "payment_channel": "RMB",
        "payment_provider": "ALIPAY_DIRECT",
        "final_price": Decimal("30.00"),
        "status": "PENDING",
        "internal_user_id": 999,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_public_checkout_payload_exposes_only_safe_order_display_fields():
    async def load_session(_token):
        return _session()

    payload = await get_alipay_checkout_payload(
        db=_FakeDb(_order()),
        token="checkout-token",
        session_loader=load_session,
    )

    assert payload == {
        "code": 0,
        "message": "success",
        "data": {
            "order_id": "bo_public_1",
            "subject": "内门弟子（30天）",
            "amount": "30.00",
            "status": "PENDING",
            "created_at": "2026-08-25T12:40:17+00:00",
        },
    }
    assert "pay_url" not in str(payload)
    assert "999" not in str(payload)


@pytest.mark.asyncio
async def test_public_checkout_launch_returns_only_the_bound_alipay_wap_url():
    async def load_session(_token):
        return _session()

    pay_url = await get_alipay_checkout_launch_url(
        db=_FakeDb(_order()),
        token="checkout-token",
        session_loader=load_session,
        gateway_url="https://openapi.alipay.test/gateway.do",
    )

    assert pay_url == "https://openapi.alipay.test/gateway.do?signed=value"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "order",
    [
        _order(payment_provider="HUANYUY"),
        _order(final_price=Decimal("30.01")),
        _order(status="FAILED"),
    ],
)
async def test_public_checkout_fails_closed_for_a_mismatched_or_failed_order(order):
    async def load_session(_token):
        return _session()

    with pytest.raises(HTTPException) as exc_info:
        await get_alipay_checkout_launch_url(
            db=_FakeDb(order),
            token="checkout-token",
            session_loader=load_session,
            gateway_url="https://openapi.alipay.test/gateway.do",
        )

    assert exc_info.value.status_code in {404, 409}


@pytest.mark.asyncio
async def test_public_checkout_reports_an_expired_session_without_querying_an_order():
    async def load_session(_token):
        return None

    with pytest.raises(HTTPException) as exc_info:
        await get_alipay_checkout_payload(
            db=_FakeDb(None),
            token="checkout-token",
            session_loader=load_session,
        )

    assert exc_info.value.status_code == 410
    assert exc_info.value.detail["reason"] == "ALIPAY_CHECKOUT_EXPIRED"


@pytest.mark.asyncio
async def test_public_checkout_maps_a_malformed_bearer_token_to_not_found():
    async def load_session(_token):
        raise ValueError("invalid token")

    with pytest.raises(HTTPException) as exc_info:
        await get_alipay_checkout_payload(
            db=_FakeDb(None),
            token="bad",
            session_loader=load_session,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["reason"] == "ALIPAY_CHECKOUT_NOT_FOUND"


@pytest.mark.asyncio
async def test_launch_route_uses_a_no_store_temporary_redirect(monkeypatch):
    launch = AsyncMock(
        return_value="https://openapi.alipay.test/gateway.do?signed=value"
    )
    monkeypatch.setattr(payment_router, "get_alipay_checkout_launch_url", launch)

    response = await payment_router.launch_alipay_checkout(
        "checkout-token",
        db=object(),
    )

    assert response.status_code == 302
    assert response.headers["location"].startswith("https://openapi.alipay.test/")
    assert response.headers["cache-control"] == "no-store"
    launch.assert_awaited_once_with(db=ANY, token="checkout-token")
