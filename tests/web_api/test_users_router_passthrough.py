from unittest.mock import AsyncMock, patch

import pytest

from src.web_api.routers import users as users_router


def _build_current_user():
    return type("User", (), {"id": 123, "username": "tester"})()


@pytest.mark.asyncio
async def test_get_favorite_apply_context_routes_to_service_without_router_side_dependencies():
    current_user = _build_current_user()
    db = object()

    with patch(
        "src.web_api.routers.users.get_history_apply_context_for_current_user",
        new=AsyncMock(return_value={"task_id": "task-1"}),
    ) as mock_service:
        response = await users_router.get_favorite_apply_context(
            "task-1",
            current_user=current_user,
            db=db,
        )

    assert response == {"task_id": "task-1"}
    mock_service.assert_awaited_once_with(
        task_id="task-1",
        current_user=current_user,
        db=db,
    )


@pytest.mark.asyncio
async def test_update_user_preferences_routes_to_current_user_service_wrapper():
    current_user = _build_current_user()
    db = object()
    prefs = type("Prefs", (), {"language_code": "en"})()

    with patch(
        "src.web_api.routers.users.update_current_user_preferences_payload",
        new=AsyncMock(return_value={"status": "success", "language_code": "en"}),
    ) as mock_service:
        response = await users_router.update_user_preferences(
            prefs,
            current_user=current_user,
            db=db,
        )

    assert response == {"status": "success", "language_code": "en"}
    mock_service.assert_awaited_once_with(
        prefs=prefs,
        current_user=current_user,
        db=db,
    )


@pytest.mark.asyncio
async def test_send_history_to_bot_routes_to_current_user_delivery_wrapper():
    current_user = _build_current_user()
    db = object()

    with patch(
        "src.web_api.routers.users.send_current_user_history_record_to_telegram",
        new=AsyncMock(return_value={"status": "success"}),
    ) as mock_service:
        response = await users_router.send_history_to_bot(
            "task-1",
            current_user=current_user,
            db=db,
        )

    assert response == {"status": "success"}
    mock_service.assert_awaited_once_with(
        task_id="task-1",
        current_user=current_user,
        db=db,
    )
