from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.dialects import postgresql

from src.services import payment_fulfillment_service


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeSession:
    def __init__(self, execute_results):
        self.execute_results = list(execute_results)
        self.statements = []
        self.added = []
        self.commit = AsyncMock()
        self.rollback = AsyncMock()
        self.flush = AsyncMock()

    async def execute(self, stmt):
        self.statements.append(stmt)
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


def _build_order(status="PENDING"):
    return SimpleNamespace(
        id=321,
        order_id="RMB-ORDER-1",
        internal_user_id=2002,
        plan_id=1,
        final_price=Decimal("10.00"),
        status=status,
        tx_hash=None,
        paid_at=None,
        payment_channel=None,
        commission_usdt=Decimal("0.0000"),
    )


def _build_plan():
    return SimpleNamespace(
        id=1,
        name="Plan A",
        identity_name="外门弟子",
        duration_days=30,
        reward_credits=100,
        price_usdt=Decimal("4.50"),
    )


def _build_user():
    return SimpleNamespace(
        id=2002,
        telegram_id=8888,
        username="payer",
        credits=10,
        current_identity="外门弟子",
        identity_expire_at=None,
    )


def _usdt_dependencies(session, settle_mock):
    return payment_fulfillment_service.PaymentFulfillmentDependencies(
        session_factory=lambda: _SessionContext(session),
        is_settlement_v2_enabled=lambda: True,
        settle_membership_plan_in_session_func=settle_mock,
        calculate_commission_func=AsyncMock(return_value=None),
        record_affiliate_transaction_func=AsyncMock(return_value=False),
        invalidate_invitation_cache_func=AsyncMock(),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("paid_amount", "expected_status", "settle_calls"),
    [
        (4_500_000, "success", 1),
        (4_499_999, "amount_mismatch", 0),
        (4_500_001, "amount_mismatch", 0),
    ],
)
async def test_usdt_ton_fulfillment_requires_exact_six_decimal_amount(
    paid_amount,
    expected_status,
    settle_calls,
):
    order = _build_order(status="PENDING")
    plan = _build_plan()
    user = _build_user()
    session = _FakeSession([order, plan, user])
    settle_mock = AsyncMock(
        return_value={
            "credits_granted": 100,
            "final_identity": "内门弟子",
            "current_credits": 110,
        }
    )

    result = await payment_fulfillment_service.fulfill_payment_command(
        payment_fulfillment_service.PaymentFulfillmentCommand(
            channel="USDT_TON",
            order_lookup="RMB-ORDER-1",
            external_tx_id=f"usdt-tx-{paid_amount}",
            paid_amount=paid_amount,
            paid_unit="micro_usdt",
            source="test",
            affiliate_source="test",
            audit_source="test",
        ),
        dependencies=_usdt_dependencies(session, settle_mock),
    )

    assert result.status == expected_status
    assert settle_mock.await_count == settle_calls
    if expected_status == "success":
        assert order.payment_channel == "USDT_TON"
        assert order.final_price == Decimal("4.5")
        session.commit.assert_awaited_once()
    else:
        session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_fulfill_order_records_affiliate_transaction_on_success(monkeypatch):
    order = _build_order(status="PENDING")
    plan = _build_plan()
    user = _build_user()
    referral = SimpleNamespace(inviter_id=1001)
    session = _FakeSession([order, plan, user])

    calculate_mock = AsyncMock(side_effect=lambda _s, current_order: setattr(current_order, "commission_usdt", Decimal("1.2500")) or referral)
    record_mock = AsyncMock(return_value=True)
    invalidate_mock = AsyncMock()

    monkeypatch.setattr(
        payment_fulfillment_service, "AsyncSessionLocal", lambda: _SessionContext(session)
    )
    monkeypatch.setattr(
        payment_fulfillment_service,
        "is_membership_settlement_v2_enabled",
        lambda: False,
    )
    monkeypatch.setattr(
        payment_fulfillment_service,
        "calculate_and_set_commission_for_paid_order",
        calculate_mock,
    )
    monkeypatch.setattr(
        payment_fulfillment_service,
        "record_affiliate_commission_transaction",
        record_mock,
    )
    monkeypatch.setattr(
        payment_fulfillment_service,
        "invalidate_invitation_recharge_cache",
        invalidate_mock,
    )
    monkeypatch.delenv("BOT_TOKEN", raising=False)

    ok = await payment_fulfillment_service.fulfill_order(
        "RMB-ORDER-1",
        "external-tx-1",
        "10.00",
    )

    assert ok is True
    assert order.status == "SUCCESS"
    assert order.payment_channel == "RMB"
    assert order.tx_hash == "external-tx-1"
    session.flush.assert_awaited_once()
    session.commit.assert_awaited_once()
    calculate_mock.assert_awaited_once()
    record_mock.assert_awaited_once_with(
        session,
        order,
        referral,
        source="rmb_payment_callback",
    )
    invalidate_mock.assert_awaited_once_with(1001)
    compiled_user_query = session.statements[2].compile(dialect=postgresql.dialect())
    assert "FOR UPDATE" in str(compiled_user_query)


@pytest.mark.asyncio
async def test_fulfill_order_invalidates_affiliate_cache_after_commit(monkeypatch):
    order = _build_order(status="PENDING")
    plan = _build_plan()
    user = _build_user()
    referral = SimpleNamespace(inviter_id=1001)
    session = _FakeSession([order, plan, user])
    events: list[str] = []

    async def commit_side_effect():
        events.append("commit")

    async def invalidate_side_effect(_user_id):
        events.append("invalidate")

    session.commit.side_effect = commit_side_effect
    calculate_mock = AsyncMock(
        side_effect=lambda _s, current_order: setattr(
            current_order, "commission_usdt", Decimal("1.2500")
        )
        or referral
    )

    monkeypatch.setattr(
        payment_fulfillment_service, "AsyncSessionLocal", lambda: _SessionContext(session)
    )
    monkeypatch.setattr(
        payment_fulfillment_service,
        "is_membership_settlement_v2_enabled",
        lambda: False,
    )
    monkeypatch.setattr(
        payment_fulfillment_service,
        "calculate_and_set_commission_for_paid_order",
        calculate_mock,
    )
    monkeypatch.setattr(
        payment_fulfillment_service,
        "record_affiliate_commission_transaction",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        payment_fulfillment_service,
        "invalidate_invitation_recharge_cache",
        AsyncMock(side_effect=invalidate_side_effect),
    )
    monkeypatch.delenv("BOT_TOKEN", raising=False)

    ok = await payment_fulfillment_service.fulfill_order(
        "RMB-ORDER-1",
        "external-tx-ordering",
        "10.00",
    )

    assert ok is True
    assert events == ["commit", "invalidate"]


@pytest.mark.asyncio
async def test_post_commit_cache_failure_does_not_turn_committed_payment_into_failure(
    monkeypatch,
):
    order = _build_order(status="PENDING")
    plan = _build_plan()
    user = _build_user()
    referral = SimpleNamespace(inviter_id=1001)
    session = _FakeSession([order, plan, user])

    monkeypatch.setattr(
        payment_fulfillment_service,
        "AsyncSessionLocal",
        lambda: _SessionContext(session),
    )
    monkeypatch.setattr(
        payment_fulfillment_service,
        "is_membership_settlement_v2_enabled",
        lambda: False,
    )
    monkeypatch.setattr(
        payment_fulfillment_service,
        "calculate_and_set_commission_for_paid_order",
        AsyncMock(
            side_effect=lambda _s, current_order: setattr(
                current_order,
                "commission_usdt",
                Decimal("1.2500"),
            )
            or referral
        ),
    )
    monkeypatch.setattr(
        payment_fulfillment_service,
        "record_affiliate_commission_transaction",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        payment_fulfillment_service,
        "invalidate_invitation_recharge_cache",
        AsyncMock(side_effect=RuntimeError("cache unavailable")),
    )
    monkeypatch.delenv("BOT_TOKEN", raising=False)

    result = await payment_fulfillment_service.fulfill_rmb_order(
        "RMB-ORDER-1",
        "external-tx-post-commit",
        "10.00",
        source="rmb_payment_callback",
    )

    assert result.status == "success"
    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_fulfill_order_accepts_string_paid_amount(monkeypatch):
    order = _build_order(status="PENDING")
    order.final_price = Decimal("0.30")
    plan = _build_plan()
    user = _build_user()
    referral = SimpleNamespace(inviter_id=1001)
    session = _FakeSession([order, plan, user])

    calculate_mock = AsyncMock(
        side_effect=lambda _s, current_order: setattr(
            current_order, "commission_usdt", Decimal("0.0450")
        )
        or referral
    )
    record_mock = AsyncMock(return_value=True)
    invalidate_mock = AsyncMock()

    monkeypatch.setattr(
        payment_fulfillment_service, "AsyncSessionLocal", lambda: _SessionContext(session)
    )
    monkeypatch.setattr(
        payment_fulfillment_service,
        "is_membership_settlement_v2_enabled",
        lambda: False,
    )
    monkeypatch.setattr(
        payment_fulfillment_service,
        "calculate_and_set_commission_for_paid_order",
        calculate_mock,
    )
    monkeypatch.setattr(
        payment_fulfillment_service,
        "record_affiliate_commission_transaction",
        record_mock,
    )
    monkeypatch.setattr(
        payment_fulfillment_service,
        "invalidate_invitation_recharge_cache",
        invalidate_mock,
    )
    monkeypatch.delenv("BOT_TOKEN", raising=False)

    ok = await payment_fulfillment_service.fulfill_order(
        "RMB-ORDER-1",
        "external-tx-precision",
        "0.30",
    )

    assert ok is True
    session.commit.assert_awaited_once()
    calculate_mock.assert_awaited_once()
    record_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_fulfill_order_duplicate_callback_does_not_record_affiliate_transaction(monkeypatch):
    order = _build_order(status="SUCCESS")
    session = _FakeSession([order])

    calculate_mock = AsyncMock()
    record_mock = AsyncMock()

    monkeypatch.setattr(
        payment_fulfillment_service, "AsyncSessionLocal", lambda: _SessionContext(session)
    )
    monkeypatch.setattr(
        payment_fulfillment_service,
        "is_membership_settlement_v2_enabled",
        lambda: False,
    )
    monkeypatch.setattr(
        payment_fulfillment_service,
        "calculate_and_set_commission_for_paid_order",
        calculate_mock,
    )
    monkeypatch.setattr(
        payment_fulfillment_service,
        "record_affiliate_commission_transaction",
        record_mock,
    )

    ok = await payment_fulfillment_service.fulfill_order(
        "RMB-ORDER-1",
        "external-tx-1",
        "10.00",
    )

    assert ok is True
    calculate_mock.assert_not_awaited()
    record_mock.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_fulfill_order_logs_warning_when_affiliate_ledger_insert_is_skipped(
    monkeypatch,
):
    order = _build_order(status="PENDING")
    plan = _build_plan()
    user = _build_user()
    referral = SimpleNamespace(inviter_id=1001)
    session = _FakeSession([order, plan, user])

    calculate_mock = AsyncMock(
        side_effect=lambda _s, current_order: setattr(
            current_order, "commission_usdt", Decimal("1.2500")
        )
        or referral
    )
    record_mock = AsyncMock(return_value=False)
    invalidate_mock = AsyncMock()
    warning_mock = Mock()

    monkeypatch.setattr(
        payment_fulfillment_service, "AsyncSessionLocal", lambda: _SessionContext(session)
    )
    monkeypatch.setattr(
        payment_fulfillment_service,
        "is_membership_settlement_v2_enabled",
        lambda: False,
    )
    monkeypatch.setattr(
        payment_fulfillment_service,
        "calculate_and_set_commission_for_paid_order",
        calculate_mock,
    )
    monkeypatch.setattr(
        payment_fulfillment_service,
        "record_affiliate_commission_transaction",
        record_mock,
    )
    monkeypatch.setattr(
        payment_fulfillment_service,
        "invalidate_invitation_recharge_cache",
        invalidate_mock,
    )
    monkeypatch.setattr(payment_fulfillment_service.logger, "warning", warning_mock)
    monkeypatch.delenv("BOT_TOKEN", raising=False)

    ok = await payment_fulfillment_service.fulfill_order(
        "RMB-ORDER-1",
        "external-tx-warning",
        "10.00",
    )

    assert ok is True
    warning_mock.assert_called_once()


@pytest.mark.asyncio
async def test_fulfill_order_uses_unified_membership_settlement_when_enabled(monkeypatch):
    order = _build_order(status="PENDING")
    plan = _build_plan()
    user = _build_user()
    referral = SimpleNamespace(inviter_id=1001)
    session = _FakeSession([order, plan, user])

    calculate_mock = AsyncMock(
        side_effect=lambda _s, current_order: setattr(
            current_order, "commission_usdt", Decimal("1.2500")
        )
        or referral
    )
    record_mock = AsyncMock(return_value=True)
    invalidate_mock = AsyncMock()
    settle_mock = AsyncMock(
        return_value={
            "credits_granted": 100,
            "converted_days": 0,
            "final_identity": "外门弟子",
            "final_expire_at": "2026-06-30T00:00:00",
            "is_pure_credit_plan": False,
            "is_downgrade": False,
        }
    )

    monkeypatch.setattr(
        payment_fulfillment_service, "AsyncSessionLocal", lambda: _SessionContext(session)
    )
    monkeypatch.setattr(
        payment_fulfillment_service,
        "calculate_and_set_commission_for_paid_order",
        calculate_mock,
    )
    monkeypatch.setattr(
        payment_fulfillment_service,
        "record_affiliate_commission_transaction",
        record_mock,
    )
    monkeypatch.setattr(
        payment_fulfillment_service,
        "invalidate_invitation_recharge_cache",
        invalidate_mock,
    )
    monkeypatch.setattr(
        payment_fulfillment_service,
        "is_membership_settlement_v2_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        payment_fulfillment_service,
        "settle_membership_plan_in_session",
        settle_mock,
    )
    monkeypatch.delenv("BOT_TOKEN", raising=False)

    ok = await payment_fulfillment_service.fulfill_order(
        "RMB-ORDER-1",
        "external-tx-unified",
        "10.00",
    )

    assert ok is True
    settle_mock.assert_awaited_once()
    session.commit.assert_awaited_once()
