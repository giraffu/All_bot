from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.web_api import dependencies as web_dependencies
from src.web_api.routers import tasks as tasks_router
from src.web_api.routers import users as users_router
from src.web_api.schemas.auth_schema import UserResponse
from src.web_api.schemas.user_schema import CheckinResponse


def _build_test_app(*, current_user, db_session):
    app = FastAPI()
    app.include_router(tasks_router.router, prefix="/api/tasks")
    app.include_router(users_router.router, prefix="/api/users")

    async def _override_get_current_user():
        return current_user

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[tasks_router.get_current_user] = _override_get_current_user
    app.dependency_overrides[web_dependencies.get_current_user] = _override_get_current_user
    app.dependency_overrides[web_dependencies.get_db] = _override_get_db
    return app


async def _request(app: FastAPI, method: str, url: str, **kwargs):
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        return await client.request(method, url, **kwargs)


@pytest.mark.asyncio
async def test_cancel_pending_task_http_route_returns_payload():
    current_user = SimpleNamespace(id=123, telegram_id=456, username="tester")
    app = _build_test_app(current_user=current_user, db_session=object())

    with patch(
        "src.web_api.routers.tasks.cancel_pending_task_payload",
        new=AsyncMock(
            return_value={
                "status": "success",
                "message": "已取消",
                "cancel_state": "cancelled",
            }
        ),
    ) as payload_mock:
        response = await _request(app, "DELETE", "/api/tasks/cancel/task-1")

    assert response.status_code == 200
    assert response.json() == {
        "status": "success",
        "message": "已取消",
        "cancel_state": "cancelled",
    }
    payload_mock.assert_awaited_once_with(task_id="task-1", user_id=123)


@pytest.mark.asyncio
async def test_update_user_preferences_http_route_uses_body_and_db_dependency():
    current_user = SimpleNamespace(id=321, telegram_id=654321, username="tester")
    fake_db = object()
    app = _build_test_app(current_user=current_user, db_session=fake_db)

    with patch(
        "src.web_api.routers.users.update_user_language_preference_payload",
        new=AsyncMock(return_value={"status": "success", "language_code": "en"}),
    ) as payload_mock:
        response = await _request(
            app,
            "PATCH",
            "/api/users/preferences",
            json={"language_code": "en-US"},
        )

    assert response.status_code == 200
    assert response.json() == {"status": "success", "language_code": "en"}
    payload_mock.assert_awaited_once_with(
        db=fake_db,
        user_id=321,
        telegram_user_id=654321,
        language_code="en-US",
    )


@pytest.mark.asyncio
async def test_get_user_profile_http_route_returns_response_model_payload():
    current_user = SimpleNamespace(id=9, telegram_id=888, username="dao")
    app = _build_test_app(current_user=current_user, db_session=object())
    expected = UserResponse(
        id=9,
        telegram_id=888,
        username="dao",
        full_name="道友",
        language_code="zh",
        credits=120,
        user_group="筑基期",
        current_identity="核心弟子",
        priority=6,
        generation_count=34,
        checkin_count=12,
        invitation_count=9,
        breakthrough_conditions=[],
        is_unlocked=True,
    )

    with patch(
        "src.web_api.routers.users.get_current_user_profile_payload",
        new=AsyncMock(return_value=expected),
    ) as payload_mock:
        response = await _request(app, "GET", "/api/users/me")

    assert response.status_code == 200
    assert response.json()["id"] == 9
    assert response.json()["credits"] == 120
    assert response.json()["current_identity"] == "核心弟子"
    payload_mock.assert_awaited_once_with(current_user)


@pytest.mark.asyncio
async def test_checkin_user_http_route_returns_response_model_payload():
    current_user = SimpleNamespace(id=7, telegram_id=777, username="tester")
    app = _build_test_app(current_user=current_user, db_session=object())
    expected = CheckinResponse(
        success=True,
        current_credits=88,
        error_msg="",
        total_days=7,
        reward=5,
    )

    with patch(
        "src.web_api.routers.users.perform_user_checkin",
        new=AsyncMock(return_value=expected),
    ) as payload_mock:
        response = await _request(app, "POST", "/api/users/checkin")

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "current_credits": 88,
        "error_msg": "",
        "total_days": 7,
        "reward": 5,
    }
    payload_mock.assert_awaited_once_with(current_user)
