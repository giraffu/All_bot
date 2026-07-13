from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from dashboard.backend.routers.system import (
    RefundTaskRequest,
    SyncLockRequest,
    clean_zombie_tasks,
    get_system_status_proxy,
    refund_bot_task,
    sync_user_concurrency,
)
from src.core.task_core_runtime import force_terminate_task


@pytest.mark.asyncio
async def test_force_terminate_task_cancels_backend_and_clears_registry(monkeypatch):
    redis_client = SimpleNamespace(
        get_active_tasks=AsyncMock(
            return_value={
                "registry-task-1": {
                    "user_id": 123,
                    "backend_task_id": "backend-task-1",
                }
            }
        ),
    )
    api_client = SimpleNamespace(cancel_task=AsyncMock())
    cleanup_runtime = AsyncMock()

    async def cancel_backend(*, backend_task_id: str, registry_task_id: str, raise_on_error: bool):
        assert registry_task_id == "registry-task-1"
        assert raise_on_error is True
        await api_client.cancel_task(backend_task_id)
        return True

    await force_terminate_task(
        "registry-task-1",
        submission_outbox=redis_client,
        cleanup_task_runtime_state_func=cleanup_runtime,
        cancel_backend_task_best_effort_func=cancel_backend,
    )

    api_client.cancel_task.assert_awaited_once_with("backend-task-1")
    cleanup_runtime.assert_awaited_once_with(
        internal_user_id=123,
        registry_task_id="registry-task-1",
        release_lock=True,
    )


@pytest.mark.asyncio
async def test_force_terminate_task_treats_missing_backend_task_as_already_cancelled(
    monkeypatch,
):
    request = httpx.Request("DELETE", "http://example.com/api/tasks/backend-task-1")
    response = httpx.Response(404, request=request)
    redis_client = SimpleNamespace(
        get_active_tasks=AsyncMock(
            return_value={
                "registry-task-1": {
                    "user_id": 123,
                    "backend_task_id": "backend-task-1",
                }
            }
        ),
    )
    api_client = SimpleNamespace(
        cancel_task=AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "not found", request=request, response=response
            )
        )
    )
    cleanup_runtime = AsyncMock()

    async def cancel_backend(*, backend_task_id: str, registry_task_id: str, raise_on_error: bool):
        assert registry_task_id == "registry-task-1"
        assert raise_on_error is True
        try:
            return await api_client.cancel_task(backend_task_id)
        except httpx.HTTPStatusError as exc:
            assert exc.response.status_code == 404
            return False

    await force_terminate_task(
        "registry-task-1",
        submission_outbox=redis_client,
        cleanup_task_runtime_state_func=cleanup_runtime,
        cancel_backend_task_best_effort_func=cancel_backend,
    )

    cleanup_runtime.assert_awaited_once_with(
        internal_user_id=123,
        registry_task_id="registry-task-1",
        release_lock=True,
    )


@pytest.mark.asyncio
async def test_system_status_proxy_uses_active_task_registry_counts(monkeypatch):
    expected = {
        "queue_size": 3,
        "queue_by_type": {"i2i_pro": 1, "ltx_video": 2},
        "middleware_queue_size": 71,
        "middleware_queue_by_type": {"i2i_pro": 23, "ltx_video": 33},
        "concurrency_locks": 3,
    }
    service_mock = AsyncMock(return_value=expected)
    monkeypatch.setattr(
        "dashboard.backend.routers.system.get_system_status_proxy_payload",
        service_mock,
    )

    data = await get_system_status_proxy()

    assert data == expected
    service_mock.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_refund_bot_task_uses_finalize_terminated_task(monkeypatch):
    expected = {
        "status": "success",
        "message": "Task registry-task-1 terminated and 7 credits refunded.",
    }
    service_mock = AsyncMock(return_value=expected)
    monkeypatch.setattr(
        "dashboard.backend.routers.system.refund_bot_task_payload",
        service_mock,
    )

    result = await refund_bot_task(RefundTaskRequest(task_id="registry-task-1"))

    assert result == expected
    service_mock.assert_awaited_once_with(task_id="registry-task-1")


@pytest.mark.asyncio
async def test_clean_zombie_tasks_uses_finalize_terminated_task(monkeypatch):
    expected = {
        "status": "success",
        "message": "Cleaned up 1 zombie tasks.",
        "removed": 1,
    }
    service_mock = AsyncMock(return_value=expected)
    monkeypatch.setattr(
        "dashboard.backend.routers.system.clean_zombie_tasks_payload",
        service_mock,
    )

    result = await clean_zombie_tasks()

    assert result == expected
    service_mock.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_sync_user_concurrency_routes_to_service(monkeypatch):
    expected = {"status": "success", "user_id": 123, "active_tasks": 1}
    service_mock = AsyncMock(return_value=expected)
    monkeypatch.setattr(
        "dashboard.backend.routers.system.sync_user_concurrency_payload",
        service_mock,
    )

    result = await sync_user_concurrency(SyncLockRequest(user_id=123))

    assert result == expected
    service_mock.assert_awaited_once_with(user_id=123)
