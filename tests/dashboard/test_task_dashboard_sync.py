from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from dashboard.backend.routers.system import (
    RefundTaskRequest,
    clean_zombie_tasks,
    get_system_status_proxy,
    refund_bot_task,
)
from src.core.task_core import (
    TaskTerminationFinalizationResult,
    force_terminate_task,
)


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

    monkeypatch.setattr("src.services.redis_client.redis_client", redis_client)
    monkeypatch.setattr("src.api_client.api_client", api_client)
    monkeypatch.setattr("src.core.task_core.cleanup_task_runtime_state", cleanup_runtime)

    await force_terminate_task("registry-task-1")

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

    monkeypatch.setattr("src.services.redis_client.redis_client", redis_client)
    monkeypatch.setattr("src.api_client.api_client", api_client)
    monkeypatch.setattr("src.core.task_core.cleanup_task_runtime_state", cleanup_runtime)

    await force_terminate_task("registry-task-1")

    cleanup_runtime.assert_awaited_once_with(
        internal_user_id=123,
        registry_task_id="registry-task-1",
        release_lock=True,
    )


class _FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class _FakeAsyncClient:
    def __init__(self, payload: dict):
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get(self, url, timeout=5.0):
        return _FakeResponse(self._payload, 200)


@pytest.mark.asyncio
async def test_system_status_proxy_uses_active_task_registry_counts(monkeypatch):
    middleware_payload = {
        "queue_size": 71,
        "queue_by_type": {"i2i_pro": 23, "ltx_video": 33},
        "active_workers": 9,
        "comfy_online": True,
    }
    active_tasks = {
        "registry-task-1": {"task_type": "i2i_pro"},
        "registry-task-2": {"task_type": "ltx_video"},
        "registry-task-3": {"task_type": "ltx_video"},
    }

    monkeypatch.setattr(
        "dashboard.backend.routers.system.httpx.AsyncClient",
        lambda trust_env=False: _FakeAsyncClient(middleware_payload),
    )
    monkeypatch.setattr(
        "dashboard.backend.routers.system.get_system_task_stats",
        AsyncMock(return_value=(active_tasks, {1001: 1, 1002: 2})),
    )

    data = await get_system_status_proxy()

    assert data["queue_size"] == 3
    assert data["queue_by_type"] == {"i2i_pro": 1, "ltx_video": 2}
    assert data["middleware_queue_size"] == 71
    assert data["middleware_queue_by_type"] == {"i2i_pro": 23, "ltx_video": 33}
    assert data["concurrency_locks"] == 3


@pytest.mark.asyncio
async def test_refund_bot_task_uses_finalize_terminated_task(monkeypatch):
    finalize_terminated_task = AsyncMock(
        return_value=TaskTerminationFinalizationResult(
            terminated=True,
            refunded=True,
        )
    )
    monkeypatch.setattr(
        "dashboard.backend.routers.system.get_system_task_stats",
        AsyncMock(
            return_value=(
                {
                    "registry-task-1": {
                        "user_id": 123,
                        "username": "tester",
                        "cost": 7,
                    }
                },
                {},
            )
        ),
    )
    monkeypatch.setattr(
        "dashboard.backend.routers.system.finalize_terminated_task",
        finalize_terminated_task,
    )

    result = await refund_bot_task(RefundTaskRequest(task_id="registry-task-1"))

    assert result == {
        "status": "success",
        "message": "Task registry-task-1 terminated and 7 credits refunded.",
    }
    finalize_terminated_task.assert_awaited_once_with(
        registry_task_id="registry-task-1",
        user_id=123,
        username="tester",
        cost=7,
        should_refund=True,
        refund_task_type="refund_admin_force",
    )


@pytest.mark.asyncio
async def test_clean_zombie_tasks_uses_finalize_terminated_task(monkeypatch):
    finalize_terminated_task = AsyncMock(
        return_value=TaskTerminationFinalizationResult(
            terminated=True,
            refunded=True,
        )
    )
    monkeypatch.setattr(
        "dashboard.backend.routers.system.time.time",
        lambda: 8000,
    )
    monkeypatch.setattr(
        "dashboard.backend.routers.system.get_system_task_stats",
        AsyncMock(
            return_value=(
                {
                    "registry-task-1": {
                        "user_id": 123,
                        "username": "tester",
                        "cost": 7,
                        "created_at": 0,
                    },
                    "registry-task-2": {
                        "user_id": 456,
                        "username": "tester2",
                        "cost": 0,
                        "created_at": 7900,
                    },
                },
                {},
            )
        ),
    )
    monkeypatch.setattr(
        "dashboard.backend.routers.system.finalize_terminated_task",
        finalize_terminated_task,
    )

    result = await clean_zombie_tasks()

    assert result == {
        "status": "success",
        "message": "Cleaned up 1 zombie tasks.",
        "removed": 1,
    }
    finalize_terminated_task.assert_awaited_once_with(
        registry_task_id="registry-task-1",
        user_id=123,
        username="tester",
        cost=7,
        should_refund=True,
        refund_task_type="refund_admin_force_cleanup",
    )
