from unittest.mock import AsyncMock

import pytest

from dashboard.backend.routers import history as history_router


@pytest.mark.asyncio
async def test_get_all_history_routes_to_service(monkeypatch):
    expected = {"items": [{"id": 1}], "total": 1}
    service_mock = AsyncMock(return_value=expected)
    monkeypatch.setattr(history_router, "get_all_history_payload", service_mock)
    db = object()

    result = await history_router.get_all_history(
        page=2,
        page_size=10,
        type="img2img,video",
        rating=1,
        is_public=True,
        worker_id="worker-1",
        db=db,
    )

    assert result == expected
    service_mock.assert_awaited_once_with(
        db=db,
        page=2,
        page_size=10,
        type="img2img,video",
        rating=1,
        is_public=True,
        worker_id="worker-1",
        logger_override=history_router.logger,
    )


@pytest.mark.asyncio
async def test_get_user_history_routes_to_service(monkeypatch):
    expected = [{"id": 1}]
    service_mock = AsyncMock(return_value=expected)
    monkeypatch.setattr(history_router, "get_user_history_payload", service_mock)
    db = object()

    result = await history_router.get_user_history(123, db=db)

    assert result == expected
    service_mock.assert_awaited_once_with(
        user_id=123,
        db=db,
        logger_override=history_router.logger,
    )
