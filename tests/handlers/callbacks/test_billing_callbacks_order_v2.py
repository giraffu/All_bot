from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.handlers.callbacks import billing_callbacks


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeSession:
    def __init__(self, execute_results):
        self.execute_results = list(execute_results)
        self.added = []
        self.commit = AsyncMock()

    async def execute(self, stmt):
        if not self.execute_results:
            raise AssertionError("unexpected execute call")
        return _ScalarResult(self.execute_results.pop(0))

    def add(self, obj):
        self.added.append(obj)


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_buy_star_plan_callback_creates_pending_order_with_order_v2_payload(
    monkeypatch,
):
    plan = SimpleNamespace(
        id=1,
        name="Stars Plan",
        identity_name="内门弟子",
        duration_days=30,
        reward_credits=100,
        price_stars=100,
    )
    session = _FakeSession([plan])
    query = SimpleNamespace(
        data="buy_star_plan_1",
        from_user=SimpleNamespace(id=12345),
        message=SimpleNamespace(chat_id=12345),
    )
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(bot=SimpleNamespace(send_invoice=AsyncMock()))

    monkeypatch.setattr(
        billing_callbacks, "AsyncSessionLocal", lambda: _SessionContext(session)
    )
    monkeypatch.setattr(
        billing_callbacks, "safe_answer_query", AsyncMock()
    )
    monkeypatch.setattr(
        billing_callbacks, "get_or_create_user_by_telegram", AsyncMock(return_value=(SimpleNamespace(id=2002), False))
    )
    monkeypatch.setattr(
        billing_callbacks, "is_order_v2_enabled", lambda: True
    )
    monkeypatch.setattr(
        billing_callbacks, "generate_business_order_id", lambda: "bo_stars_1"
    )

    await billing_callbacks.buy_star_plan_callback(update, context)

    created_order = session.added[0]
    assert created_order.business_order_id == "bo_stars_1"
    assert created_order.internal_user_id == 2002
    assert created_order.status == "PENDING"
    context.bot.send_invoice.assert_awaited_once()
    assert (
        context.bot.send_invoice.await_args.kwargs["payload"] == "ORDER_V2:bo_stars_1"
    )
