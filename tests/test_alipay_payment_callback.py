from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src import payment_callback_router
from src.services.rmb_payment_service import RMBOrderQueryResult, RMBOrderQueryStatus


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
    query_order = AsyncMock(
        return_value=RMBOrderQueryResult(
            status=RMBOrderQueryStatus.NOT_PAID,
            out_trade_no="ORDER-1",
        )
    )
    monkeypatch.setattr(
        payment_callback_router,
        "get_alipay_direct_service",
        lambda: SimpleNamespace(
            verify_callback=lambda _params: False,
            query_order=query_order,
        ),
    )
    monkeypatch.setattr(
        payment_callback_router,
        "load_alipay_callback_order",
        AsyncMock(return_value=None),
    )
    fulfill = AsyncMock()
    monkeypatch.setattr(payment_callback_router, "fulfill_rmb_order", fulfill)

    response = await payment_callback_router.alipay_notify(_Request({"sign": "bad"}))

    assert response.body == b"fail"
    query_order.assert_not_awaited()
    fulfill.assert_not_awaited()


@pytest.mark.asyncio
async def test_alipay_callback_uses_signed_query_fallback_without_trusting_callback(
    monkeypatch,
):
    query_order = AsyncMock(
        return_value=RMBOrderQueryResult(
            status=RMBOrderQueryStatus.PAID,
            out_trade_no="ORDER-1",
            external_trade_no="SIGNED-TRADE-1",
            paid_amount="30.00",
        )
    )
    service = SimpleNamespace(
        verify_callback=lambda _params: False,
        query_order=query_order,
    )
    monkeypatch.setattr(
        payment_callback_router,
        "get_alipay_direct_service",
        lambda: service,
    )
    monkeypatch.setattr(
        payment_callback_router,
        "load_alipay_callback_order",
        AsyncMock(
            return_value=SimpleNamespace(
                payment_channel="RMB",
                payment_provider="ALIPAY_DIRECT",
                final_price="30.00",
            )
        ),
    )
    fulfill = AsyncMock(return_value=SimpleNamespace(status="success"))
    monkeypatch.setattr(payment_callback_router, "fulfill_rmb_order", fulfill)
    schedule = AsyncMock()
    monkeypatch.setattr(payment_callback_router, "deliver_notification", schedule)

    response = await payment_callback_router.alipay_notify(
        _Request(
            {
                "out_trade_no": "ORDER-1",
                "trade_no": "FORGED-CALLBACK-TRADE",
                "total_amount": "0.01",
                "trade_status": "TRADE_SUCCESS",
                "sign": "bad",
            }
        )
    )

    assert response.body == b"success"
    query_order.assert_awaited_once_with(
        out_trade_no="ORDER-1",
        expected_amount="30.00",
    )
    fulfill.assert_awaited_once_with(
        "ORDER-1",
        "SIGNED-TRADE-1",
        "30.00",
        source="alipay_direct_callback_query_fallback",
    )
    schedule.assert_awaited_once()


@pytest.mark.asyncio
async def test_alipay_callback_query_fallback_fails_closed_when_query_is_not_paid(
    monkeypatch,
):
    service = SimpleNamespace(
        verify_callback=lambda _params: False,
        query_order=AsyncMock(
            return_value=RMBOrderQueryResult(
                status=RMBOrderQueryStatus.NOT_PAID,
                out_trade_no="ORDER-1",
            )
        ),
    )
    monkeypatch.setattr(
        payment_callback_router,
        "get_alipay_direct_service",
        lambda: service,
    )
    monkeypatch.setattr(
        payment_callback_router,
        "load_alipay_callback_order",
        AsyncMock(
            return_value=SimpleNamespace(
                payment_channel="RMB",
                payment_provider="ALIPAY_DIRECT",
                final_price="30.00",
            )
        ),
    )
    fulfill = AsyncMock()
    monkeypatch.setattr(payment_callback_router, "fulfill_rmb_order", fulfill)

    response = await payment_callback_router.alipay_notify(
        _Request(
            {
                "out_trade_no": "ORDER-1",
                "trade_status": "TRADE_SUCCESS",
                "sign": "bad",
            }
        )
    )

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
