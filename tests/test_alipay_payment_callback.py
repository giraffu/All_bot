from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src import payment_callback_router


class _Request:
    def __init__(self, params):
        self._params = params

    async def form(self):
        return self._params


class _Session:
    def __init__(self, order):
        self.order = order

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def execute(self, _statement):
        return SimpleNamespace(scalar_one_or_none=lambda: self.order)


@pytest.mark.asyncio
async def test_alipay_callback_acknowledges_success_and_duplicate(monkeypatch):
    service = SimpleNamespace(verify_callback=lambda _params: True)
    monkeypatch.setattr(
        payment_callback_router,
        "get_alipay_direct_service",
        lambda: service,
    )
    monkeypatch.setattr(
        payment_callback_router,
        "validate_alipay_callback_order",
        AsyncMock(return_value=True),
    )
    fulfill = AsyncMock(
        side_effect=[SimpleNamespace(status="success"), SimpleNamespace(status="noop")]
    )
    monkeypatch.setattr(payment_callback_router, "fulfill_rmb_order", fulfill)
    schedule = AsyncMock()
    monkeypatch.setattr(payment_callback_router, "deliver_notification", schedule)
    request = _Request(
        {
            "out_trade_no": "ORDER-1",
            "trade_no": "TRADE-1",
            "total_amount": "0.01",
            "sign": "signed",
        }
    )

    first = await payment_callback_router.alipay_notify(request)
    second = await payment_callback_router.alipay_notify(request)

    assert first.body == b"success"
    assert second.body == b"success"
    assert fulfill.await_count == 2
    schedule.assert_awaited_once()


@pytest.mark.asyncio
async def test_alipay_callback_rejects_wrong_signature_or_order_provider(monkeypatch):
    monkeypatch.setattr(
        payment_callback_router,
        "get_alipay_direct_service",
        lambda: SimpleNamespace(verify_callback=lambda _params: False),
    )
    fulfill = AsyncMock()
    monkeypatch.setattr(payment_callback_router, "fulfill_rmb_order", fulfill)

    response = await payment_callback_router.alipay_notify(_Request({"sign": "bad"}))

    assert response.body == b"fail"
    fulfill.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "amount", "expected"),
    [
        ("ALIPAY_DIRECT", "0.01", True),
        ("HUANYUY", "0.01", False),
        ("ALIPAY_DIRECT", "0.02", False),
    ],
)
async def test_callback_order_validation_requires_direct_provider_and_exact_amount(
    monkeypatch,
    provider,
    amount,
    expected,
):
    order = SimpleNamespace(
        payment_channel="RMB",
        payment_provider=provider,
        final_price="0.01",
    )
    monkeypatch.setattr(
        payment_callback_router,
        "AsyncSessionLocal",
        lambda: _Session(order),
    )

    result = await payment_callback_router.validate_alipay_callback_order(
        {"out_trade_no": "ORDER-1", "total_amount": amount}
    )

    assert result is expected
