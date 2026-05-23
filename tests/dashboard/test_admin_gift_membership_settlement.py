from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from dashboard.backend.routers import users as dashboard_users
from dashboard.backend.schemas import AdminGiftRequest


@pytest.mark.asyncio
async def test_admin_gift_plan_routes_to_service(monkeypatch):
    db = object()
    request = AdminGiftRequest(plan_id=1, note="test")
    expected = {"status": "ok", "message": "ok"}
    service_mock = AsyncMock(return_value=expected)
    monkeypatch.setattr(dashboard_users, "admin_gift_plan_payload", service_mock)

    result = await dashboard_users.admin_gift_plan(2002, request, db=db)

    assert result == expected
    service_mock.assert_awaited_once_with(
        user_id=2002,
        request=request,
        db=db,
        logger_override=dashboard_users.logger,
    )
