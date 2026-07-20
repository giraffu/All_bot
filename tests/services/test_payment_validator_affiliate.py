from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.dialects import postgresql

from src.constants import TON_TO_NANOTON
from src.services import payment_validator


VALID_TON_ADDRESS = "UQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAJKZ"


def _validator(bot):
    return payment_validator.TonPaymentValidator(
        SimpleNamespace(bot=bot),
        merchant_address=VALID_TON_ADDRESS,
    )


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


class _FakeAiohttpResponse:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self):
        return self.payload


class _FakeAiohttpSession:
    def __init__(self, response, post_calls):
        self.response = response
        self.post_calls = post_calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def post(self, url, json=None, headers=None):
        self.post_calls.append({"url": url, "json": json, "headers": headers})
        return self.response


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
    validator = _validator(bot)

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
    validator = _validator(SimpleNamespace(send_message=AsyncMock()))

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
    validator = _validator(bot)

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
    validator = _validator(bot)

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
    validator = _validator(bot)

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


@pytest.mark.asyncio
async def test_check_new_transactions_backs_off_on_rate_limit_payload(monkeypatch):
    post_calls = []
    warning_mock = Mock()
    validator = payment_validator.TonPaymentValidator(
        SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock())),
        merchant_address=VALID_TON_ADDRESS,
        api_key="secret-key",
        poll_interval_seconds=15,
        max_poll_interval_seconds=120,
    )

    monkeypatch.setattr(
        payment_validator.aiohttp,
        "ClientSession",
        lambda: _FakeAiohttpSession(
            _FakeAiohttpResponse({"result": "Ratelimit exceed"}),
            post_calls,
        ),
    )
    monkeypatch.setattr(payment_validator.logger, "warning", warning_mock)

    await validator._check_new_transactions()

    assert validator.current_poll_interval_seconds == 30
    assert post_calls[0]["headers"] == {"X-API-Key": "secret-key"}
    warning_mock.assert_called_once()


@pytest.mark.asyncio
async def test_check_new_transactions_resets_backoff_after_successful_fetch(monkeypatch):
    post_calls = []
    validator = payment_validator.TonPaymentValidator(
        SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock())),
        merchant_address=VALID_TON_ADDRESS,
        api_key="secret-key",
        poll_interval_seconds=15,
        max_poll_interval_seconds=120,
    )
    validator.current_poll_interval_seconds = 60

    monkeypatch.setattr(
        payment_validator.aiohttp,
        "ClientSession",
        lambda: _FakeAiohttpSession(
            _FakeAiohttpResponse({"result": []}),
            post_calls,
        ),
    )

    await validator._check_new_transactions()

    assert validator.current_poll_interval_seconds == 15
    assert post_calls[0]["headers"] == {"X-API-Key": "secret-key"}


@pytest.mark.asyncio
async def test_fulfillment_failure_does_not_advance_checkpoint(monkeypatch):
    post_calls = []
    validator = _validator(SimpleNamespace(send_message=AsyncMock()))
    validator.last_lt = 10
    validator._last_lt_loaded = True
    process_order = AsyncMock(return_value=False)
    persist_last_lt = AsyncMock()
    monkeypatch.setattr(validator, "_process_order", process_order)
    monkeypatch.setattr(validator, "_persist_last_lt", persist_last_lt)
    monkeypatch.setattr(
        payment_validator.aiohttp,
        "ClientSession",
        lambda: _FakeAiohttpSession(
            _FakeAiohttpResponse(
                {
                    "result": [
                        {
                            "transaction_id": {"lt": "20", "hash": "tx-20"},
                            "in_msg": {
                                "value": str(TON_TO_NANOTON),
                                "message": "ORDER:12345:1:999",
                            },
                        }
                    ]
                }
            ),
            post_calls,
        ),
    )

    await validator._check_new_transactions()

    process_order.assert_awaited_once()
    assert validator.last_lt == 10
    persist_last_lt.assert_not_awaited()


def test_validator_rejects_missing_merchant_before_any_polling():
    with pytest.raises(ValueError, match="merchant"):
        payment_validator.TonPaymentValidator(
            SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock())),
            merchant_address=None,
        )


def test_checkpoint_key_is_scoped_to_validated_merchant_address():
    validator = _validator(SimpleNamespace(send_message=AsyncMock()))

    assert validator._last_lt_checkpoint_key == f"ton:{VALID_TON_ADDRESS}:last_lt"


def test_invalid_runtime_config_does_not_construct_ton_poller():
    validator_factory = Mock()

    result = payment_validator.build_ton_payment_validator_if_available(
        SimpleNamespace(),
        availability=SimpleNamespace(
            requested_enabled=True,
            enabled=False,
            merchant_address=None,
            error_reason="TON merchant address is invalid",
        ),
        validator_factory=validator_factory,
    )

    assert result is None
    validator_factory.assert_not_called()


def test_valid_runtime_config_constructs_poller_with_resolved_address():
    constructed = object()
    validator_factory = Mock(return_value=constructed)
    bot_app = SimpleNamespace()

    result = payment_validator.build_ton_payment_validator_if_available(
        bot_app,
        availability=SimpleNamespace(
            requested_enabled=True,
            enabled=True,
            merchant_address=VALID_TON_ADDRESS,
            error_reason=None,
        ),
        validator_factory=validator_factory,
    )

    assert result is constructed
    validator_factory.assert_called_once_with(
        bot_app=bot_app,
        merchant_address=VALID_TON_ADDRESS,
    )
