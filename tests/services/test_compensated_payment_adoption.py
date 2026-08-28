from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services import payment_fulfillment_service


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
        self.rollback = AsyncMock()
        self.flush = AsyncMock()

    async def execute(self, _stmt):
        if not self.execute_results:
            raise AssertionError("unexpected execute call")
        return _ScalarResult(self.execute_results.pop(0))

    def add(self, value):
        self.added.append(value)


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *_args):
        return False


@pytest.mark.asyncio
async def test_adopt_compensated_payment_marks_order_paid_without_regranting_user_assets():
    created_at = datetime(2026, 8, 29, 2, 29, 38)
    target = SimpleNamespace(
        id=20833,
        order_id="WEB-PAID",
        business_order_id="bo-paid",
        internal_user_id=10000000004165,
        plan_id=2,
        original_price=Decimal("70.00"),
        final_price=Decimal("70.00"),
        payment_channel="RMB",
        payment_provider="ALIPAY_DIRECT",
        status="PENDING",
        tx_hash=None,
        paid_at=None,
        commission_usdt=Decimal("0.0000"),
        settlement_snapshot={"schema_version": "order_plan_v1"},
        created_at=created_at,
    )
    gift = SimpleNamespace(
        id=20835,
        order_id="GIFT:4165:2:1",
        business_order_id=None,
        internal_user_id=10000000004165,
        plan_id=2,
        final_price=Decimal("0.00"),
        payment_channel=None,
        payment_provider=None,
        status="SUCCESS",
        tx_hash="manual_gift",
        paid_at=datetime(2026, 8, 29, 2, 58, 22),
        settlement_snapshot={"credits_granted": 1200},
        created_at=datetime(2026, 8, 29, 2, 58, 22),
    )
    user = SimpleNamespace(
        id=10000000004165,
        username="payer",
        telegram_id=123,
        credits=1201,
        current_identity="核心弟子",
        identity_expire_at=datetime(2026, 10, 8, 2, 58, 22),
    )
    job = SimpleNamespace(
        status="pending",
        last_outcome=None,
        last_error_code=None,
        completed_at=None,
        lease_token=None,
        lease_until=None,
        updated_at=None,
    )
    session = _FakeSession([target, gift, user, None, job])
    calculate_commission = AsyncMock(return_value=None)
    settle_membership = AsyncMock()
    dependencies = payment_fulfillment_service.PaymentFulfillmentDependencies(
        session_factory=lambda: _SessionContext(session),
        is_settlement_v2_enabled=lambda: True,
        settle_membership_plan_in_session_func=settle_membership,
        calculate_commission_func=calculate_commission,
        record_affiliate_transaction_func=AsyncMock(return_value=False),
        invalidate_invitation_cache_func=AsyncMock(),
    )

    before = (user.credits, user.current_identity, user.identity_expire_at)
    result = await payment_fulfillment_service.adopt_compensated_rmb_payment(
        payment_fulfillment_service.CompensatedRMBPaymentAdoptionCommand(
            order_lookup="bo-paid",
            compensation_order_lookup="GIFT:4165:2:1",
            expected_internal_user_id=10000000004165,
            external_tx_id="ALIPAY-TRADE-1",
            paid_amount="70.00",
            source="prod_repair",
            now=datetime(2026, 8, 29, 3, 5, 0),
        ),
        dependencies=dependencies,
    )

    assert result.status == "success"
    assert result.credits_granted == 0
    assert (user.credits, user.current_identity, user.identity_expire_at) == before
    assert target.status == "SUCCESS"
    assert target.tx_hash == "ALIPAY-TRADE-1"
    assert target.paid_at == datetime(2026, 8, 29, 3, 5, 0)
    assert gift.settlement_snapshot["payment_compensation_adoption"]["order_id"] == 20833
    assert job.status == "completed"
    assert job.last_outcome == "compensated_payment_adopted"
    settle_membership.assert_not_awaited()
    calculate_commission.assert_awaited_once_with(session, target)
    assert len(session.added) == 1
    assert session.added[0].operation_type == "compensated_payment_adoption"
    assert session.added[0].credit_change == 0
    assert session.added[0].current_balance == 1201
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_adopt_compensated_payment_is_idempotent_after_matching_success():
    marker = {
        "order_id": 20833,
        "external_tx_key": "existing-key",
        "adopted_at": "2026-08-29T03:05:00",
    }
    target = SimpleNamespace(
        id=20833,
        order_id="WEB-PAID",
        business_order_id="bo-paid",
        internal_user_id=10000000004165,
        plan_id=2,
        final_price=Decimal("70.00"),
        payment_channel="RMB",
        payment_provider="ALIPAY_DIRECT",
        status="SUCCESS",
        tx_hash="ALIPAY-TRADE-1",
        paid_at=datetime(2026, 8, 29, 3, 5, 0),
        settlement_snapshot={},
        created_at=datetime(2026, 8, 29, 2, 29, 38),
    )
    gift = SimpleNamespace(
        id=20835,
        order_id="GIFT:4165:2:1",
        internal_user_id=10000000004165,
        plan_id=2,
        final_price=Decimal("0.00"),
        status="SUCCESS",
        tx_hash="manual_gift",
        paid_at=datetime(2026, 8, 29, 2, 58, 22),
        settlement_snapshot={"payment_compensation_adoption": marker},
        created_at=datetime(2026, 8, 29, 2, 58, 22),
    )
    user = SimpleNamespace(
        id=10000000004165,
        username="payer",
        telegram_id=123,
        credits=1201,
        current_identity="核心弟子",
        identity_expire_at=datetime(2026, 10, 8, 2, 58, 22),
    )
    session = _FakeSession([target, gift, user])
    dependencies = payment_fulfillment_service.PaymentFulfillmentDependencies(
        session_factory=lambda: _SessionContext(session),
        is_settlement_v2_enabled=lambda: True,
        settle_membership_plan_in_session_func=AsyncMock(),
        calculate_commission_func=AsyncMock(),
        record_affiliate_transaction_func=AsyncMock(),
        invalidate_invitation_cache_func=AsyncMock(),
    )

    result = await payment_fulfillment_service.adopt_compensated_rmb_payment(
        payment_fulfillment_service.CompensatedRMBPaymentAdoptionCommand(
            order_lookup="bo-paid",
            compensation_order_lookup="GIFT:4165:2:1",
            expected_internal_user_id=10000000004165,
            external_tx_id="ALIPAY-TRADE-1",
            paid_amount="70.00",
            source="prod_repair",
        ),
        dependencies=dependencies,
    )

    assert result.status == "noop"
    assert not session.added
    session.commit.assert_not_awaited()
    dependencies.calculate_commission_func.assert_not_awaited()
