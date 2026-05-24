import asyncio
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import delete, func, or_, select

from config import DATABASE_URL
from scripts import backfill_affiliate_transactions as backfill_script
from src.core import affiliate_core
from src.database.core import AsyncSessionLocal as DBSessionLocal
from src.database.core import engine as db_engine
from src.database.models import (
    AffiliateTransaction,
    MembershipPlan,
    Order,
    Referral,
    User,
    UserLog,
)
from src.handlers import payment_handler
from src.services import payment_fulfillment_service
from src.services import payment_validator


pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DATABASE_URL.startswith("postgresql"),
        reason="requires PostgreSQL row locks and unique constraints",
    ),
]


class _TwoPartyGate:
    def __init__(self):
        self._count = 0
        self._lock = asyncio.Lock()
        self._ready = asyncio.Event()

    async def wait(self) -> None:
        async with self._lock:
            self._count += 1
            if self._count >= 2:
                self._ready.set()
        await asyncio.wait_for(self._ready.wait(), timeout=5)


class _ProxySession:
    def __init__(self, session, gate: _TwoPartyGate | None):
        self._session = session
        self._gate = gate

    async def execute(self, stmt, *args, **kwargs):
        if self._gate and self._should_gate(stmt):
            await self._gate.wait()
        return await self._session.execute(stmt, *args, **kwargs)

    def __getattr__(self, item):
        return getattr(self._session, item)

    @staticmethod
    def _should_gate(stmt) -> bool:
        sql = str(stmt)
        return (
            ("FROM users" in sql and "FOR UPDATE" in sql)
            or ("FROM orders" in sql and "orders.tx_hash" in sql)
            or ("INSERT INTO orders" in sql and "tx_hash" in sql)
        )


class _ProxySessionContext:
    def __init__(self, session_factory, gate: _TwoPartyGate | None = None):
        self._session_factory = session_factory
        self._gate = gate
        self._raw_session = None
        self._proxy = None

    async def __aenter__(self):
        self._raw_session = self._session_factory()
        session = await self._raw_session.__aenter__()
        self._proxy = _ProxySession(session, self._gate)
        return self._proxy

    async def __aexit__(self, exc_type, exc, tb):
        return await self._raw_session.__aexit__(exc_type, exc, tb)


def _unique_suffix() -> str:
    return uuid.uuid4().hex[:12]


async def _fixed_rates():
    return {
        "rmb_to_usdt": Decimal("0.15"),
        "ton_to_usdt": Decimal("1.40"),
        "stars_to_usdt": Decimal("0.013"),
    }


async def _dispose_db_engine() -> None:
    await db_engine.dispose()


async def _create_affiliate_fixture(
    prefix: str,
    *,
    with_orders: bool,
    duration_days: int = 0,
    reward_credits: int = 10,
) -> dict:
    async with DBSessionLocal() as session:
        inviter = User(
            telegram_id=int(f"71{prefix[:8]}", 16) % 9_000_000_000_000_000,
            username=f"inviter_{prefix}",
            full_name=f"Inviter {prefix}",
            credits=0,
        )
        invitee = User(
            telegram_id=int(f"72{prefix[:8]}", 16) % 9_000_000_000_000_000,
            username=f"invitee_{prefix}",
            full_name=f"Invitee {prefix}",
            credits=0,
        )
        plan = MembershipPlan(
            name=f"affiliate-test-{prefix}",
            identity_name="外门弟子",
            price_ton=Decimal("1.00"),
            price_stars=100,
            price_rmb=Decimal("10.00"),
            reward_credits=reward_credits,
            duration_days=duration_days,
            is_active=True,
        )
        session.add_all([inviter, invitee, plan])
        await session.flush()

        referral = Referral(inviter_id=inviter.id, invitee_id=invitee.id)
        session.add(referral)
        await session.flush()

        order_ids: list[int] = []
        if with_orders:
            order_1 = Order(
                order_id=f"{prefix}-order-1",
                telegram_id=invitee.id,
                plan_id=plan.id,
                original_price=Decimal("10.00"),
                final_price=Decimal("10.00"),
                status="PENDING",
            )
            order_2 = Order(
                order_id=f"{prefix}-order-2",
                telegram_id=invitee.id,
                plan_id=plan.id,
                original_price=Decimal("10.00"),
                final_price=Decimal("10.00"),
                status="PENDING",
            )
            session.add_all([order_1, order_2])
            await session.flush()
            order_ids = [order_1.id, order_2.id]

        await session.commit()
        return {
            "plan_id": plan.id,
            "referral_id": referral.id,
            "inviter_id": inviter.id,
            "invitee_id": invitee.id,
            "invitee_telegram_id": invitee.telegram_id,
            "user_ids": [inviter.id, invitee.id],
            "order_ids": order_ids,
        }


async def _cleanup_affiliate_fixture(
    *,
    order_ids: list[int],
    user_ids: list[int],
    plan_id: int,
) -> None:
    async with DBSessionLocal() as session:
        if order_ids:
            order_id_refs = [str(order_id) for order_id in order_ids]
            await session.execute(
                delete(AffiliateTransaction).where(
                    AffiliateTransaction.reference_type == "ORDER",
                    AffiliateTransaction.reference_id.in_(order_id_refs),
                )
            )
            await session.execute(delete(Order).where(Order.id.in_(order_ids)))

        if user_ids:
            await session.execute(delete(UserLog).where(UserLog.user_id.in_(user_ids)))
            await session.execute(
                delete(Referral).where(
                    or_(
                        Referral.inviter_id.in_(user_ids),
                        Referral.invitee_id.in_(user_ids),
                    )
                )
            )
            await session.execute(delete(User).where(User.id.in_(user_ids)))

        await session.execute(delete(MembershipPlan).where(MembershipPlan.id == plan_id))
        await session.commit()


async def _mark_order_paid_and_record(
    order_id: int,
    paid_at: datetime,
    *,
    source: str,
) -> dict:
    async with DBSessionLocal() as session:
        order = await session.get(Order, order_id)
        order.status = "SUCCESS"
        order.payment_channel = "TON"
        order.paid_at = paid_at

        referral = await affiliate_core.calculate_and_set_commission_for_paid_order(
            session, order
        )
        inserted = False
        if referral and Decimal(str(order.commission_usdt or 0)) > 0:
            inserted = await affiliate_core.record_affiliate_commission_transaction(
                session,
                order,
                referral,
                source=source,
            )
        await session.commit()
        return {
            "order_id": order.id,
            "commission_usdt": Decimal(str(order.commission_usdt or 0)),
            "inserted": inserted,
        }


async def _create_backfill_fixture(prefix: str) -> dict:
    async with DBSessionLocal() as session:
        inviter = User(
            telegram_id=int(f"81{prefix[:8]}", 16) % 9_000_000_000_000_000,
            username=f"backfill_inviter_{prefix}",
            full_name=f"Backfill Inviter {prefix}",
            credits=0,
        )
        invitee_should_insert = User(
            telegram_id=int(f"82{prefix[:8]}", 16) % 9_000_000_000_000_000,
            username=f"backfill_should_{prefix}",
            full_name=f"Backfill Should {prefix}",
            credits=0,
        )
        invitee_already_exists = User(
            telegram_id=int(f"83{prefix[:8]}", 16) % 9_000_000_000_000_000,
            username=f"backfill_existing_{prefix}",
            full_name=f"Backfill Existing {prefix}",
            credits=0,
        )
        invitee_missing_referral = User(
            telegram_id=int(f"84{prefix[:8]}", 16) % 9_000_000_000_000_000,
            username=f"backfill_missing_{prefix}",
            full_name=f"Backfill Missing {prefix}",
            credits=0,
        )
        invitee_historical_anomaly = User(
            telegram_id=int(f"85{prefix[:8]}", 16) % 9_000_000_000_000_000,
            username=f"backfill_anomaly_{prefix}",
            full_name=f"Backfill Anomaly {prefix}",
            credits=0,
        )
        plan = MembershipPlan(
            name=f"backfill-plan-{prefix}",
            identity_name="外门弟子",
            price_ton=Decimal("1.00"),
            price_stars=100,
            price_rmb=Decimal("10.00"),
            reward_credits=10,
            duration_days=0,
            is_active=True,
        )
        session.add_all(
            [
                inviter,
                invitee_should_insert,
                invitee_already_exists,
                invitee_missing_referral,
                invitee_historical_anomaly,
                plan,
            ]
        )
        await session.flush()

        referral_should_insert = Referral(
            inviter_id=inviter.id, invitee_id=invitee_should_insert.id
        )
        referral_already_exists = Referral(
            inviter_id=inviter.id, invitee_id=invitee_already_exists.id
        )
        referral_historical_anomaly = Referral(
            inviter_id=inviter.id, invitee_id=invitee_historical_anomaly.id
        )
        session.add_all(
            [
                referral_should_insert,
                referral_already_exists,
                referral_historical_anomaly,
            ]
        )
        await session.flush()

        paid_at = datetime(2026, 5, 18, 12, 0, 0)
        order_should_insert = Order(
            order_id=f"{prefix}-should-insert",
            telegram_id=invitee_should_insert.id,
            plan_id=plan.id,
            original_price=Decimal("10.00"),
            final_price=Decimal("10.00"),
            status="SUCCESS",
            payment_channel="RMB",
            paid_at=paid_at,
            commission_usdt=Decimal("1.2500"),
        )
        order_already_exists = Order(
            order_id=f"{prefix}-already-exists",
            telegram_id=invitee_already_exists.id,
            plan_id=plan.id,
            original_price=Decimal("10.00"),
            final_price=Decimal("10.00"),
            status="SUCCESS",
            payment_channel="TON",
            paid_at=paid_at,
            commission_usdt=Decimal("0.5000"),
        )
        order_missing_referral = Order(
            order_id=f"{prefix}-missing-referral",
            telegram_id=invitee_missing_referral.id,
            plan_id=plan.id,
            original_price=Decimal("10.00"),
            final_price=Decimal("10.00"),
            status="SUCCESS",
            payment_channel="XTR",
            paid_at=paid_at,
            commission_usdt=Decimal("0.7000"),
        )
        order_historical_anomaly = Order(
            order_id=f"{prefix}-historical-anomaly",
            telegram_id=invitee_historical_anomaly.id,
            plan_id=plan.id,
            original_price=Decimal("0.00"),
            final_price=Decimal("0.00"),
            status="SUCCESS",
            payment_channel=None,
            paid_at=None,
            commission_usdt=Decimal("0.3333"),
        )
        session.add_all(
            [
                order_should_insert,
                order_already_exists,
                order_missing_referral,
                order_historical_anomaly,
            ]
        )
        await session.flush()

        session.add(
            AffiliateTransaction(
                user_id=inviter.id,
                amount_usdt=Decimal("0.5000"),
                transaction_type="COMMISSION_ACCRUAL",
                direction="IN",
                reference_type="ORDER",
                reference_id=str(order_already_exists.id),
                idempotency_key=f"affiliate:commission:order:{order_already_exists.id}",
                status="SUCCESS",
                details={
                    "order_pk": order_already_exists.id,
                    "order_id": order_already_exists.order_id,
                    "source": "existing_fixture",
                },
            )
        )

        await session.commit()
        return {
            "plan_id": plan.id,
            "inviter_id": inviter.id,
            "user_ids": [
                inviter.id,
                invitee_should_insert.id,
                invitee_already_exists.id,
                invitee_missing_referral.id,
                invitee_historical_anomaly.id,
            ],
            "order_ids": [
                order_should_insert.id,
                order_already_exists.id,
                order_missing_referral.id,
                order_historical_anomaly.id,
            ],
            "orders": {
                "should_insert": {
                    "pk": order_should_insert.id,
                    "order_id": order_should_insert.order_id,
                    "commission_usdt": Decimal("1.2500"),
                    "referral_id": referral_should_insert.id,
                },
                "already_exists": {
                    "pk": order_already_exists.id,
                    "order_id": order_already_exists.order_id,
                    "commission_usdt": Decimal("0.5000"),
                    "referral_id": referral_already_exists.id,
                },
                "missing_referral": {
                    "pk": order_missing_referral.id,
                    "order_id": order_missing_referral.order_id,
                },
                "historical_anomaly": {
                    "pk": order_historical_anomaly.id,
                    "order_id": order_historical_anomaly.order_id,
                    "commission_usdt": Decimal("0.3333"),
                    "referral_id": referral_historical_anomaly.id,
                },
            },
        }


def _build_stars_update(*, telegram_user_id: int, plan_id: int, charge_id: str):
    message = SimpleNamespace(
        successful_payment=SimpleNamespace(
            invoice_payload=f"ORDER:{telegram_user_id}:{plan_id}:999",
            total_amount=100,
            telegram_payment_charge_id=charge_id,
        ),
        reply_text=AsyncMock(),
    )
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=telegram_user_id),
        message=message,
    )


def _extract_reply_texts(update) -> list[str]:
    texts = []
    for awaited_call in update.message.reply_text.await_args_list:
        if awaited_call.args:
            texts.append(awaited_call.args[0])
    return texts


async def test_affiliate_commission_lock_serializes_same_invitee_on_real_db(monkeypatch):
    monkeypatch.setattr(affiliate_core, "get_exchange_rates", _fixed_rates)
    await _dispose_db_engine()

    prefix = _unique_suffix()
    fixture = await _create_affiliate_fixture(prefix, with_orders=True)
    paid_at_1 = datetime(2026, 5, 18, 12, 0, 0)
    paid_at_2 = paid_at_1 + timedelta(seconds=5)

    try:
        async with DBSessionLocal() as locked_session:
            locked_referral = (
                await locked_session.execute(
                    select(Referral)
                    .where(Referral.id == fixture["referral_id"])
                    .with_for_update()
                )
            ).scalar_one()
            assert locked_referral.id == fixture["referral_id"]

            task_2 = asyncio.create_task(
                _mark_order_paid_and_record(
                    fixture["order_ids"][1],
                    paid_at_2,
                    source="integration_second_order",
                )
            )

            await asyncio.sleep(0.2)
            assert not task_2.done()

            order_1 = await locked_session.get(Order, fixture["order_ids"][0])
            order_1.status = "SUCCESS"
            order_1.payment_channel = "TON"
            order_1.paid_at = paid_at_1

            referral = await affiliate_core.calculate_and_set_commission_for_paid_order(
                locked_session, order_1
            )
            inserted_first = False
            if referral and Decimal(str(order_1.commission_usdt or 0)) > 0:
                inserted_first = (
                    await affiliate_core.record_affiliate_commission_transaction(
                        locked_session,
                        order_1,
                        referral,
                        source="integration_first_order",
                    )
                )
            await locked_session.commit()

        second_result = await asyncio.wait_for(task_2, timeout=5)
        await asyncio.sleep(0.05)

        async with DBSessionLocal() as verify_session:
            orders = (
                (
                    await verify_session.execute(
                        select(Order)
                        .where(Order.id.in_(fixture["order_ids"]))
                        .order_by(Order.id.asc())
                    )
                )
                .scalars()
                .all()
            )
            txn_count = (
                await verify_session.execute(
                    select(func.count(AffiliateTransaction.id)).where(
                        AffiliateTransaction.reference_type == "ORDER",
                        AffiliateTransaction.reference_id.in_(
                            [str(order_id) for order_id in fixture["order_ids"]]
                        ),
                    )
                )
            ).scalar_one()

        positive_orders = [
            order.id
            for order in orders
            if Decimal(str(order.commission_usdt or 0)) > 0
        ]

        assert inserted_first is True
        assert second_result["inserted"] is False
        assert positive_orders == [fixture["order_ids"][0]]
        assert txn_count == 1
    finally:
        await _cleanup_affiliate_fixture(
            order_ids=fixture["order_ids"],
            user_ids=fixture["user_ids"],
            plan_id=fixture["plan_id"],
        )
        await _dispose_db_engine()


async def test_affiliate_commission_reverse_commit_order_only_records_one_ledger_entry(
    monkeypatch,
):
    monkeypatch.setattr(affiliate_core, "get_exchange_rates", _fixed_rates)
    await _dispose_db_engine()

    prefix = _unique_suffix()
    fixture = await _create_affiliate_fixture(prefix, with_orders=True)
    paid_at_1 = datetime(2026, 5, 18, 12, 0, 0)
    paid_at_2 = paid_at_1 + timedelta(seconds=5)

    try:
        async with DBSessionLocal() as locked_session:
            later_order = await locked_session.get(Order, fixture["order_ids"][1])
            later_order.status = "SUCCESS"
            later_order.payment_channel = "TON"
            later_order.paid_at = paid_at_2

            referral = await affiliate_core.calculate_and_set_commission_for_paid_order(
                locked_session, later_order
            )
            inserted_later = False
            if referral and Decimal(str(later_order.commission_usdt or 0)) > 0:
                inserted_later = (
                    await affiliate_core.record_affiliate_commission_transaction(
                        locked_session,
                        later_order,
                        referral,
                        source="integration_reverse_commit_later_first",
                    )
                )

            earlier_task = asyncio.create_task(
                _mark_order_paid_and_record(
                    fixture["order_ids"][0],
                    paid_at_1,
                    source="integration_reverse_commit_earlier_second",
                )
            )

            await asyncio.sleep(0.2)
            assert not earlier_task.done()

            await locked_session.commit()

        earlier_result = await asyncio.wait_for(earlier_task, timeout=5)
        await asyncio.sleep(0.05)

        async with DBSessionLocal() as verify_session:
            orders = (
                (
                    await verify_session.execute(
                        select(Order)
                        .where(Order.id.in_(fixture["order_ids"]))
                        .order_by(Order.id.asc())
                    )
                )
                .scalars()
                .all()
            )
            tx_count = (
                await verify_session.execute(
                    select(func.count(AffiliateTransaction.id)).where(
                        AffiliateTransaction.reference_type == "ORDER",
                        AffiliateTransaction.reference_id.in_(
                            [str(order_id) for order_id in fixture["order_ids"]]
                        ),
                    )
                )
            ).scalar_one()

        positive_orders = [
            order.id
            for order in orders
            if Decimal(str(order.commission_usdt or 0)) > 0
        ]

        assert inserted_later is True
        assert earlier_result["inserted"] is False
        assert positive_orders == [fixture["order_ids"][1]]
        assert tx_count == 1
    finally:
        await _cleanup_affiliate_fixture(
            order_ids=fixture["order_ids"],
            user_ids=fixture["user_ids"],
            plan_id=fixture["plan_id"],
        )
        await _dispose_db_engine()


async def test_stars_duplicate_charge_concurrent_callback_is_idempotent_on_real_db(
    monkeypatch,
):
    monkeypatch.setattr(affiliate_core, "get_exchange_rates", _fixed_rates)
    await _dispose_db_engine()
    monkeypatch.setattr(
        affiliate_core,
        "invalidate_invitation_recharge_cache",
        AsyncMock(),
    )

    gate = _TwoPartyGate()
    monkeypatch.setattr(
        payment_handler,
        "AsyncSessionLocal",
        lambda: _ProxySessionContext(DBSessionLocal, gate),
    )

    prefix = _unique_suffix()
    fixture = await _create_affiliate_fixture(prefix, with_orders=False)
    charge_id = f"charge-{prefix}"
    update_1 = _build_stars_update(
        telegram_user_id=fixture["invitee_telegram_id"],
        plan_id=fixture["plan_id"],
        charge_id=charge_id,
    )
    update_2 = _build_stars_update(
        telegram_user_id=fixture["invitee_telegram_id"],
        plan_id=fixture["plan_id"],
        charge_id=charge_id,
    )
    context = SimpleNamespace()

    try:
        await asyncio.wait_for(
            asyncio.gather(
                payment_handler.successful_payment_callback(update_1, context),
                payment_handler.successful_payment_callback(update_2, context),
            ),
            timeout=10,
        )
        await asyncio.sleep(0.05)

        async with DBSessionLocal() as session:
            orders = (
                (
                    await session.execute(
                        select(Order)
                        .where(Order.tx_hash == charge_id[:100])
                        .order_by(Order.id.asc())
                    )
                )
                .scalars()
                .all()
            )
            tx_count = (
                await session.execute(
                    select(func.count(AffiliateTransaction.id)).where(
                        AffiliateTransaction.reference_type == "ORDER",
                        AffiliateTransaction.reference_id.in_(
                            [str(order.id) for order in orders]
                        ),
                    )
                )
            ).scalar_one()

        reply_texts = _extract_reply_texts(update_1) + _extract_reply_texts(update_2)

        assert len(orders) == 1
        assert tx_count == 1
        assert "❌ 发货异常，请联系管理员核实订单。" not in reply_texts
    finally:
        async with DBSessionLocal() as session:
            created_orders = (
                (
                    await session.execute(
                        select(Order.id).where(
                            Order.order_id == f"ORDER:{fixture['invitee_telegram_id']}:{fixture['plan_id']}:999"[
                                :64
                            ]
                        )
                    )
                )
                .scalars()
                .all()
            )
        await _cleanup_affiliate_fixture(
            order_ids=list(created_orders),
            user_ids=fixture["user_ids"],
            plan_id=fixture["plan_id"],
        )
        await _dispose_db_engine()


async def test_ton_duplicate_tx_concurrent_callback_is_idempotent_on_real_db(
    monkeypatch,
):
    monkeypatch.setattr(affiliate_core, "get_exchange_rates", _fixed_rates)
    await _dispose_db_engine()
    monkeypatch.setattr(
        affiliate_core,
        "invalidate_invitation_recharge_cache",
        AsyncMock(),
    )

    gate = _TwoPartyGate()
    monkeypatch.setattr(
        payment_validator,
        "AsyncSessionLocal",
        lambda: _ProxySessionContext(DBSessionLocal, gate),
    )

    prefix = _unique_suffix()
    fixture = await _create_affiliate_fixture(
        prefix,
        with_orders=False,
        duration_days=30,
        reward_credits=20,
    )
    tx_hash = f"ton-hash-{prefix}"
    order_id = f"ORDER:{fixture['invitee_telegram_id']}:{fixture['plan_id']}:999"
    validator = payment_validator.TonPaymentValidator(
        SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()))
    )

    async def _fake_get_or_create_user_by_telegram(_telegram_id, **_kwargs):
        return SimpleNamespace(id=fixture["invitee_id"]), False

    monkeypatch.setattr(
        "src.core.user_core.get_or_create_user_by_telegram",
        _fake_get_or_create_user_by_telegram,
    )

    try:
        from src.constants import TON_TO_NANOTON

        results = await asyncio.wait_for(
            asyncio.gather(
                validator._process_order(
                    order_id,
                    int(Decimal("1.00") * Decimal(str(TON_TO_NANOTON))),
                    tx_hash,
                ),
                validator._process_order(
                    order_id,
                    int(Decimal("1.00") * Decimal(str(TON_TO_NANOTON))),
                    tx_hash,
                ),
            ),
            timeout=10,
        )
        await asyncio.sleep(0.05)

        async with DBSessionLocal() as session:
            orders = (
                (
                    await session.execute(
                        select(Order)
                        .where(Order.tx_hash == tx_hash)
                        .order_by(Order.id.asc())
                    )
                )
                .scalars()
                .all()
            )
            tx_count = (
                await session.execute(
                    select(func.count(AffiliateTransaction.id)).where(
                        AffiliateTransaction.reference_type == "ORDER",
                        AffiliateTransaction.reference_id.in_(
                            [str(order.id) for order in orders]
                        ),
                    )
                )
            ).scalar_one()

        assert results == [True, True]
        assert len(orders) == 1
        assert tx_count == 1
    finally:
        async with DBSessionLocal() as session:
            created_orders = (
                (
                    await session.execute(
                        select(Order.id).where(Order.tx_hash == tx_hash)
                    )
                )
                .scalars()
                .all()
            )
        await _cleanup_affiliate_fixture(
            order_ids=list(created_orders),
            user_ids=fixture["user_ids"],
            plan_id=fixture["plan_id"],
        )
        await _dispose_db_engine()


async def test_rmb_duplicate_notify_concurrent_callback_is_idempotent_on_real_db(
    monkeypatch,
):
    monkeypatch.setattr(affiliate_core, "get_exchange_rates", _fixed_rates)
    await _dispose_db_engine()

    invalidate_mock = AsyncMock()
    monkeypatch.setattr(
        payment_fulfillment_service,
        "invalidate_invitation_recharge_cache",
        invalidate_mock,
    )
    monkeypatch.delenv("BOT_TOKEN", raising=False)

    prefix = _unique_suffix()
    fixture = await _create_affiliate_fixture(
        prefix,
        with_orders=True,
        duration_days=30,
        reward_credits=100,
    )
    target_order_id = fixture["order_ids"][0]
    out_trade_no = f"{prefix}-order-1"
    external_trade_no = f"rmb-trade-{prefix}"

    try:
        async with DBSessionLocal() as locked_session:
            locked_order = (
                await locked_session.execute(
                    select(Order)
                    .where(Order.id == target_order_id)
                    .with_for_update()
                )
            ).scalar_one()
            assert locked_order.id == target_order_id

            task_1 = asyncio.create_task(
                payment_fulfillment_service.fulfill_order(
                    out_trade_no,
                    external_trade_no,
                    10.0,
                )
            )
            task_2 = asyncio.create_task(
                payment_fulfillment_service.fulfill_order(
                    out_trade_no,
                    external_trade_no,
                    10.0,
                )
            )

            await asyncio.sleep(0.2)
            assert not task_1.done()
            assert not task_2.done()

            await locked_session.commit()

        results = await asyncio.wait_for(asyncio.gather(task_1, task_2), timeout=10)
        await asyncio.sleep(0.05)

        async with DBSessionLocal() as session:
            order = await session.get(Order, target_order_id)
            user = await session.get(User, fixture["invitee_id"])
            tx_count = (
                await session.execute(
                    select(func.count(AffiliateTransaction.id)).where(
                        AffiliateTransaction.reference_type == "ORDER",
                        AffiliateTransaction.reference_id == str(target_order_id),
                    )
                )
            ).scalar_one()

        assert results == [True, True]
        assert order is not None
        assert order.status == "SUCCESS"
        assert order.payment_channel == "RMB"
        assert order.tx_hash == external_trade_no
        assert user is not None
        assert user.credits == 100
        assert tx_count == 1
        invalidate_mock.assert_awaited_once_with(fixture["inviter_id"])
    finally:
        await _cleanup_affiliate_fixture(
            order_ids=fixture["order_ids"],
            user_ids=fixture["user_ids"],
            plan_id=fixture["plan_id"],
        )
        await _dispose_db_engine()


async def test_backfill_affiliate_transactions_real_db_classifies_and_applies(
    monkeypatch,
):
    await _dispose_db_engine()
    prefix = _unique_suffix()
    fixture = await _create_backfill_fixture(prefix)
    invalidate_mock = AsyncMock()
    monkeypatch.setattr(
        backfill_script, "invalidate_invitation_recharge_cache", invalidate_mock
    )

    try:
        async with DBSessionLocal() as session:
            should_insert_candidates = await backfill_script.collect_backfill_candidates(
                session,
                business_order_id=fixture["orders"]["should_insert"]["order_id"],
            )
            already_exists_candidates = (
                await backfill_script.collect_backfill_candidates(
                    session,
                    business_order_id=fixture["orders"]["already_exists"]["order_id"],
                )
            )
            missing_referral_candidates = (
                await backfill_script.collect_backfill_candidates(
                    session,
                    business_order_id=fixture["orders"]["missing_referral"]["order_id"],
                )
            )

        assert len(should_insert_candidates) == 1
        assert should_insert_candidates[0].status == "should_insert"
        assert (
            should_insert_candidates[0].referral_id
            == fixture["orders"]["should_insert"]["referral_id"]
        )
        assert (
            should_insert_candidates[0].commission_usdt
            == fixture["orders"]["should_insert"]["commission_usdt"]
        )

        assert len(already_exists_candidates) == 1
        assert already_exists_candidates[0].status == "already_exists"
        assert (
            already_exists_candidates[0].referral_id
            == fixture["orders"]["already_exists"]["referral_id"]
        )

        assert len(missing_referral_candidates) == 1
        assert missing_referral_candidates[0].status == "missing_referral"
        assert missing_referral_candidates[0].referral_id is None
        assert missing_referral_candidates[0].inviter_id is None

        async with DBSessionLocal() as session:
            historical_anomaly_candidates = (
                await backfill_script.collect_backfill_candidates(
                    session,
                    business_order_id=fixture["orders"]["historical_anomaly"]["order_id"],
                )
            )

        assert len(historical_anomaly_candidates) == 1
        assert historical_anomaly_candidates[0].status == "should_insert"
        assert (
            historical_anomaly_candidates[0].referral_id
            == fixture["orders"]["historical_anomaly"]["referral_id"]
        )
        assert (
            historical_anomaly_candidates[0].commission_usdt
            == fixture["orders"]["historical_anomaly"]["commission_usdt"]
        )

        apply_summary = await backfill_script.backfill_affiliate_transactions(
            apply=True,
            business_order_id=fixture["orders"]["should_insert"]["order_id"],
        )

        assert apply_summary.mode == "apply"
        assert apply_summary.candidate_orders == 1
        assert apply_summary.should_insert == 1
        assert apply_summary.already_exists == 0
        assert apply_summary.missing_referral == 0
        assert apply_summary.error == 0
        assert apply_summary.inserted == 1
        assert apply_summary.skipped_during_apply == 0
        assert apply_summary.inviter_count == 1
        assert (
            apply_summary.amount_total
            == fixture["orders"]["should_insert"]["commission_usdt"]
        )
        invalidate_mock.assert_awaited_once_with(fixture["inviter_id"])

        async with DBSessionLocal() as session:
            inserted_tx = (
                await session.execute(
                    select(AffiliateTransaction).where(
                        AffiliateTransaction.idempotency_key
                        == f"affiliate:commission:order:{fixture['orders']['should_insert']['pk']}"
                    )
                )
            ).scalar_one_or_none()
            post_apply_candidates = await backfill_script.collect_backfill_candidates(
                session,
                business_order_id=fixture["orders"]["should_insert"]["order_id"],
            )

        assert inserted_tx is not None
        assert inserted_tx.reference_type == "ORDER"
        assert (
            inserted_tx.reference_id
            == str(fixture["orders"]["should_insert"]["pk"])
        )
        assert inserted_tx.amount_usdt == fixture["orders"]["should_insert"][
            "commission_usdt"
        ]
        assert inserted_tx.details["source"] == "backfill_script"
        assert len(post_apply_candidates) == 1
        assert post_apply_candidates[0].status == "already_exists"

        anomaly_summary = await backfill_script.backfill_affiliate_transactions(
            apply=True,
            business_order_id=fixture["orders"]["historical_anomaly"]["order_id"],
        )

        assert anomaly_summary.mode == "apply"
        assert anomaly_summary.candidate_orders == 1
        assert anomaly_summary.should_insert == 1
        assert anomaly_summary.inserted == 1
        assert anomaly_summary.skipped_during_apply == 0

        async with DBSessionLocal() as session:
            anomaly_tx = (
                await session.execute(
                    select(AffiliateTransaction).where(
                        AffiliateTransaction.idempotency_key
                        == f"affiliate:commission:order:{fixture['orders']['historical_anomaly']['pk']}"
                    )
                )
            ).scalar_one_or_none()

        assert anomaly_tx is not None
        assert (
            anomaly_tx.amount_usdt
            == fixture["orders"]["historical_anomaly"]["commission_usdt"]
        )
    finally:
        await _cleanup_affiliate_fixture(
            order_ids=fixture["order_ids"],
            user_ids=fixture["user_ids"],
            plan_id=fixture["plan_id"],
        )
        await _dispose_db_engine()


async def test_backfill_affiliate_transactions_treats_same_order_reference_as_existing(
    monkeypatch,
):
    await _dispose_db_engine()
    prefix = _unique_suffix()
    fixture = await _create_backfill_fixture(prefix)
    invalidate_mock = AsyncMock()
    monkeypatch.setattr(
        backfill_script, "invalidate_invitation_recharge_cache", invalidate_mock
    )

    try:
        target_order_pk = fixture["orders"]["should_insert"]["pk"]
        async with DBSessionLocal() as session:
            session.add(
                AffiliateTransaction(
                    user_id=fixture["inviter_id"],
                    amount_usdt=fixture["orders"]["should_insert"]["commission_usdt"],
                    transaction_type="COMMISSION_ACCRUAL",
                    direction="IN",
                    reference_type="ORDER",
                    reference_id=str(target_order_pk),
                    idempotency_key=f"manual-import-order:{target_order_pk}",
                    status="SUCCESS",
                    details={
                        "order_pk": target_order_pk,
                        "order_id": fixture["orders"]["should_insert"]["order_id"],
                        "source": "manual_import",
                    },
                )
            )
            await session.commit()

        async with DBSessionLocal() as session:
            candidates = await backfill_script.collect_backfill_candidates(
                session,
                business_order_id=fixture["orders"]["should_insert"]["order_id"],
            )

        assert len(candidates) == 1
        assert candidates[0].status == "already_exists"

        apply_summary = await backfill_script.backfill_affiliate_transactions(
            apply=True,
            business_order_id=fixture["orders"]["should_insert"]["order_id"],
        )

        assert apply_summary.mode == "apply"
        assert apply_summary.candidate_orders == 1
        assert apply_summary.should_insert == 0
        assert apply_summary.already_exists == 1
        assert apply_summary.inserted == 0
        assert apply_summary.skipped_during_apply == 0
        invalidate_mock.assert_not_awaited()

        async with DBSessionLocal() as session:
            tx_count = (
                await session.execute(
                    select(func.count(AffiliateTransaction.id)).where(
                        AffiliateTransaction.reference_type == "ORDER",
                        AffiliateTransaction.reference_id == str(target_order_pk),
                    )
                )
            ).scalar_one()

        assert tx_count == 1
    finally:
        await _cleanup_affiliate_fixture(
            order_ids=fixture["order_ids"],
            user_ids=fixture["user_ids"],
            plan_id=fixture["plan_id"],
        )
        await _dispose_db_engine()
