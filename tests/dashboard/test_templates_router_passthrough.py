from unittest.mock import AsyncMock

import pytest

from dashboard.backend.routers import templates as templates_router


@pytest.mark.asyncio
async def test_get_template_contributions_routes_to_service(monkeypatch):
    expected = [{"id": 1}]
    service_mock = AsyncMock(return_value=expected)
    monkeypatch.setattr(
        templates_router,
        "get_template_contributions_payload",
        service_mock,
    )
    db = object()

    result = await templates_router.get_template_contributions(db=db)

    assert result == expected
    service_mock.assert_awaited_once_with(db=db, logger_override=templates_router.logger)


@pytest.mark.asyncio
async def test_approve_contribution_routes_to_service(monkeypatch):
    expected = {"status": "ok"}
    service_mock = AsyncMock(return_value=expected)
    monkeypatch.setattr(templates_router, "approve_contribution_payload", service_mock)
    db = object()

    result = await templates_router.approve_contribution(7, db=db)

    assert result == expected
    service_mock.assert_awaited_once_with(
        contribution_id=7,
        db=db,
        logger_override=templates_router.logger,
    )


@pytest.mark.asyncio
async def test_delete_contribution_routes_to_service(monkeypatch):
    expected = {"status": "ok", "message": "Contribution deleted"}
    service_mock = AsyncMock(return_value=expected)
    monkeypatch.setattr(templates_router, "delete_contribution_payload", service_mock)
    db = object()

    result = await templates_router.delete_contribution(9, db=db)

    assert result == expected
    service_mock.assert_awaited_once_with(
        contribution_id=9,
        db=db,
        logger_override=templates_router.logger,
    )
