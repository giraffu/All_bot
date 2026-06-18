from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from paid_group_guard_bot.eligibility import (
    build_paid_group_eligibility_stmt,
    check_paid_group_eligibility,
)


class _Result:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _Session:
    def __init__(self, row):
        self.row = row
        self.statements = []

    async def execute(self, stmt):
        self.statements.append(stmt)
        return _Result(self.row)


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _session_factory(session):
    return lambda: _SessionContext(session)


def test_build_paid_group_eligibility_stmt_uses_success_paid_or_gift_order():
    stmt = build_paid_group_eligibility_stmt(12345)
    compiled = stmt.compile(dialect=postgresql.dialect())

    assert compiled.params["telegram_id_1"] == 12345
    assert "orders.status = " in str(compiled)
    assert "orders.paid_at IS NOT NULL" in str(compiled)
    assert compiled.params["status_1"] == "SUCCESS"
    assert compiled.params["tx_hash_1"] == "manual\\_%"
    assert compiled.params["order_id_1"] == "GIFT:%"


@pytest.mark.asyncio
async def test_check_paid_group_eligibility_allows_matching_order():
    row = SimpleNamespace(
        internal_user_id=9001,
        telegram_id=12345,
        matched_order_id=77,
    )
    session = _Session(row)

    decision = await check_paid_group_eligibility(
        12345,
        session_factory=_session_factory(session),
    )

    assert decision.eligible is True
    assert decision.reason == "matched_successful_paid_or_gift_order"
    assert decision.internal_user_id == 9001
    assert decision.matched_order_id == 77
    assert session.statements


@pytest.mark.asyncio
async def test_check_paid_group_eligibility_rejects_unknown_user():
    session = _Session(None)

    decision = await check_paid_group_eligibility(
        12345,
        session_factory=_session_factory(session),
    )

    assert decision.eligible is False
    assert decision.reason == "user_not_found"
    assert decision.internal_user_id is None


@pytest.mark.asyncio
async def test_check_paid_group_eligibility_rejects_user_without_order():
    row = SimpleNamespace(
        internal_user_id=9001,
        telegram_id=12345,
        matched_order_id=None,
    )
    session = _Session(row)

    decision = await check_paid_group_eligibility(
        12345,
        session_factory=_session_factory(session),
    )

    assert decision.eligible is False
    assert decision.reason == "no_successful_paid_or_gift_order"
    assert decision.internal_user_id == 9001

