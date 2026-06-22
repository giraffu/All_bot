from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.services import referral_stats_service


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _FakeSession:
    def __init__(self, results):
        self._results = list(results)

    async def execute(self, _stmt):
        if not self._results:
            raise AssertionError("unexpected execute call")
        return _FakeResult(self._results.pop(0))


@pytest.mark.asyncio
async def test_query_referral_rewards_sums_commission_before_rounding(monkeypatch):
    async def _fake_rates():
        return {
            "ton_to_usdt": 1.4,
            "rmb_to_usdt": 1.0 / 6.7,
            "stars_to_usdt": 0.013,
        }

    monkeypatch.setattr(referral_stats_service, "get_exchange_rates", _fake_rates)

    inviter = SimpleNamespace(
        id=1,
        telegram_id=1001,
        full_name="Inviter",
        username="inviter",
    )
    invitee = SimpleNamespace(
        id=2,
        telegram_id=2002,
        full_name="Invitee",
        username="invitee",
    )
    created_at = datetime(2026, 5, 18, 12, 0, 0)
    order_1 = SimpleNamespace(
        order_id="ORD-1",
        final_price=Decimal("10.00"),
        payment_channel="RMB",
        commission_usdt=Decimal("0.0149"),
        paid_at=created_at,
        created_at=created_at,
    )
    order_2 = SimpleNamespace(
        order_id="ORD-2",
        final_price=Decimal("10.00"),
        payment_channel="RMB",
        commission_usdt=Decimal("0.0149"),
        paid_at=created_at,
        created_at=created_at,
    )
    session = _FakeSession(
        results=[
            [
                (order_1, inviter, invitee),
                (order_2, inviter, invitee),
            ],
            [(1, 1)],
            [(1, Decimal("0.0111"))],
        ]
    )

    rewards = await referral_stats_service.query_referral_rewards(session)

    assert len(rewards) == 1
    reward = rewards[0]
    assert reward["commission_usdt"] == 0.03
    assert reward["spent_commission_usdt"] == 0.01
    assert reward["invitees"][0]["commission_usdt"] == 0.03
    assert reward["total_invitees"] == 1
    assert reward["total_invitations"] == 1
    assert reward["total_rmb"] == 20.0


def test_round_money_uses_half_up_decimal_rounding():
    assert referral_stats_service._round_money(Decimal("0.015")) == 0.02
    assert referral_stats_service._round_money(Decimal("2.675")) == 2.68


@pytest.mark.asyncio
async def test_query_invitation_recharge_stats_reads_history_and_balance_from_ledger():
    session = _FakeSession(
        results=[
            [
                (2002, Decimal("10.00"), "RMB", Decimal("0.0149")),
                (2002, Decimal("99.00"), "RMB", Decimal("0.0000")),
                (3003, Decimal("2.50"), "TON", Decimal("0.0149")),
                (3003, Decimal("3.00"), "TON", Decimal("0.0000")),
                (4004, 100, "XTR", Decimal("0.1300")),
                (4004, 500, "XTR", Decimal("0.0000")),
            ],
            [
                (Decimal("1.2345"), Decimal("0.1111"), Decimal("1.1234")),
            ],
        ]
    )

    stats = await referral_stats_service.query_invitation_recharge_stats(session, 1001)

    assert stats == {
        "recharged_invitees_count": 3,
        "total_recharge_count": 3,
        "total_ton": 2.5,
        "total_rmb": 10.0,
        "total_stars": 100,
        "commission_usdt": 1.23,
        "total_commission_usdt": 1.23,
        "spent_commission_usdt": 0.11,
        "available_balance_usdt": 1.12,
    }


@pytest.mark.asyncio
async def test_query_invitation_recharge_stats_defaults_ledger_aggregates_to_zero():
    session = _FakeSession(
        results=[
            [
                (2002, Decimal("8.00"), "RMB", Decimal("1.2345")),
            ],
            [
                (None, None, None),
            ],
        ]
    )

    stats = await referral_stats_service.query_invitation_recharge_stats(session, 1001)

    assert stats["commission_usdt"] == 0.0
    assert stats["total_commission_usdt"] == 0.0
    assert stats["spent_commission_usdt"] == 0.0
    assert stats["available_balance_usdt"] == 0.0


@pytest.mark.asyncio
async def test_query_invitation_recharge_stats_can_show_non_zero_history_when_orders_sum_zero():
    session = _FakeSession(
        results=[
            [
                (2002, Decimal("8.00"), "RMB", Decimal("0.0000")),
            ],
            [
                (Decimal("300.0000"), Decimal("67.6500"), Decimal("232.3500")),
            ],
        ]
    )

    stats = await referral_stats_service.query_invitation_recharge_stats(session, 1001)

    assert stats["commission_usdt"] == 300.0
    assert stats["total_commission_usdt"] == 300.0
    assert stats["spent_commission_usdt"] == 67.65
    assert stats["available_balance_usdt"] == 232.35
