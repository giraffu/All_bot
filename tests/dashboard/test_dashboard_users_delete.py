from unittest.mock import AsyncMock

import pytest

from dashboard.backend.routers import users as dashboard_users_router


@pytest.mark.asyncio
async def test_delete_user_routes_to_service(monkeypatch):
    expected = {"message": "User 123 and all associated data deleted successfully"}
    db = object()
    service_mock = AsyncMock(return_value=expected)
    monkeypatch.setattr(dashboard_users_router, "delete_user_payload", service_mock)

    response = await dashboard_users_router.delete_user(123, db=db)

    assert response == expected
    service_mock.assert_awaited_once_with(user_id=123, db=db, logger_override=dashboard_users_router.logger)
