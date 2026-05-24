from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.dialects import postgresql

from src.constants import TON_TO_NANOTON
from src.services import payment_validator


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeSession:
    def __init__(self, execute_results, get_results=None):
        self.execute_results = list(execute_results)
        self.get_results = dict(get_results or {})
        self.statements = []
        self.added = []
        self.commit = AsyncMock()
        self.rollback = AsyncMock()
        self.flush = AsyncMock()

    async def execute(self, stmt):
        self.statements.append(stmt)
        if self.execute_results:
            return _ScalarResult(self.execute_results.pop(0))
        return _ScalarResult(None)

    def add(self, obj):
        self.added.append(obj)

    async def get(self, _model, key):
        return self.get_results.get(key)


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _build_plan():
    return SimpleNamespace(
        id=1,
        name="TON Plan",
        identity_name="外门弟子",
        duration_days=30,
        reward_credits=20,
        price_ton=Decimal("1.00"),
    )


def _build_user():
    return SimpleNamespace(
        id=9001,
        username="ton_user",
        credits=5,
        current_identity="外门弟子",
        identity_expire_at=None,
    )


def _build_inserted_order():
    return SimpleNamespace(
        id=321,
        order_id="ORDER:12345:1:999",
        telegram_id=9001,
        internal_user_id=9001,
        plan_id=1,
        original_price=Decimal("1.00"),
        final_price=Decimal("1.00"),
        status="SUCCESS",
        tx_hash="txhash-1",
        payment_channel="TON",
        paid_at=None,
        commission_usdt=Decimal("0.0000"),
    )


@pytest.mark.asyncio
async def test_process_order_records_affiliate_transaction_on_success(monkeypatch):
    inserted_order = _build_inserted_order()
    session = _FakeSession(
        [None, _build_plan(), _build_user(), inserted_order.id],
        get_results={inserted_order.id: inserted_order},
    )
    referral = SimpleNamespace(inviter_id=1001)
    bot = SimpleNamespace(send_message=AsyncMock())
    validator = payment_validator.TonPaymentValidator(SimpleNamespace(bot=bot))

    calculate_mock = AsyncMock(
        side_effect=lambda _db, order: setattr(order, "commission_usdt", Decimal("1.5000"))
        or referral
    )
    record_mock = AsyncMock(return_value=True)
    invalidate_mock = AsyncMock()
    get_user_mock = AsyncMock(return_value=(SimpleNamespace(id=9001), False))

    monkeypatch.setattr(
        payment_validator, "AsyncSessionLocal", lambda: _SessionContext(session)
    )
    monkeypatch.setattr(
        payment_validator,
        "is_membership_settlement_v2_enabled",
        lambda: False,
    )
    monkeypatch.setattr(
        "src.core.user_core.get_or_create_user_by_telegram",
        get_user_mock,
    )
    monkeypatch.setattr(
        "src.core.affiliate_core.calculate_and_set_commission_for_paid_order",
        calculate_mock,
    )
    monkeypatch.setattr(
        "src.core.affiliate_core.record_affiliate_commission_transaction",
        record_mock,
    )
    monkeypatch.setattr(
        "src.core.affiliate_core.invalidate_invitation_recharge_cache",
        invalidate_mock,
    )

    ok = await validator._process_order(
        "ORDER:12345:1:999",
        int(Decimal("1.00") * Decimal(str(TON_TO_NANOTON))),
        "txhash-1",
    )

    assert ok is True
    session.flush.assert_awaited_once()
    session.commit.assert_awaited_once()
    calculate_mock.assert_awaited_once()
    record_mock.assert_awaited_once()
    invalidate_mock.assert_awaited_once_with(1001)
    bot.send_message.assert_awaited_once()
    compiled_user_query = session.statements[2].compile(dialect=postgresql.dialect())
    assert "FOR UPDATE" in str(compiled_user_query)


@pytest.mark.asyncio
async def test_process_order_duplicate_tx_does_not_record_affiliate_transaction(monkeypatch):
    session = _FakeSession([None, _build_plan(), _build_user(), None])
    validator = payment_validator.TonPaymentValidator(
        SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()))
    )

    record_mock = AsyncMock()
    calculate_mock = AsyncMock()
    get_user_mock = AsyncMock(return_value=(SimpleNamespace(id=9001), False))

    monkeypatch.setattr(
        payment_validator, "AsyncSessionLocal", lambda: _SessionContext(session)
    )
    monkeypatch.setattr(
        payment_validator,
        "is_membership_settlement_v2_enabled",
        lambda: False,
    )
    monkeypatch.setattr(
        "src.core.user_core.get_or_create_user_by_telegram",
        get_user_mock,
    )
    monkeypatch.setattr(
        "src.core.affiliate_core.calculate_and_set_commission_for_paid_order",
        calculate_mock,
    )
    monkeypatch.setattr(
        "src.core.affiliate_core.record_affiliate_commission_transaction",
        record_mock,
    )

    ok = await validator._process_order(
        "ORDER:12345:1:999",
        int(Decimal("1.00") * Decimal(str(TON_TO_NANOTON))),
        "txhash-dup",
    )

    assert ok is True
    calculate_mock.assert_not_awaited()
    record_mock.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_order_logs_warning_when_affiliate_ledger_insert_is_skipped(
    monkeypatch,
):
    inserted_order = _build_inserted_order()
    session = _FakeSession(
        [None, _build_plan(), _build_user(), inserted_order.id],
        get_results={inserted_order.id: inserted_order},
    )
    referral = SimpleNamespace(inviter_id=1001)
    bot = SimpleNamespace(send_message=AsyncMock())
    validator = payment_validator.TonPaymentValidator(SimpleNamespace(bot=bot))

    calculate_mock = AsyncMock(
        side_effect=lambda _db, order: setattr(order, "commission_usdt", Decimal("1.5000"))
        or referral
    )
    record_mock = AsyncMock(return_value=False)
    invalidate_mock = AsyncMock()
    get_user_mock = AsyncMock(return_value=(SimpleNamespace(id=9001), False))
    warning_mock = Mock()

    monkeypatch.setattr(
        payment_validator, "AsyncSessionLocal", lambda: _SessionContext(session)
    )
    monkeypatch.setattr(
        payment_validator,
        "is_membership_settlement_v2_enabled",
        lambda: False,
    )
    monkeypatch.setattr(
        "src.core.user_core.get_or_create_user_by_telegram",
        get_user_mock,
    )
    monkeypatch.setattr(
        "src.core.affiliate_core.calculate_and_set_commission_for_paid_order",
        calculate_mock,
    )
    monkeypatch.setattr(
        "src.core.affiliate_core.record_affiliate_commission_transaction",
        record_mock,
    )
    monkeypatch.setattr(
        "src.core.affiliate_core.invalidate_invitation_recharge_cache",
        invalidate_mock,
    )
    monkeypatch.setattr(payment_validator.logger, "warning", warning_mock)

    ok = await validator._process_order(
        "ORDER:12345:1:999",
        int(Decimal("1.00") * Decimal(str(TON_TO_NANOTON))),
        inserted_order.tx_hash,
    )

    assert ok is True
    warning_mock.assert_called_once()


@pytest.mark.asyncio
async def test_process_order_uses_unified_membership_settlement_when_enabled(
    monkeypatch,
):
    inserted_order = _build_inserted_order()
    session = _FakeSession(
        [None, _build_plan(), _build_user(), inserted_order.id],
        get_results={inserted_order.id: inserted_order},
    )
    referral = SimpleNamespace(inviter_id=1001)
    bot = SimpleNamespace(send_message=AsyncMock())
    validator = payment_validator.TonPaymentValidator(SimpleNamespace(bot=bot))

    calculate_mock = AsyncMock(
        side_effect=lambda _db, order: setattr(order, "commission_usdt", Decimal("1.5000"))
        or referral
    )
    record_mock = AsyncMock(return_value=True)
    invalidate_mock = AsyncMock()
    get_user_mock = AsyncMock(return_value=(SimpleNamespace(id=9001), False))
    settle_mock = AsyncMock(
        return_value={
            "credits_granted": 20,
            "converted_days": 0,
            "final_identity": "外门弟子",
            "final_expire_at": "2026-06-30T00:00:00",
            "is_downgrade": False,
        }
    )

    monkeypatch.setattr(
        payment_validator, "AsyncSessionLocal", lambda: _SessionContext(session)
    )
    monkeypatch.setattr(
        "src.core.user_core.get_or_create_user_by_telegram",
        get_user_mock,
    )
    monkeypatch.setattr(
        "src.core.affiliate_core.calculate_and_set_commission_for_paid_order",
        calculate_mock,
    )
    monkeypatch.setattr(
        "src.core.affiliate_core.record_affiliate_commission_transaction",
        record_mock,
    )
    monkeypatch.setattr(
        "src.core.affiliate_core.invalidate_invitation_recharge_cache",
        invalidate_mock,
    )
    monkeypatch.setattr(
        payment_validator,
        "is_membership_settlement_v2_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        payment_validator,
        "settle_membership_plan_in_session",
        settle_mock,
    )

    ok = await validator._process_order(
        "ORDER:12345:1:999",
        int(Decimal("1.00") * Decimal(str(TON_TO_NANOTON))),
        "txhash-1",
    )

    assert ok is True
    settle_mock.assert_awaited_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_order_supports_order_v2_pending_order(monkeypatch):
    pending_order = SimpleNamespace(
        id=321,
        order_id="ORDER:12345:1:999",
        business_order_id="bo_ton_1",
        telegram_id=9001,
        internal_user_id=9001,
        plan_id=1,
        original_price=Decimal("1.00"),
        final_price=Decimal("1.00"),
        status="PENDING",
        tx_hash=None,
        payment_channel="TON",
        paid_at=None,
        commission_usdt=Decimal("0.0000"),
    )
    session = _FakeSession([pending_order, _build_plan(), _build_user()])
    bot = SimpleNamespace(send_message=AsyncMock())
    validator = payment_validator.TonPaymentValidator(SimpleNamespace(bot=bot))

    monkeypatch.setattr(
        payment_validator, "AsyncSessionLocal", lambda: _SessionContext(session)
    )
    monkeypatch.setattr(
        payment_validator,
        "is_membership_settlement_v2_enabled",
        lambda: False,
    )
    monkeypatch.setattr(
        "src.core.affiliate_core.calculate_and_set_commission_for_paid_order",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "src.core.affiliate_core.record_affiliate_commission_transaction",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        "src.core.affiliate_core.invalidate_invitation_recharge_cache",
        AsyncMock(),
    )

    ok = await validator._process_order(
        "ORDER_V2:bo_ton_1",
        int(Decimal("1.00") * Decimal(str(TON_TO_NANOTON))),
        "txhash-v2",
    )

    assert ok is True
    assert pending_order.status == "SUCCESS"
    assert pending_order.tx_hash == "txhash-v2"
    session.commit.assert_awaited_once()
