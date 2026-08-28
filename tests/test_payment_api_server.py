from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from src import payment_api_server
from src.services.rmb_payment_service import RMBPaymentService


@pytest.mark.asyncio
async def test_register_payment_api_providers_invokes_provider_setup(monkeypatch):
    ensure_mock = Mock()
    monkeypatch.setattr(
        payment_api_server,
        "ensure_billing_core_providers_registered",
        ensure_mock,
    )

    await payment_api_server.register_payment_api_providers()

    ensure_mock.assert_called_once_with()


@pytest.mark.asyncio
async def test_payment_api_lifespan_starts_enabled_reconciler(monkeypatch):
    run_forever = AsyncMock()
    reconciler = SimpleNamespace(
        run_forever=run_forever,
        payment_providers=("ALIPAY_DIRECT",),
    )
    monkeypatch.setattr(
        payment_api_server,
        "build_rmb_payment_reconciler_if_enabled",
        Mock(return_value=reconciler),
    )
    monkeypatch.setattr(
        payment_api_server,
        "register_payment_api_providers",
        AsyncMock(),
    )

    async with payment_api_server.payment_api_lifespan(payment_api_server.app):
        await __import__("asyncio").sleep(0)

    run_forever.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_payment_health_reports_reconciler_state(monkeypatch):
    monkeypatch.setattr(payment_api_server.app.state, "reconciler_enabled", True)
    monkeypatch.setattr(
        payment_api_server.app.state,
        "huanyuy_reconciliation_enabled",
        False,
    )
    monkeypatch.setattr(
        payment_api_server.app.state,
        "alipay_direct_reconciliation_enabled",
        True,
    )

    transport = httpx.ASGITransport(app=payment_api_server.app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://payment.test",
    ) as client:
        response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "rmb_reconciliation_enabled": True,
        "huanyuy_reconciliation_enabled": False,
        "alipay_direct_reconciliation_enabled": True,
        "alipay_direct_configured": False,
    }


def _signed_callback_params(**overrides):
    params = {
        "pid": "merchant-1",
        "type": "alipay",
        "out_trade_no": "RMB-ORDER-1",
        "trade_no": "gateway-trade-1",
        "money": "30.00",
        "trade_status": "TRADE_SUCCESS",
        "sign_type": "MD5",
    }
    params.update(overrides)
    params["sign"] = RMBPaymentService.generate_sign(params, "callback-secret")
    return params


async def _request(method: str, *, params=None, data=None):
    transport = httpx.ASGITransport(app=payment_api_server.app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://payment.test",
    ) as client:
        return await client.request(method, "/api/pay/notify/huanyuy", params=params, data=data)


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["GET", "POST"])
async def test_huanyuy_notify_accepts_signed_get_and_post_and_returns_exact_success(
    monkeypatch,
    method,
):
    result = SimpleNamespace(status="success")
    fulfill_mock = AsyncMock(return_value=result)
    schedule_mock = Mock()
    monkeypatch.setattr(payment_api_server, "HUANYUY_PID", "merchant-1")
    monkeypatch.setattr(payment_api_server, "HUANYUY_KEY", "callback-secret")
    monkeypatch.setattr(payment_api_server, "fulfill_rmb_order", fulfill_mock)
    monkeypatch.setattr(
        payment_api_server,
        "_callback_provider_is_valid",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        payment_api_server,
        "schedule_payment_notification",
        schedule_mock,
    )

    payload = _signed_callback_params()
    response = await _request(
        method,
        params=payload if method == "GET" else None,
        data=payload if method == "POST" else None,
    )

    assert response.status_code == 200
    assert response.text == "SUCCESS"
    assert response.headers["content-type"].startswith("text/plain")
    fulfill_mock.assert_awaited_once_with(
        "RMB-ORDER-1",
        "gateway-trade-1",
        "30.00",
        source="rmb_payment_callback",
    )
    schedule_mock.assert_called_once_with(result)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("overrides", "configured_pid", "configured_key"),
    [
        ({"pid": "other-merchant"}, "merchant-1", "callback-secret"),
        ({"sign_type": "RSA"}, "merchant-1", "callback-secret"),
        ({"trade_status": "WAIT_BUYER_PAY"}, "merchant-1", "callback-secret"),
        ({"trade_no": ""}, "merchant-1", "callback-secret"),
        ({"sign": "bad-signature"}, "merchant-1", "callback-secret"),
        ({}, None, "callback-secret"),
        ({}, "merchant-1", None),
    ],
)
async def test_huanyuy_notify_rejects_invalid_or_unconfigured_callbacks(
    monkeypatch,
    overrides,
    configured_pid,
    configured_key,
):
    fulfill_mock = AsyncMock()
    monkeypatch.setattr(payment_api_server, "HUANYUY_PID", configured_pid)
    monkeypatch.setattr(payment_api_server, "HUANYUY_KEY", configured_key)
    monkeypatch.setattr(payment_api_server, "fulfill_rmb_order", fulfill_mock)
    monkeypatch.setattr(
        payment_api_server,
        "_callback_provider_is_valid",
        AsyncMock(return_value=True),
    )

    payload = _signed_callback_params()
    payload.update(overrides)
    if "sign" not in overrides:
        payload["sign"] = RMBPaymentService.generate_sign(payload, "callback-secret")

    response = await _request("GET", params=payload)

    assert response.status_code == 200
    assert response.text == "fail"
    fulfill_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_huanyuy_notify_acknowledges_duplicate_without_scheduling_notification(
    monkeypatch,
):
    fulfill_mock = AsyncMock(return_value=SimpleNamespace(status="noop"))
    schedule_mock = Mock()
    monkeypatch.setattr(payment_api_server, "HUANYUY_PID", "merchant-1")
    monkeypatch.setattr(payment_api_server, "HUANYUY_KEY", "callback-secret")
    monkeypatch.setattr(payment_api_server, "fulfill_rmb_order", fulfill_mock)
    monkeypatch.setattr(
        payment_api_server,
        "_callback_provider_is_valid",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        payment_api_server,
        "schedule_payment_notification",
        schedule_mock,
    )

    response = await _request("GET", params=_signed_callback_params())

    assert response.text == "SUCCESS"
    schedule_mock.assert_not_called()


@pytest.mark.asyncio
async def test_huanyuy_post_accepts_callback_parameters_in_query_string(monkeypatch):
    fulfill_mock = AsyncMock(return_value=SimpleNamespace(status="noop"))
    monkeypatch.setattr(payment_api_server, "HUANYUY_PID", "merchant-1")
    monkeypatch.setattr(payment_api_server, "HUANYUY_KEY", "callback-secret")
    monkeypatch.setattr(payment_api_server, "fulfill_rmb_order", fulfill_mock)
    monkeypatch.setattr(
        payment_api_server,
        "_callback_provider_is_valid",
        AsyncMock(return_value=True),
    )

    response = await _request("POST", params=_signed_callback_params())

    assert response.text == "SUCCESS"
    fulfill_mock.assert_awaited_once()
