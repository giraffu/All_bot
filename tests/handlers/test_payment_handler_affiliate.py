from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.dialects import postgresql

from src.handlers import payment_handler
from src.services import telegram_payment_service
from src.services.telegram_payment_service import TelegramStarsPaymentResult


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
        if not self.execute_results:
            raise AssertionError("unexpected execute call")
        return _ScalarResult(self.execute_results.pop(0))

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
        name="Stars Plan",
        identity_name="外门弟子",
        duration_days=0,
        reward_credits=12,
        price_stars=100,
    )


def _build_user():
    return SimpleNamespace(
        id=2002,
        telegram_id=12345,
        username="stars_user",
        credits=5,
        current_identity="外门弟子",
        identity_expire_at=None,
    )


def _build_update():
    message = SimpleNamespace(
        successful_payment=SimpleNamespace(
            invoice_payload="ORDER:12345:1:999",
            total_amount=100,
            telegram_payment_charge_id="charge-id-123",
        ),
        reply_text=AsyncMock(),
    )
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=12345),
        message=message,
    )


def _build_inserted_order():
    return SimpleNamespace(
        id=321,
        order_id="ORDER:12345:1:999",
        internal_user_id=2002,
        plan_id=1,
        original_price=100,
        final_price=100,
        status="SUCCESS",
        tx_hash="charge-id-123",
        payment_channel="XTR",
        paid_at=datetime.now(),
        commission_usdt=Decimal("0.0000"),
    )


@pytest.mark.asyncio
async def test_successful_payment_callback_delegates_and_replies(monkeypatch):
    update = _build_update()
    context = SimpleNamespace()
    process_mock = AsyncMock(
        return_value=TelegramStarsPaymentResult(
            status="success",
            plan_name="Stars Plan",
            credits_granted=12,
            final_identity="外门弟子",
        )
    )
    monkeypatch.setattr(payment_handler, "process_successful_stars_payment", process_mock)

    await payment_handler.successful_payment_callback(update, context)

    process_mock.assert_awaited_once()
    update.message.reply_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_successful_stars_payment_records_affiliate_transaction(
    monkeypatch,
):
    inserted_order = _build_inserted_order()
    session = _FakeSession(
        [_build_plan(), _build_user(), inserted_order.id],
        get_results={inserted_order.id: inserted_order},
    )
    referral = SimpleNamespace(inviter_id=1001)

    calculate_mock = AsyncMock(
        side_effect=lambda _session, order: setattr(order, "commission_usdt", Decimal("0.5500"))
        or referral
    )
    record_mock = AsyncMock(return_value=True)
    invalidate_mock = AsyncMock()

    monkeypatch.setattr(
        telegram_payment_service, "AsyncSessionLocal", lambda: _SessionContext(session)
    )
    monkeypatch.setattr(
        telegram_payment_service,
        "is_membership_settlement_v2_enabled",
        lambda: False,
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

    result = await telegram_payment_service.process_successful_stars_payment(
        payload="ORDER:12345:1:999",
        total_amount=100,
        telegram_payment_charge_id="charge-id-123",
    )

    session.flush.assert_awaited_once()
    session.commit.assert_awaited_once()
    calculate_mock.assert_awaited_once()
    record_mock.assert_awaited_once()
    invalidate_mock.assert_awaited_once_with(1001)
    assert result.status == "success"
    compiled_user_query = session.statements[1].compile(dialect=postgresql.dialect())
    assert "FOR UPDATE" in str(compiled_user_query)
    compiled_insert = session.statements[2].compile(dialect=postgresql.dialect())
    assert compiled_insert.params["internal_user_id"] == 2002


@pytest.mark.asyncio
async def test_process_successful_stars_payment_duplicate_charge_does_not_record_affiliate_transaction(
    monkeypatch,
):
    session = _FakeSession([_build_plan(), _build_user(), None])

    calculate_mock = AsyncMock()
    record_mock = AsyncMock()

    monkeypatch.setattr(
        telegram_payment_service, "AsyncSessionLocal", lambda: _SessionContext(session)
    )
    monkeypatch.setattr(
        telegram_payment_service,
        "is_membership_settlement_v2_enabled",
        lambda: False,
    )
    monkeypatch.setattr(
        "src.core.affiliate_core.calculate_and_set_commission_for_paid_order",
        calculate_mock,
    )
    monkeypatch.setattr(
        "src.core.affiliate_core.record_affiliate_commission_transaction",
        record_mock,
    )

    result = await telegram_payment_service.process_successful_stars_payment(
        payload="ORDER:12345:1:999",
        total_amount=100,
        telegram_payment_charge_id="charge-id-123",
    )

    session.commit.assert_not_awaited()
    calculate_mock.assert_not_awaited()
    record_mock.assert_not_awaited()
    assert result.status == "noop"


@pytest.mark.asyncio
async def test_process_successful_stars_payment_handles_existing_naive_expire_at(
    monkeypatch,
):
    plan = _build_plan()
    plan.duration_days = 30
    existing_expire_at = datetime.now() + timedelta(days=5)
    user = _build_user()
    user.identity_expire_at = existing_expire_at
    inserted_order = _build_inserted_order()
    session = _FakeSession(
        [plan, user, inserted_order.id],
        get_results={inserted_order.id: inserted_order},
    )
    referral = SimpleNamespace(inviter_id=1001)

    calculate_mock = AsyncMock(
        side_effect=lambda _session, order: setattr(order, "commission_usdt", Decimal("0.5500"))
        or referral
    )
    record_mock = AsyncMock(return_value=True)
    invalidate_mock = AsyncMock()

    monkeypatch.setattr(
        telegram_payment_service, "AsyncSessionLocal", lambda: _SessionContext(session)
    )
    monkeypatch.setattr(
        telegram_payment_service,
        "is_membership_settlement_v2_enabled",
        lambda: False,
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

    result = await telegram_payment_service.process_successful_stars_payment(
        payload="ORDER:12345:1:999",
        total_amount=100,
        telegram_payment_charge_id="charge-id-123",
    )

    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()
    record_mock.assert_awaited_once()
    invalidate_mock.assert_awaited_once_with(1001)
    assert isinstance(user.identity_expire_at, datetime)
    assert user.identity_expire_at > existing_expire_at
    assert result.status == "success"


@pytest.mark.asyncio
async def test_process_successful_stars_payment_logs_warning_when_affiliate_ledger_insert_is_skipped(
    monkeypatch,
):
    inserted_order = _build_inserted_order()
    session = _FakeSession(
        [_build_plan(), _build_user(), inserted_order.id],
        get_results={inserted_order.id: inserted_order},
    )
    referral = SimpleNamespace(inviter_id=1001)

    calculate_mock = AsyncMock(
        side_effect=lambda _session, order: setattr(order, "commission_usdt", Decimal("0.5500"))
        or referral
    )
    record_mock = AsyncMock(return_value=False)
    invalidate_mock = AsyncMock()
    warning_mock = Mock()

    monkeypatch.setattr(
        telegram_payment_service, "AsyncSessionLocal", lambda: _SessionContext(session)
    )
    monkeypatch.setattr(
        telegram_payment_service,
        "is_membership_settlement_v2_enabled",
        lambda: False,
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
    monkeypatch.setattr(telegram_payment_service.logger, "warning", warning_mock)

    await telegram_payment_service.process_successful_stars_payment(
        payload="ORDER:12345:1:999",
        total_amount=100,
        telegram_payment_charge_id="charge-id-123",
    )

    warning_mock.assert_called_once()


@pytest.mark.asyncio
async def test_process_successful_stars_payment_uses_unified_membership_settlement_when_enabled(
    monkeypatch,
):
    inserted_order = _build_inserted_order()
    session = _FakeSession(
        [_build_plan(), _build_user(), inserted_order.id],
        get_results={inserted_order.id: inserted_order},
    )
    referral = SimpleNamespace(inviter_id=1001)

    calculate_mock = AsyncMock(
        side_effect=lambda _session, order: setattr(
            order, "commission_usdt", Decimal("0.5500")
        )
        or referral
    )
    record_mock = AsyncMock(return_value=True)
    invalidate_mock = AsyncMock()
    settle_mock = AsyncMock(
        return_value={
            "credits_granted": 12,
            "converted_days": 0,
            "final_identity": "外门弟子",
            "final_expire_at": "2026-06-30T00:00:00",
            "is_pure_credit_plan": True,
            "is_downgrade": False,
        }
    )

    monkeypatch.setattr(
        telegram_payment_service, "AsyncSessionLocal", lambda: _SessionContext(session)
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
        telegram_payment_service,
        "is_membership_settlement_v2_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        telegram_payment_service,
        "settle_membership_plan_in_session",
        settle_mock,
    )

    await telegram_payment_service.process_successful_stars_payment(
        payload="ORDER:12345:1:999",
        total_amount=100,
        telegram_payment_charge_id="charge-id-123",
    )

    settle_mock.assert_awaited_once()
    session.commit.assert_awaited_once()
    invalidate_mock.assert_awaited_once_with(1001)


@pytest.mark.asyncio
async def test_validate_stars_precheckout_accepts_order_v2_after_strong_validation(
    monkeypatch,
):
    session = _FakeSession(
        [
            SimpleNamespace(
                business_order_id="bo_123",
                internal_user_id=2002,
                status="PENDING",
                plan_id=1,
            ),
            _build_plan(),
        ]
    )

    monkeypatch.setattr(
        telegram_payment_service, "AsyncSessionLocal", lambda: _SessionContext(session)
    )
    monkeypatch.setattr(
        telegram_payment_service,
        "get_or_create_user_by_telegram",
        AsyncMock(return_value=(SimpleNamespace(id=2002), False)),
    )

    ok = await telegram_payment_service.validate_stars_precheckout(
        payload="ORDER_V2:bo_123",
        telegram_user_id=12345,
        total_amount=100,
    )

    assert ok is True


@pytest.mark.asyncio
async def test_process_successful_stars_payment_updates_pending_order_for_order_v2(
    monkeypatch,
):
    pending_order = SimpleNamespace(
        id=321,
        order_id="ORDER:12345:1:999",
        business_order_id="bo_123",
        internal_user_id=2002,
        plan_id=1,
        original_price=100,
        final_price=100,
        status="PENDING",
        tx_hash=None,
        payment_channel="XTR",
        paid_at=None,
        commission_usdt=Decimal("0.0000"),
    )
    session = _FakeSession([pending_order, _build_user(), _build_plan()])

    monkeypatch.setattr(
        telegram_payment_service, "AsyncSessionLocal", lambda: _SessionContext(session)
    )
    monkeypatch.setattr(
        telegram_payment_service,
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

    await telegram_payment_service.process_successful_stars_payment(
        payload="ORDER_V2:bo_123",
        total_amount=100,
        telegram_payment_charge_id="charge-id-456",
    )

    assert pending_order.status == "SUCCESS"
    assert pending_order.tx_hash == "charge-id-456"
    session.commit.assert_awaited_once()
