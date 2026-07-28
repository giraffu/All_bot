from decimal import Decimal

import pytest

from src.services.rmb_payment_service import (
    RMBOrderQueryStatus,
    RMBPaymentService,
)


@pytest.fixture(autouse=True)
def _gateway_config(monkeypatch):
    monkeypatch.setattr(
        "src.services.rmb_payment_service.HUANYUY_GATEWAY",
        "https://gateway.test/submit.php",
    )
    monkeypatch.setattr(
        "src.services.rmb_payment_service.HUANYUY_PID",
        "merchant-1",
    )
    monkeypatch.setattr(
        "src.services.rmb_payment_service.HUANYUY_KEY",
        "gateway-secret",
    )
    monkeypatch.setattr(
        "src.services.rmb_payment_service.HUANYUY_NOTIFY_URL",
        "https://payment.test/notify",
    )
    monkeypatch.setattr(
        "src.services.rmb_payment_service.HUANYUY_RETURN_URL",
        "https://payment.test/result",
    )
    monkeypatch.setattr(
        "src.services.rmb_payment_service.HUANYUY_SITENAME",
        "AllBot",
    )


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.status = 200

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self, content_type=None):
        return self._payload

    async def text(self):
        return str(self._payload)

    async def read(self):
        return str(self._payload).encode()


class _FakeClientSession:
    def __init__(self, captured, payload):
        self._captured = captured
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def post(self, url, data, timeout):
        self._captured["url"] = url
        self._captured["data"] = data
        self._captured["timeout"] = timeout
        return _FakeResponse(self._payload)

    def get(self, url, params, timeout, headers):
        self._captured["url"] = url
        self._captured["params"] = params
        self._captured["timeout"] = timeout
        self._captured["headers"] = headers
        return _FakeResponse(self._payload)


@pytest.mark.asyncio
async def test_create_payment_url_formats_decimal_amount_without_float_rounding_noise(
    monkeypatch,
):
    captured = {}

    monkeypatch.setattr(
        "src.services.rmb_payment_service.aiohttp.ClientSession",
        lambda: _FakeClientSession(captured, {"code": 1, "payurl": "https://pay.test"}),
    )

    result = await RMBPaymentService.create_payment_url(
        out_trade_no="RMB-ORDER-1",
        plan_name="Plan A",
        amount=Decimal("0.30"),
        pay_type="alipay",
    )

    assert result == {"code": 1, "payurl": "https://pay.test"}
    assert captured["timeout"] == 15
    assert captured["url"] == "https://gateway.test/submit.php"
    assert captured["data"]["money"] == "0.30"
    assert captured["data"]["return_type"] == "json"


@pytest.mark.asyncio
async def test_create_payment_url_does_not_log_signed_payload(monkeypatch, caplog):
    captured = {}
    monkeypatch.setattr(
        "src.services.rmb_payment_service.aiohttp.ClientSession",
        lambda: _FakeClientSession(
            captured,
            {"code": 1, "payurl": "https://pay.test/sensitive"},
        ),
    )

    await RMBPaymentService.create_payment_url(
        out_trade_no="RMB-SENSITIVE-ORDER",
        plan_name="Plan A",
        amount="30.00",
    )

    rendered = caplog.text
    assert "RMB-SENSITIVE-ORDER" not in rendered
    assert "https://pay.test/sensitive" not in rendered
    assert "sign" not in rendered.lower()


@pytest.mark.asyncio
async def test_query_order_parses_paid_order_with_strict_identity_and_amount(
    monkeypatch,
):
    captured = {}
    monkeypatch.setattr(
        "src.services.rmb_payment_service.aiohttp.ClientSession",
        lambda: _FakeClientSession(
            captured,
            {
                "code": 1,
                "status": 1,
                "out_trade_no": "RMB-ORDER-1",
                "trade_no": "gateway-1",
                "money": "30.00",
            },
        ),
    )

    result = await RMBPaymentService.query_order(
        out_trade_no="RMB-ORDER-1",
        expected_amount=Decimal("30.00"),
        query_url="https://gateway.test/order-query",
    )

    assert result.status == RMBOrderQueryStatus.PAID
    assert result.external_trade_no == "gateway-1"
    assert captured["params"]["act"] == "order"
    assert captured["params"]["out_trade_no"] == "RMB-ORDER-1"
    assert captured["timeout"] == 5


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {
            "code": 1,
            "status": 1,
            "out_trade_no": "OTHER",
            "trade_no": "gateway-1",
            "money": "30.00",
        },
        {
            "code": 1,
            "status": 1,
            "out_trade_no": "RMB-ORDER-1",
            "trade_no": "gateway-1",
            "money": "29.99",
        },
        {
            "code": 1,
            "status": 1,
            "out_trade_no": "RMB-ORDER-1",
            "money": "30.00",
        },
    ],
)
async def test_query_order_fails_closed_on_paid_response_mismatch(
    monkeypatch,
    payload,
):
    monkeypatch.setattr(
        "src.services.rmb_payment_service.aiohttp.ClientSession",
        lambda: _FakeClientSession({}, payload),
    )

    with pytest.raises(ValueError):
        await RMBPaymentService.query_order(
            out_trade_no="RMB-ORDER-1",
            expected_amount="30.00",
            query_url="https://gateway.test/order-query",
        )


@pytest.mark.asyncio
async def test_query_order_returns_not_paid_without_requiring_trade_number(monkeypatch):
    monkeypatch.setattr(
        "src.services.rmb_payment_service.aiohttp.ClientSession",
        lambda: _FakeClientSession({}, {"code": 1, "status": 0}),
    )

    result = await RMBPaymentService.query_order(
        out_trade_no="RMB-ORDER-1",
        expected_amount="30.00",
        query_url="https://gateway.test/order-query",
    )

    assert result.status == RMBOrderQueryStatus.NOT_PAID
    assert result.external_trade_no is None


@pytest.mark.asyncio
async def test_query_order_fails_closed_on_non_200_response(monkeypatch):
    response = _FakeResponse({"code": 1, "status": 1})
    response.status = 404
    monkeypatch.setattr(
        "src.services.rmb_payment_service.aiohttp.ClientSession",
        lambda: _FakeClientSession({}, response._payload),
    )
    original_get = _FakeClientSession.get

    def _get(self, url, params, timeout, headers):
        original_get(self, url, params, timeout, headers)
        return response

    monkeypatch.setattr(_FakeClientSession, "get", _get)

    with pytest.raises(ValueError, match="HTTP 404"):
        await RMBPaymentService.query_order(
            out_trade_no="RMB-ORDER-1",
            expected_amount="30.00",
            query_url="https://gateway.test/order-query",
        )
