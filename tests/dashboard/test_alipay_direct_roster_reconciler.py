import asyncio
import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.dialects import postgresql

from dashboard.backend.services import alipay_direct_roster_reconciler
from src.database.models import UserLog


class _ScalarRows:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return self

    def all(self):
        return self._values


class _FakeSession:
    def __init__(self, users):
        self.users = users
        self.statements = []
        self.added = []
        self.commit = AsyncMock()
        self.rollback = AsyncMock()

    async def execute(self, stmt):
        self.statements.append(stmt)
        return _ScalarRows(self.users)

    def add(self, value):
        self.added.append(value)


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _user(user_id: int):
    return SimpleNamespace(
        id=user_id,
        username=f"payer-{user_id}",
        full_name=None,
        credits=100 + user_id,
        alipay_direct_enabled=True,
    )


@pytest.mark.asyncio
async def test_successful_direct_payers_are_removed_from_roster_in_one_transaction():
    users = [_user(11), _user(12)]
    session = _FakeSession(users)
    changed_at = datetime(2026, 8, 28, 23, 10, 0)
    dependencies = alipay_direct_roster_reconciler.AlipayDirectRosterDependencies(
        session_factory=lambda: _SessionContext(session),
        now_func=lambda: changed_at,
    )

    changed = await alipay_direct_roster_reconciler.reconcile_alipay_direct_roster_once(
        dependencies=dependencies,
        batch_size=500,
    )

    assert changed == 2
    assert [user.alipay_direct_enabled for user in users] == [False, False]
    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()
    assert len(session.added) == 2
    assert all(isinstance(log, UserLog) for log in session.added)
    assert {log.operation_type for log in session.added} == {
        "auto_disable_alipay_direct_after_payment"
    }
    assert {log.created_at for log in session.added} == {changed_at}
    assert {
        json.loads(log.extra_info)["reason"] for log in session.added
    } == {"successful_alipay_direct_payment"}

    sql = str(session.statements[0].compile(dialect=postgresql.dialect()))
    assert "orders.payment_provider" in sql
    assert "orders.status" in sql
    assert "orders.paid_at IS NOT NULL" in sql
    assert "users.alipay_direct_enabled IS true" in sql
    assert "FOR UPDATE OF users SKIP LOCKED" in sql


@pytest.mark.asyncio
async def test_empty_roster_reconciliation_does_not_create_a_write_transaction():
    session = _FakeSession([])
    dependencies = alipay_direct_roster_reconciler.AlipayDirectRosterDependencies(
        session_factory=lambda: _SessionContext(session),
        now_func=datetime.now,
    )

    changed = await alipay_direct_roster_reconciler.reconcile_alipay_direct_roster_once(
        dependencies=dependencies,
    )

    assert changed == 0
    assert session.added == []
    session.commit.assert_not_awaited()
    session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_periodic_reconciler_stops_without_waiting_for_another_interval():
    stop_event = asyncio.Event()
    reconcile_once = AsyncMock(side_effect=lambda: stop_event.set() or 3)

    await alipay_direct_roster_reconciler.run_alipay_direct_roster_reconciler(
        stop_event=stop_event,
        interval_seconds=60,
        reconcile_once_func=reconcile_once,
    )

    reconcile_once.assert_awaited_once()


@pytest.mark.asyncio
async def test_periodic_reconciler_defaults_to_five_minutes(monkeypatch):
    observed_delays = []

    async def cancel_after_observing_delay(delay):
        observed_delays.append(delay)
        raise asyncio.CancelledError

    monkeypatch.delenv(
        "DASHBOARD_ALIPAY_DIRECT_RECONCILE_INTERVAL_SECONDS",
        raising=False,
    )
    monkeypatch.setattr(
        alipay_direct_roster_reconciler.asyncio,
        "sleep",
        cancel_after_observing_delay,
    )

    with pytest.raises(asyncio.CancelledError):
        await alipay_direct_roster_reconciler.run_alipay_direct_roster_reconciler(
            reconcile_once_func=AsyncMock(return_value=0),
        )

    assert observed_delays == [300]
