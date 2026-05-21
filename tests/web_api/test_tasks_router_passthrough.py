from unittest.mock import AsyncMock, patch

import pytest

from src.web_api.routers import tasks as tasks_router
from src.web_api.schemas.task_schema import TaskGenerateRequest, TaskGenerateResponse


def _build_current_user():
    return type("User", (), {"id": 123, "username": "tester"})()


@pytest.mark.asyncio
async def test_cancel_pending_task_routes_to_service():
    with patch(
        "src.web_api.routers.tasks.cancel_pending_task_payload",
        new=AsyncMock(return_value={"status": "success", "message": "已取消", "cancel_state": "cancelled"}),
    ) as mock_service:
        response = await tasks_router.cancel_pending_task("task-1", _build_current_user())

    assert response == {
        "status": "success",
        "message": "已取消",
        "cancel_state": "cancelled",
    }
    mock_service.assert_awaited_once_with(task_id="task-1", user_id=123)


@pytest.mark.asyncio
async def test_create_generation_task_routes_to_service():
    request = TaskGenerateRequest(task_type="image", inputs={"prompt": "foo"})
    expected = TaskGenerateResponse(
        task_id="task-1",
        status="submitted",
        message="任务已提交",
        cost=5,
        balance_remaining=95,
    )

    with patch(
        "src.web_api.routers.tasks.submit_generation_task_payload",
        new=AsyncMock(return_value=expected),
    ) as mock_service:
        response = await tasks_router.create_generation_task(
            request,
            current_user=_build_current_user(),
        )

    assert response == expected
    mock_service.assert_awaited_once()
