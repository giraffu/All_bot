from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.dialects import postgresql

from scripts import backfill_affiliate_transactions as backfill_script


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _FakeReadSession:
    def __init__(self, rows):
        self.rows = rows
        self.execute = AsyncMock(return_value=_FakeResult(rows))


class _ApplySession:
    def __init__(self):
        self.commit = AsyncMock()


class _ApplyCandidateSession:
    def __init__(self, *, order=None, referral=None):
        self._order = order
        self._referral = referral

    async def get(self, model, _key):
        if model is backfill_script.Order:
            return self._order
        if model is backfill_script.Referral:
            return self._referral
        return None


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _build_order(
    *,
    order_pk: int,
    order_id: str,
    invitee_user_id: int = 2002,
    commission_usdt: str = "1.2500",
):
    return SimpleNamespace(
        id=order_pk,
        order_id=order_id,
        internal_user_id=invitee_user_id,
        commission_usdt=Decimal(commission_usdt),
    )


def _build_referral(referral_id: int, inviter_id: int = 1001):
    return SimpleNamespace(
        id=referral_id,
        inviter_id=inviter_id,
    )


@pytest.mark.asyncio
async def test_collect_backfill_candidates_classifies_rows_and_supports_filters():
    session = _FakeReadSession(
        [
            (_build_order(order_pk=1, order_id="ORD-1"), _build_referral(11), None),
            (_build_order(order_pk=2, order_id="ORD-2"), _build_referral(12), 99),
            (_build_order(order_pk=3, order_id="ORD-3"), None, None),
        ]
    )

    candidates = await backfill_script.collect_backfill_candidates(
        session,
        business_order_id="ORD-2",
    )

    assert len(candidates) == 3
    stmt = session.execute.await_args.args[0]
    compiled = stmt.compile(dialect=postgresql.dialect())
    sql = str(compiled)
    assert "orders.order_id =" in sql
    assert "affiliate_transactions.idempotency_key" in sql
    assert "affiliate_transactions.reference_type =" in sql
    assert "affiliate_transactions.reference_id =" in sql


@pytest.mark.asyncio
async def test_collect_backfill_candidates_supports_order_pk_filter_before_limit():
    session = _FakeReadSession([])

    await backfill_script.collect_backfill_candidates(
        session,
        order_pk=2,
        limit=1,
    )

    stmt = session.execute.await_args.args[0]
    compiled = stmt.compile(dialect=postgresql.dialect())
    sql = str(compiled)
    assert "orders.id =" in sql
    assert "LIMIT" in sql


@pytest.mark.asyncio
async def test_collect_backfill_candidates_rejects_ambiguous_numeric_deprecated_order_filter():
    session = _FakeReadSession([])

    with pytest.raises(ValueError, match="numeric --order-id is ambiguous"):
        await backfill_script.collect_backfill_candidates(
            session,
            order_filter="2",
        )


@pytest.mark.asyncio
async def test_apply_backfill_candidate_replays_historical_success_order_without_payment_metadata(
    monkeypatch,
):
    order = SimpleNamespace(
        id=1,
        status="SUCCESS",
        commission_usdt=Decimal("1.2500"),
        payment_channel="INVALID",
        paid_at=None,
        final_price=Decimal("10.00"),
    )
    referral = _build_referral(11)
    session = _ApplyCandidateSession(order=order, referral=referral)
    exists_mock = AsyncMock(return_value=False)
    record_mock = AsyncMock()

    monkeypatch.setattr(
        backfill_script, "_affiliate_commission_exists_for_order", exists_mock
    )
    monkeypatch.setattr(
        backfill_script, "record_affiliate_commission_transaction", record_mock
    )

    record_mock.return_value = True

    inserted = await backfill_script.apply_backfill_candidate(
        session,
        backfill_script.BackfillCandidate(
            order_pk=1,
            order_id="ORD-1",
            invitee_user_id=2002,
            inviter_id=1001,
            referral_id=11,
            commission_usdt=Decimal("1.2500"),
            status="should_insert",
        ),
    )

    assert inserted is True
    exists_mock.assert_awaited_once_with(session, 1)
    record_mock.assert_awaited_once_with(
        session,
        order,
        referral,
        source="backfill_script",
    )


@pytest.mark.asyncio
async def test_apply_backfill_candidate_skips_when_reference_already_exists(monkeypatch):
    order = SimpleNamespace(
        id=1,
        status="SUCCESS",
        commission_usdt=Decimal("1.2500"),
        payment_channel="RMB",
        paid_at=object(),
        final_price=Decimal("10.00"),
    )
    referral = _build_referral(11)
    session = _ApplyCandidateSession(order=order, referral=referral)
    exists_mock = AsyncMock(return_value=True)
    record_mock = AsyncMock()

    monkeypatch.setattr(
        backfill_script, "_affiliate_commission_exists_for_order", exists_mock
    )
    monkeypatch.setattr(
        backfill_script, "record_affiliate_commission_transaction", record_mock
    )

    inserted = await backfill_script.apply_backfill_candidate(
        session,
        backfill_script.BackfillCandidate(
            order_pk=1,
            order_id="ORD-1",
            invitee_user_id=2002,
            inviter_id=1001,
            referral_id=11,
            commission_usdt=Decimal("1.2500"),
            status="should_insert",
        ),
    )

    assert inserted is False
    exists_mock.assert_awaited_once_with(session, 1)
    record_mock.assert_not_awaited()


def test_summarize_backfill_candidates_counts_inviters_and_amount():
    candidates = [
        backfill_script.BackfillCandidate(
            order_pk=1,
            order_id="ORD-1",
            invitee_user_id=2002,
            inviter_id=1001,
            referral_id=11,
            commission_usdt=Decimal("1.2500"),
            status="should_insert",
        ),
        backfill_script.BackfillCandidate(
            order_pk=2,
            order_id="ORD-2",
            invitee_user_id=2003,
            inviter_id=1001,
            referral_id=12,
            commission_usdt=Decimal("0.5000"),
            status="already_exists",
        ),
        backfill_script.BackfillCandidate(
            order_pk=3,
            order_id="ORD-3",
            invitee_user_id=2004,
            inviter_id=None,
            referral_id=None,
            commission_usdt=Decimal("0.2000"),
            status="missing_referral",
        ),
    ]

    summary = backfill_script.summarize_backfill_candidates(
        candidates,
        mode="dry-run",
    )

    assert summary.mode == "dry-run"
    assert summary.candidate_orders == 3
    assert summary.should_insert == 1
    assert summary.already_exists == 1
    assert summary.missing_referral == 1
    assert summary.error == 0
    assert summary.inserted == 0
    assert summary.skipped_during_apply == 0
    assert summary.inviter_count == 1
    assert summary.amount_total == Decimal("1.2500")
    assert summary.to_dict() == {
        "mode": "dry-run",
        "candidate_orders": 3,
        "should_insert": 1,
        "already_exists": 1,
        "missing_referral": 1,
        "error": 0,
        "inviter_count": 1,
        "amount_total": 1.25,
    }


@pytest.mark.asyncio
async def test_backfill_affiliate_transactions_apply_only_processes_should_insert(monkeypatch):
    read_session = _FakeReadSession([])
    apply_session_1 = _ApplySession()
    apply_session_2 = _ApplySession()
    sessions = [read_session, apply_session_1, apply_session_2]

    candidates = [
        backfill_script.BackfillCandidate(
            order_pk=1,
            order_id="ORD-1",
            invitee_user_id=2002,
            inviter_id=1001,
            referral_id=11,
            commission_usdt=Decimal("1.2500"),
            status="should_insert",
        ),
        backfill_script.BackfillCandidate(
            order_pk=2,
            order_id="ORD-2",
            invitee_user_id=2003,
            inviter_id=1002,
            referral_id=12,
            commission_usdt=Decimal("0.7000"),
            status="should_insert",
        ),
        backfill_script.BackfillCandidate(
            order_pk=3,
            order_id="ORD-3",
            invitee_user_id=2004,
            inviter_id=1003,
            referral_id=13,
            commission_usdt=Decimal("0.8000"),
            status="already_exists",
        ),
    ]
    collect_mock = AsyncMock(return_value=candidates)
    apply_mock = AsyncMock(side_effect=[True, True])
    invalidate_mock = AsyncMock()

    def _session_factory():
        if not sessions:
            raise AssertionError("unexpected AsyncSessionLocal call")
        return _SessionContext(sessions.pop(0))

    monkeypatch.setattr(backfill_script, "AsyncSessionLocal", _session_factory)
    monkeypatch.setattr(backfill_script, "collect_backfill_candidates", collect_mock)
    monkeypatch.setattr(backfill_script, "apply_backfill_candidate", apply_mock)
    monkeypatch.setattr(
        backfill_script, "invalidate_invitation_recharge_cache", invalidate_mock
    )

    summary = await backfill_script.backfill_affiliate_transactions(
        apply=True,
        user_id=1001,
        order_pk=1,
        limit=10,
    )

    collect_mock.assert_awaited_once_with(
        read_session,
        user_id=1001,
        order_pk=1,
        business_order_id=None,
        order_filter=None,
        limit=10,
    )
    assert apply_mock.await_count == 2
    apply_session_1.commit.assert_awaited_once()
    apply_session_2.commit.assert_awaited_once()
    invalidate_mock.assert_any_await(1001)
    invalidate_mock.assert_any_await(1002)
    assert summary.mode == "apply"
    assert summary.should_insert == 2
    assert summary.inserted == 2
    assert summary.skipped_during_apply == 0
    assert summary.already_exists == 1
    assert summary.to_dict()["inserted"] == 2
    assert summary.to_dict()["skipped_during_apply"] == 0


@pytest.mark.asyncio
async def test_backfill_affiliate_transactions_apply_summary_tracks_conflicts_during_apply(
    monkeypatch,
):
    read_session = _FakeReadSession([])
    apply_session = _ApplySession()
    sessions = [read_session, apply_session]
    candidate = backfill_script.BackfillCandidate(
        order_pk=1,
        order_id="ORD-1",
        invitee_user_id=2002,
        inviter_id=1001,
        referral_id=11,
        commission_usdt=Decimal("1.2500"),
        status="should_insert",
    )
    collect_mock = AsyncMock(return_value=[candidate])
    apply_mock = AsyncMock(return_value=False)
    invalidate_mock = AsyncMock()

    def _session_factory():
        if not sessions:
            raise AssertionError("unexpected AsyncSessionLocal call")
        return _SessionContext(sessions.pop(0))

    monkeypatch.setattr(backfill_script, "AsyncSessionLocal", _session_factory)
    monkeypatch.setattr(backfill_script, "collect_backfill_candidates", collect_mock)
    monkeypatch.setattr(backfill_script, "apply_backfill_candidate", apply_mock)
    monkeypatch.setattr(
        backfill_script, "invalidate_invitation_recharge_cache", invalidate_mock
    )

    summary = await backfill_script.backfill_affiliate_transactions(apply=True)

    apply_session.commit.assert_awaited_once()
    invalidate_mock.assert_not_awaited()
    assert summary.should_insert == 1
    assert summary.inserted == 0
    assert summary.skipped_during_apply == 1
    assert summary.error == 0
    assert summary.to_dict()["inserted"] == 0
    assert summary.to_dict()["skipped_during_apply"] == 1


@pytest.mark.asyncio
async def test_backfill_affiliate_transactions_dry_run_uses_same_candidate_collection(monkeypatch):
    read_session = _FakeReadSession([])
    candidate = backfill_script.BackfillCandidate(
        order_pk=1,
        order_id="ORD-1",
        invitee_user_id=2002,
        inviter_id=1001,
        referral_id=11,
        commission_usdt=Decimal("1.2500"),
        status="should_insert",
    )
    collect_mock = AsyncMock(return_value=[candidate])

    monkeypatch.setattr(
        backfill_script, "AsyncSessionLocal", lambda: _SessionContext(read_session)
    )
    monkeypatch.setattr(backfill_script, "collect_backfill_candidates", collect_mock)

    summary = await backfill_script.backfill_affiliate_transactions(
        apply=False,
        user_id=1001,
        business_order_id="ORD-1",
        limit=5,
    )

    collect_mock.assert_awaited_once_with(
        read_session,
        user_id=1001,
        order_pk=None,
        business_order_id="ORD-1",
        order_filter=None,
        limit=5,
    )
    assert summary.mode == "dry-run"
    assert summary.should_insert == 1
    assert summary.inserted == 0
    assert summary.skipped_during_apply == 0
    assert summary.amount_total == Decimal("1.2500")
    serialized = summary.to_dict()
    assert "inserted" not in serialized
    assert "skipped_during_apply" not in serialized
