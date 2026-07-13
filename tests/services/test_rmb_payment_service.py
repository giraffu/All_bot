from decimal import Decimal
from urllib.parse import parse_qs, urlparse

import pytest

from src.services.rmb_payment_service import RMBPaymentService


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


class _FakeClientSession:
    def __init__(self, captured, payload):
        self._captured = captured
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def get(self, url, timeout):
        self._captured["url"] = url
        self._captured["timeout"] = timeout
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

    query = parse_qs(urlparse(captured["url"]).query)
    assert query["money"] == ["0.30"]
