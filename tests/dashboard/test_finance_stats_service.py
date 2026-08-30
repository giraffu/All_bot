from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from dashboard.backend.services.stats_service_finance import (
    build_finance_history_payload,
    load_finance_dashboard_history_impl,
    serialize_rmb_channel_totals,
)


def _channel_row(**overrides):
    values = {
        "rmb_total": 100,
        "direct_alipay_amount": 40,
        "direct_alipay_orders": 2,
        "collected_alipay_amount": 30,
        "collected_alipay_orders": 3,
        "collected_wechat_amount": 20,
        "collected_wechat_orders": 4,
        "legacy_unclassified_amount": 10,
        "legacy_unclassified_orders": 1,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_finance_summary_preserves_three_rmb_channels_and_legacy_bucket():
    result = serialize_rmb_channel_totals(_channel_row())

    assert result == {
        "direct_alipay": {"amount": 40.0, "orders": 2},
        "collected_alipay": {"amount": 30.0, "orders": 3},
        "collected_wechat": {"amount": 20.0, "orders": 4},
        "legacy_unclassified": {"amount": 10.0, "orders": 1},
    }


def test_finance_history_returns_daily_and_cumulative_channel_amounts():
    before = _channel_row(
        rmb_total=10,
        direct_alipay_amount=4,
        collected_alipay_amount=3,
        collected_wechat_amount=2,
        legacy_unclassified_amount=1,
        ton_sum=1,
        stars_sum=10,
        credits_sum=100,
    )
    daily = [
        SimpleNamespace(
            date=date(2026, 8, 30),
            rmb_sum=20,
            direct_alipay_amount=8,
            collected_alipay_amount=6,
            collected_wechat_amount=4,
            legacy_unclassified_amount=2,
            ton_sum=2,
            stars_sum=20,
            credits_sum=200,
            inner_count=1,
            core_count=2,
            true_count=3,
        )
    ]

    result = build_finance_history_payload(
        start_date=date(2026, 8, 30),
        days=1,
        before_row=before,
        daily_rows=daily,
        rates={"ton_to_usdt": 1, "stars_to_usdt": 0.1, "rmb_to_usdt": 0.2},
    )

    assert result[0]["rmb_direct_alipay"] == 8.0
    assert result[0]["rmb_collected_alipay"] == 6.0
    assert result[0]["rmb_collected_wechat"] == 4.0
    assert result[0]["rmb_legacy_unclassified"] == 2.0
    assert result[0]["cumulative_rmb_direct_alipay"] == 12.0
    assert result[0]["cumulative_rmb"] == 30.0
    assert result[0]["usdt_recharge"] == 8.0


class _Result:
    def __init__(self, *, first=None, rows=()):
        self._first = first
        self._rows = rows

    def first(self):
        return self._first

    def __iter__(self):
        return iter(self._rows)


class _FinanceHistoryDB:
    def __init__(self, before, daily):
        self.responses = [_Result(first=before), _Result(rows=daily)]
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return self.responses.pop(0)


@pytest.mark.asyncio
async def test_finance_history_uses_two_focused_order_queries(monkeypatch):
    before = _channel_row(ton_sum=0, stars_sum=0, credits_sum=0)
    db = _FinanceHistoryDB(before, [])
    monkeypatch.setattr(
        "dashboard.backend.services.stats_service_finance.get_exchange_rates",
        AsyncMock(return_value={
            "ton_to_usdt": 1,
            "stars_to_usdt": 1,
            "rmb_to_usdt": 1,
        }),
    )

    result = await load_finance_dashboard_history_impl(db=db, days=1)

    assert len(db.statements) == 2
    assert len(result) == 1
