from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from dashboard.backend.routers import stats as stats_router
from dashboard.backend.services import stats_service


def test_parse_stats_target_date_defaults_to_today():
    result = stats_service.parse_stats_target_date(None)

    assert result == stats_service.date.today()


def test_build_hourly_distribution_maps_none_hour_to_zero_slot():
    rows = [
        SimpleNamespace(hour=None, count=2),
        SimpleNamespace(hour=3, count=5),
    ]

    result = stats_service._build_hourly_distribution(rows)

    assert result["00"] == 2
    assert result["03"] == 5
    assert len(result) == 24


@pytest.mark.asyncio
async def test_get_stats_routes_through_loader(monkeypatch):
    expected = {"total_users": 1}
    loader = AsyncMock(return_value=expected)
    monkeypatch.setattr(stats_router, "load_dashboard_stats", loader)
    db = object()

    result = await stats_router.get_stats.__wrapped__(db=db)

    assert result == expected
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
async def test_get_stats_history_wraps_loader_exception(monkeypatch):
    loader = AsyncMock(side_effect=RuntimeError("boom"))
    monkeypatch.setattr(stats_router, "load_dashboard_stats_history", loader)
    db = object()

    with pytest.raises(HTTPException) as exc_info:
        await stats_router.get_stats_history.__wrapped__(days=7, db=db)

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "boom"
