from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from dashboard.backend.routers import logs as logs_router
from dashboard.backend.services import log_admin_service


def test_parse_log_filter_date_handles_valid_invalid_and_end_of_day():
    assert log_admin_service.parse_log_filter_date(None) is None
    assert log_admin_service.parse_log_filter_date("invalid") is None
    assert log_admin_service.parse_log_filter_date("2026-05-23") == datetime(
        2026, 5, 23, 0, 0, 0
    )
    assert log_admin_service.parse_log_filter_date(
        "2026-05-23", end_of_day=True
    ) == datetime(2026, 5, 23, 23, 59, 59)


@pytest.mark.asyncio
async def test_get_logs_payload_parses_dates_before_calling_log_service(monkeypatch):
    service_mock = AsyncMock(return_value={"items": [], "total": 0})
    monkeypatch.setattr(log_admin_service.LogService, "get_logs", service_mock)

    result = await log_admin_service.get_logs_payload(
        user_id=7,
        username="alice",
        operation_type="gift",
        start_date="2026-05-01",
        end_date="2026-05-02",
        page=3,
        page_size=50,
    )

    assert result == {"items": [], "total": 0}
    service_mock.assert_awaited_once_with(
        user_id=7,
        username="alice",
        operation_type="gift",
        start_date=datetime(2026, 5, 1, 0, 0, 0),
        end_date=datetime(2026, 5, 2, 23, 59, 59),
        page=3,
        page_size=50,
    )


@pytest.mark.asyncio
async def test_get_logs_router_routes_to_service(monkeypatch):
    expected = {"items": [], "total": 0, "page": 1, "page_size": 20, "total_pages": 0}
    service_mock = AsyncMock(return_value=expected)
    monkeypatch.setattr(logs_router, "get_logs_payload", service_mock)

    result = await logs_router.get_logs(
        user_id=9,
        username="bob",
        operation_type="invite",
        start_date="2026-05-01",
        end_date="2026-05-03",
        page=2,
        page_size=10,
    )

    assert result == expected
    service_mock.assert_awaited_once_with(
        user_id=9,
        username="bob",
        operation_type="invite",
        start_date="2026-05-01",
        end_date="2026-05-03",
        page=2,
        page_size=10,
    )


@pytest.mark.asyncio
async def test_get_logs_router_wraps_service_exception(monkeypatch):
    service_mock = AsyncMock(side_effect=RuntimeError("boom"))
    monkeypatch.setattr(logs_router, "get_logs_payload", service_mock)

    with pytest.raises(HTTPException) as exc_info:
        await logs_router.get_logs()

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "boom"
