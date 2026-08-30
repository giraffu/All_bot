from datetime import datetime
from types import SimpleNamespace

import pytest

from src.database.models import Order, RMBPaymentReconciliationJob
from src.services import telegram_billing_service


class _FakeSession:
    def __init__(self):
        self.added = []
        self.flushed = False
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def add(self, value):
        self.added.append(value)
        if isinstance(value, Order):
            value.id = 101

    async def flush(self):
        self.flushed = True

    async def commit(self):
        self.committed = True


@pytest.mark.asyncio
async def test_create_rmb_pending_order_creates_future_reconciliation_job_in_transaction(
    monkeypatch,
):
    session = _FakeSession()
    monkeypatch.setattr(
        telegram_billing_service,
        "AsyncSessionLocal",
        lambda: session,
    )
    plan = SimpleNamespace(
        id=7,
        price_rmb="30.00",
        name="Plan",
        reward_credits=100,
        duration_days=30,
        identity_name="内门弟子",
    )

    started_at = datetime.now()
    order, _public_id = await telegram_billing_service.create_rmb_pending_order(
        internal_user_id=55,
        plan=plan,
        out_trade_no="RMB-ORDER-1",
        payment_provider="ALIPAY_DIRECT",
        pay_type="alipay",
    )

    assert session.flushed is True
    assert session.committed is True
    assert isinstance(session.added[0], Order)
    assert isinstance(session.added[1], RMBPaymentReconciliationJob)
    assert session.added[1].order_id == order.id
    assert session.added[1].status == "pending"
    assert 29 <= (session.added[1].next_attempt_at - started_at).total_seconds() <= 31
    assert order.payment_provider == "ALIPAY_DIRECT"
    assert order.settlement_snapshot["rmb_pay_type"] == "alipay"
