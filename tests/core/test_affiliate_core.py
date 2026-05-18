from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
import asyncio

import pytest
from sqlalchemy.dialects import postgresql

from src.constants import COMMISSION_RATE
from src.core import affiliate_core
from src.database.models import Order, Referral


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _TrackingSession:
    def __init__(self, execute_results=None):
        self.execute_results = list(execute_results or [])
        self.statements = []
        self.flush_calls = 0

    async def execute(self, stmt):
        self.statements.append(stmt)
        if not self.execute_results:
            raise AssertionError("unexpected execute call")
        return _ScalarResult(self.execute_results.pop(0))

    async def flush(self):
        self.flush_calls += 1


class _ConcurrentState:
    def __init__(self, referral):
        self.referral = referral
        self.lock = asyncio.Lock()
        self.first_lock_acquired = asyncio.Event()
        self.winner_order_id = None


class _ConcurrentReferralSession:
    def __init__(self, state: _ConcurrentState):
        self.state = state
        self.execute_call_count = 0

    async def execute(self, _stmt):
        self.execute_call_count += 1
        if self.execute_call_count == 1:
            await self.state.lock.acquire()
            self.state.first_lock_acquired.set()
            return _ScalarResult(self.state.referral)
        if self.execute_call_count == 2:
            return _ScalarResult(self.state.winner_order_id)
        raise AssertionError("unexpected execute call")

    async def flush(self):
        return None


def _build_order(**overrides):
    payload = {
        "id": 123,
        "order_id": "ORD-123",
        "telegram_id": 2002,
        "plan_id": 1,
        "original_price": Decimal("10.00"),
        "final_price": Decimal("10.00"),
        "status": "SUCCESS",
        "tx_hash": "tx-123",
        "commission_usdt": Decimal("0.0000"),
        "payment_channel": "TON",
        "paid_at": datetime(2026, 5, 18, 12, 0, 0),
    }
    payload.update(overrides)
    return Order(**payload)


def _build_referral(**overrides):
    payload = {
        "id": 10,
        "inviter_id": 1001,
        "invitee_id": 2002,
    }
    payload.update(overrides)
    return Referral(**payload)


@pytest.mark.asyncio
async def test_calculate_and_set_commission_for_paid_order_first_paid_order(monkeypatch):
    async def _fake_rates():
        return {
            "rmb_to_usdt": Decimal("0.15"),
            "ton_to_usdt": Decimal("1.40"),
            "stars_to_usdt": Decimal("0.013"),
        }

    monkeypatch.setattr(affiliate_core, "get_exchange_rates", _fake_rates)

    referral = _build_referral()
    order = _build_order(payment_channel="TON", final_price=Decimal("10.00"))
    session = _TrackingSession(execute_results=[referral, None])

    locked_referral = await affiliate_core.calculate_and_set_commission_for_paid_order(
        session, order
    )

    expected = (
        Decimal("10.00") * Decimal("1.40") * Decimal(str(COMMISSION_RATE))
    ).quantize(affiliate_core.COMMISSION_QUANT, rounding=ROUND_HALF_UP)
    assert locked_referral is referral
    assert order.commission_usdt == expected
    assert len(session.statements) == 2


@pytest.mark.asyncio
async def test_calculate_and_set_commission_for_paid_order_non_first_order_gets_zero():
    referral = _build_referral()
    order = _build_order()
    session = _TrackingSession(execute_results=[referral, 999])

    locked_referral = await affiliate_core.calculate_and_set_commission_for_paid_order(
        session, order
    )

    assert locked_referral is referral
    assert order.commission_usdt == Decimal("0.0000")


@pytest.mark.asyncio
async def test_calculate_and_set_commission_for_paid_order_earlier_order_query_only_counts_commission_channels(
    monkeypatch,
):
    async def _fake_rates():
        return {
            "rmb_to_usdt": Decimal("0.15"),
            "ton_to_usdt": Decimal("1.40"),
            "stars_to_usdt": Decimal("0.013"),
        }

    monkeypatch.setattr(affiliate_core, "get_exchange_rates", _fake_rates)

    referral = _build_referral()
    order = _build_order(payment_channel="RMB", final_price=Decimal("10.00"))
    session = _TrackingSession(execute_results=[referral, None])

    await affiliate_core.calculate_and_set_commission_for_paid_order(session, order)

    compiled = session.statements[1].compile(dialect=postgresql.dialect())
    sql = str(compiled)
    assert "orders.payment_channel IN" in sql
    assert "orders.paid_at <" not in sql


@pytest.mark.asyncio
async def test_calculate_and_set_commission_for_paid_order_without_referral_returns_none():
    order = _build_order()
    session = _TrackingSession(execute_results=[None])

    locked_referral = await affiliate_core.calculate_and_set_commission_for_paid_order(
        session, order
    )

    assert locked_referral is None
    assert order.commission_usdt == Decimal("0.0000")
    assert len(session.statements) == 1


@pytest.mark.asyncio
async def test_calculate_and_set_commission_for_paid_order_raises_when_exchange_rate_missing(
    monkeypatch,
):
    async def _missing_rates():
        return {}

    monkeypatch.setattr(affiliate_core, "get_exchange_rates", _missing_rates)

    referral = _build_referral()
    order = _build_order(payment_channel="TON")
    session = _TrackingSession(execute_results=[referral, None])

    with pytest.raises(affiliate_core.AffiliateCommissionConfigurationError):
        await affiliate_core.calculate_and_set_commission_for_paid_order(
            session, order
        )


@pytest.mark.asyncio
async def test_calculate_and_set_commission_for_paid_order_invalid_payment_state_skips_queries():
    order = _build_order(payment_channel="INVALID")
    session = _TrackingSession()

    locked_referral = await affiliate_core.calculate_and_set_commission_for_paid_order(
        session, order
    )

    assert locked_referral is None
    assert order.commission_usdt == Decimal("0.0000")
    assert session.statements == []


@pytest.mark.asyncio
async def test_record_affiliate_commission_transaction_builds_idempotent_insert():
    referral = _build_referral(inviter_id=1001)
    order = _build_order(
        id=321,
        order_id="ORDER-321",
        tx_hash="hash-321",
        commission_usdt=Decimal("1.2300"),
        payment_channel="RMB",
    )
    session = _TrackingSession(execute_results=[object()])

    inserted = await affiliate_core.record_affiliate_commission_transaction(
        session,
        order,
        referral,
        source="unit_test",
    )

    assert inserted is True
    assert len(session.statements) == 1

    compiled = session.statements[0].compile(dialect=postgresql.dialect())
    sql = str(compiled)
    params = compiled.params

    assert "ON CONFLICT (idempotency_key) DO NOTHING" in sql
    assert params["user_id"] == 1001
    assert params["amount_usdt"] == Decimal("1.2300")
    assert params["transaction_type"] == "COMMISSION_ACCRUAL"
    assert params["direction"] == "IN"
    assert params["reference_type"] == "ORDER"
    assert params["reference_id"] == "321"
    assert params["idempotency_key"] == "affiliate:commission:order:321"
    assert params["status"] == "SUCCESS"
    assert params["details"] == {
        "order_pk": 321,
        "order_id": "ORDER-321",
        "tx_hash": "hash-321",
        "invitee_user_id": 2002,
        "inviter_id": 1001,
        "payment_channel": "RMB",
        "commission_usdt": "1.2300",
        "source": "unit_test",
    }
    assert "RETURNING affiliate_transactions.id" in sql


@pytest.mark.asyncio
async def test_record_affiliate_commission_transaction_skips_zero_commission():
    referral = _build_referral()
    order = _build_order(commission_usdt=Decimal("0.0000"))
    session = _TrackingSession()

    inserted = await affiliate_core.record_affiliate_commission_transaction(
        session,
        order,
        referral,
    )

    assert inserted is False
    assert session.statements == []


@pytest.mark.asyncio
async def test_record_affiliate_commission_transaction_returns_false_when_conflict_happens():
    referral = _build_referral()
    order = _build_order(commission_usdt=Decimal("1.0000"))
    session = _TrackingSession(execute_results=[None])

    inserted = await affiliate_core.record_affiliate_commission_transaction(
        session,
        order,
        referral,
    )

    assert inserted is False
    assert len(session.statements) == 1


@pytest.mark.asyncio
async def test_record_affiliate_commission_transaction_raises_for_mismatched_referral():
    referral = _build_referral(invitee_id=9999)
    order = _build_order(commission_usdt=Decimal("1.0000"))
    session = _TrackingSession()

    with pytest.raises(ValueError, match="referral invitee mismatch"):
        await affiliate_core.record_affiliate_commission_transaction(
            session,
            order,
            referral,
        )


@pytest.mark.asyncio
async def test_calculate_and_set_commission_for_paid_order_serializes_same_invitee(monkeypatch):
    async def _fake_rates():
        return {
            "rmb_to_usdt": Decimal("0.15"),
            "ton_to_usdt": Decimal("1.40"),
            "stars_to_usdt": Decimal("0.013"),
        }

    monkeypatch.setattr(affiliate_core, "get_exchange_rates", _fake_rates)

    referral = _build_referral()
    state = _ConcurrentState(referral)

    async def _run_order(order_id: int):
        session = _ConcurrentReferralSession(state)
        order = _build_order(id=order_id, order_id=f"ORD-{order_id}")
        locked_referral = await affiliate_core.calculate_and_set_commission_for_paid_order(
            session, order
        )
        if order.commission_usdt > 0:
            state.winner_order_id = order.id
        state.lock.release()
        return order, locked_referral

    task_1 = asyncio.create_task(_run_order(1))
    await state.first_lock_acquired.wait()
    task_2 = asyncio.create_task(_run_order(2))

    (order_1, referral_1), (order_2, referral_2) = await asyncio.gather(task_1, task_2)

    positive_orders = [
        order.id for order in (order_1, order_2) if Decimal(str(order.commission_usdt)) > 0
    ]
    assert referral_1 is referral
    assert referral_2 is referral
    assert positive_orders == [1]
    assert order_2.commission_usdt == Decimal("0.0000")


@pytest.mark.asyncio
async def test_calculate_and_set_commission_for_paid_order_zeroes_second_committer_even_if_paid_at_is_earlier(
    monkeypatch,
):
    async def _fake_rates():
        return {
            "rmb_to_usdt": Decimal("0.15"),
            "ton_to_usdt": Decimal("1.40"),
            "stars_to_usdt": Decimal("0.013"),
        }

    monkeypatch.setattr(affiliate_core, "get_exchange_rates", _fake_rates)

    referral = _build_referral()
    later_paid_order = _build_order(
        id=2,
        order_id="ORD-2",
        paid_at=datetime(2026, 5, 18, 12, 0, 5),
    )
    earlier_paid_order = _build_order(
        id=1,
        order_id="ORD-1",
        paid_at=datetime(2026, 5, 18, 12, 0, 0),
    )

    later_session = _TrackingSession(execute_results=[referral, None])
    locked_referral = await affiliate_core.calculate_and_set_commission_for_paid_order(
        later_session, later_paid_order
    )
    assert locked_referral is referral
    assert later_paid_order.commission_usdt > 0

    earlier_session = _TrackingSession(execute_results=[referral, later_paid_order.id])
    locked_referral = await affiliate_core.calculate_and_set_commission_for_paid_order(
        earlier_session, earlier_paid_order
    )
    assert locked_referral is referral
    assert earlier_paid_order.commission_usdt == Decimal("0.0000")
