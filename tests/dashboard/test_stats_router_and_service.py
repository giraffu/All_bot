from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.dialects import postgresql

from dashboard.backend.routers import stats as stats_router
from dashboard.backend.services import stats_service
from dashboard.backend.services import stats_service_activity
from dashboard.backend.services import stats_service_task_efficiency
from dashboard.backend.services.stats_service_consumption import (
    GENERATION_CONSUMPTION_OPERATION_TYPES,
    build_generation_consumption_log_filter,
    build_generation_consumption_value,
    normalize_consumed_credit_total,
)
from dashboard.backend.services.stats_service_utils import day_bounds
from src.database.models import UserLog


class _FakeStatsDB:
    def __init__(self):
        self.bind = type(
            "Bind",
            (),
            {"dialect": type("Dialect", (), {"name": "postgresql"})()},
        )()
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return []


def _compile_postgresql(statement) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def test_parse_stats_target_date_defaults_to_today():
    result = stats_service.parse_stats_target_date(None)

    assert result == stats_service.date.today()


def test_stats_day_bounds_returns_half_open_range():
    target_date = stats_service.date(2026, 6, 10)

    start_date, end_date = day_bounds(target_date)

    assert start_date == target_date
    assert end_date == stats_service.date(2026, 6, 11)


def test_build_hourly_distribution_maps_none_hour_to_zero_slot():
    rows = [
        SimpleNamespace(hour=None, count=2),
        SimpleNamespace(hour=3, count=5),
    ]

    result = stats_service._build_hourly_distribution(rows)

    assert result["00"] == 2
    assert result["03"] == 5
    assert len(result) == 24


def test_consumed_credit_total_clamps_negative_net_refunds():
    assert normalize_consumed_credit_total(-18) == 0
    assert normalize_consumed_credit_total(None) == 0
    assert normalize_consumed_credit_total(42) == 42


def test_consumption_expression_uses_user_log_ledger():
    stmt = (
        select(func.sum(build_generation_consumption_value()))
        .select_from(UserLog)
        .where(build_generation_consumption_log_filter())
    )

    sql = _compile_postgresql(stmt).lower()

    assert "from user_logs" in sql
    assert "credit_change < 0" in sql
    assert "operation_type in" in sql
    assert "operation_type like 'refund%%'" in sql
    assert "from history" not in sql


def test_consumption_operation_types_include_dashboard_generation_aliases():
    assert "img2img_lora" in GENERATION_CONSUMPTION_OPERATION_TYPES
    assert "image_to_video" in GENERATION_CONSUMPTION_OPERATION_TYPES
    assert "face_video" in GENERATION_CONSUMPTION_OPERATION_TYPES


@pytest.mark.asyncio
async def test_get_stats_routes_through_loader(monkeypatch):
    stats_router._stats_cache.clear()
    stats_router._stats_cache_locks.clear()
    expected = {"total_users": 1}
    loader = AsyncMock(return_value=expected)
    monkeypatch.setattr(stats_router, "load_dashboard_stats", loader)
    db = object()

    result = await stats_router.get_stats(db=db)

    assert result == expected
    loader.assert_awaited_once_with(db=db, logger=stats_router.logger)


@pytest.mark.asyncio
async def test_get_finance_summary_routes_through_focused_loader(monkeypatch):
    stats_router._stats_cache.clear()
    stats_router._stats_cache_locks.clear()
    loader = AsyncMock(return_value={"rmb_balance": 88})
    monkeypatch.setattr(stats_router, "load_finance_dashboard_summary", loader)
    db = object()

    result = await stats_router.get_finance_summary(db=db)

    assert result == {"rmb_balance": 88}
    loader.assert_awaited_once_with(db=db, logger=stats_router.logger)


@pytest.mark.asyncio
async def test_get_hourly_stats_routes_through_loader(monkeypatch):
    expected = {"00": 0, "01": 2}
    loader = AsyncMock(return_value=expected)
    monkeypatch.setattr(stats_router, "load_hourly_generation_stats_by_date_str", loader)
    db = object()

    result = await stats_router.get_hourly_stats(date_str="2026-01-01", db=db)

    assert result == expected
    loader.assert_awaited_once_with(db=db, date_str="2026-01-01")


@pytest.mark.asyncio
async def test_load_hourly_generation_stats_by_date_str_parses_before_delegate(monkeypatch):
    loader = AsyncMock(return_value={"00": 1})
    monkeypatch.setattr(stats_service, "load_hourly_generation_stats", loader)
    db = object()

    result = await stats_service.load_hourly_generation_stats_by_date_str(
        db=db,
        date_str="2026-01-01",
    )

    assert result == {"00": 1}
    loader.assert_awaited_once()
    assert loader.await_args.kwargs["db"] is db
    assert str(loader.await_args.kwargs["target_date"]) == "2026-01-01"


@pytest.mark.asyncio
async def test_generation_stats_filter_created_at_without_date_function():
    db = _FakeStatsDB()

    await stats_service_activity.load_hourly_generation_stats_impl(
        db=db,
        target_date=stats_service.date(2026, 6, 10),
    )

    sql = _compile_postgresql(db.statements[0]).lower()
    assert "date(history.created_at)" not in sql
    assert "history.created_at >=" in sql
    assert "history.created_at <" in sql


@pytest.mark.asyncio
async def test_get_stats_history_wraps_loader_exception(monkeypatch):
    stats_router._stats_cache.clear()
    stats_router._stats_cache_locks.clear()
    loader = AsyncMock(side_effect=RuntimeError("boom"))
    monkeypatch.setattr(stats_router, "load_dashboard_stats_history", loader)
    db = object()

    with pytest.raises(HTTPException) as exc_info:
        await stats_router.get_stats_history(days=7, db=db)

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "boom"


def test_task_analytics_normalizes_billing_and_history_aliases():
    assert stats_service_task_efficiency.normalize_task_analytics_type("edit") == "img2img"
    assert (
        stats_service_task_efficiency.normalize_task_analytics_type("faceswap_step1")
        == "face_swap"
    )
    assert (
        stats_service_task_efficiency.normalize_task_analytics_type("ltx_video_flf2v")
        == "ltx_video"
    )
    assert (
        stats_service_task_efficiency.normalize_task_analytics_type("minimax_h3_ref2v")
        == "minimax_h3_ref2v"
    )


def test_build_task_credit_distribution_aggregates_aliases():
    rows = [
        SimpleNamespace(task_type="edit", credits=8),
        SimpleNamespace(task_type="image", credits=6),
        SimpleNamespace(task_type="minimax_h3_i2v", credits=42),
    ]

    result = stats_service_task_efficiency.build_task_credit_distribution(rows)

    assert result == {"img2img": 14, "minimax_h3_i2v": 42}


def test_build_task_gpu_efficiency_uses_5090_equivalent_calibration():
    credit_rows = [
        SimpleNamespace(task_type="minimax_h3_i2v", credits=90),
        SimpleNamespace(task_type="edit", credits=20),
        SimpleNamespace(task_type="character_reference_build", credits=18),
    ]
    history_rows = [
        SimpleNamespace(task_type="minimax_h3_i2v", task_count=6),
        SimpleNamespace(task_type="image", task_count=4),
        SimpleNamespace(task_type="character_reference_build", task_count=1),
    ]

    result = stats_service_task_efficiency.build_task_gpu_efficiency(
        credit_rows=credit_rows,
        history_rows=history_rows,
    )

    h3 = result["items"]["minimax_h3_i2v"]
    assert h3["credits"] == 90
    assert h3["task_count"] == 6
    assert h3["gpu_hours"] == pytest.approx(0.2475, abs=0.0001)
    assert h3["value"] == pytest.approx(363.64, abs=0.01)

    image = result["items"]["img2img"]
    assert image["credits"] == 20
    assert image["task_count"] == 4
    assert image["value"] == pytest.approx(1704.55, abs=0.01)

    assert result["uncovered_credits"] == 18
    assert result["calibration"] == "production_p50_5090_equivalent_v1"


@pytest.mark.asyncio
async def test_task_credit_distribution_query_uses_half_open_day_and_debits_only():
    db = _FakeStatsDB()

    await stats_service_task_efficiency.load_task_credit_distribution_stats(
        db=db,
        target_date=stats_service.date(2026, 6, 10),
    )

    sql = _compile_postgresql(db.statements[0]).lower()
    assert "from user_logs" in sql
    assert "credit_change < 0" in sql
    assert "credit_change > 0" not in sql
    assert "user_logs.created_at >=" in sql
    assert "user_logs.created_at <" in sql


@pytest.mark.asyncio
async def test_get_task_efficiency_routes_through_loader(monkeypatch):
    stats_router._stats_cache.clear()
    stats_router._stats_cache_locks.clear()
    expected = {"items": {"minimax_h3_i2v": {"value": 720}}}
    loader = AsyncMock(return_value=expected)
    monkeypatch.setattr(
        stats_router,
        "load_task_gpu_efficiency_stats_by_date_str",
        loader,
    )
    db = object()

    result = await stats_router.get_task_gpu_efficiency_stats(
        date_str="2026-01-01",
        db=db,
    )

    assert result == expected
    loader.assert_awaited_once_with(db=db, date_str="2026-01-01")


@pytest.mark.asyncio
async def test_get_task_credit_distribution_routes_through_loader(monkeypatch):
    stats_router._stats_cache.clear()
    stats_router._stats_cache_locks.clear()
    expected = {"values": {"minimax_h3_i2v": 120}}
    loader = AsyncMock(return_value=expected)
    monkeypatch.setattr(
        stats_router,
        "load_task_credit_distribution_stats_by_date_str",
        loader,
    )
    db = object()

    result = await stats_router.get_task_credit_distribution_stats(
        date_str="2026-01-01",
        db=db,
    )

    assert result == expected
    loader.assert_awaited_once_with(db=db, date_str="2026-01-01")
