from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from starlette.requests import Request

from dashboard.backend.routers import system as system_router
from dashboard.backend.services import system_service
from src.core.task_core import TaskTerminationFinalizationResult


class _FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class _FakeAsyncClient:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self._status_code = status_code

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get(self, _url, timeout=5.0):
        _ = timeout
        return _FakeResponse(self._payload, self._status_code)


class _FakeDbSession:
    def __init__(self, rows):
        self._rows = rows

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def execute(self, _stmt):
        return SimpleNamespace(all=lambda: self._rows)


@pytest.fixture(autouse=True)
def _clear_backend_task_status_cache():
    system_service.clear_backend_task_status_cache()
    yield
    system_service.clear_backend_task_status_cache()


@pytest.mark.asyncio
async def test_refund_bot_task_payload_uses_finalize_terminated_task():
    finalize_terminated_task = AsyncMock(
        return_value=TaskTerminationFinalizationResult(
            terminated=True,
            refunded=True,
        )
    )

    result = await system_service.refund_bot_task_payload(
        task_id="registry-task-1",
        get_system_task_stats_func=AsyncMock(
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
        finalize_terminated_task_func=finalize_terminated_task,
    )

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
async def test_clean_zombie_tasks_payload_uses_finalize_terminated_task():
    finalize_terminated_task = AsyncMock(
        return_value=TaskTerminationFinalizationResult(
            terminated=True,
            refunded=True,
        )
    )

    result = await system_service.clean_zombie_tasks_payload(
        get_system_task_stats_func=AsyncMock(
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
        finalize_terminated_task_func=finalize_terminated_task,
        now_func=lambda: 8000,
    )

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


def test_count_tasks_by_type_uses_worker_execution_task_types():
    tasks = {
        "task-1": {"task_type": "edit"},
        "task-2": {"task_type": "img2img_lora"},
        "task-3": {"task_type": "custom_video"},
        "task-4": {"task_type": "video_lora"},
        "task-5": {"task_type": "image_to_video"},
        "task-6": {"task_type": "ltx_video"},
        "task-7": {"task_type": "txt2img"},
        "task-8": {"task_type": "doggy_style"},
        "task-9": {"task_type": "face_video_step1"},
        "task-10": {"task_type": None},
    }

    assert system_service.count_tasks_by_type(tasks) == {
        "img2img": 1,
        "img2img_lora": 1,
        "image_to_video": 4,
        "ltx_video": 1,
        "t2i-pornmaster-turbo": 1,
        "face_video": 1,
        "unknown": 1,
    }


@pytest.mark.asyncio
async def test_get_system_status_proxy_payload_uses_active_task_registry_counts():
    middleware_payload = {
        "queue_size": 71,
        "queue_by_type": {"i2i_pro": 23, "ltx_video": 33},
        "active_workers": 9,
        "healthy_workers": 7,
        "error_workers": 1,
        "quarantined_workers": 1,
        "workers_by_status": {"running": 3, "idle": 4, "error": 1, "quarantined": 1},
        "comfy_online": True,
    }
    active_tasks = {
        "registry-task-1": {"task_type": "i2i_pro"},
        "registry-task-2": {"task_type": "ltx_video"},
        "registry-task-3": {"task_type": "ltx_video"},
    }

    data = await system_service.get_system_status_proxy_payload(
        httpx_async_client_factory=lambda **_kwargs: _FakeAsyncClient(middleware_payload),
        get_system_task_stats_func=AsyncMock(
            return_value=(active_tasks, {1001: 1, 1002: 2})
        ),
    )

    assert data["queue_size"] == 3
    assert data["queue_by_type"] == {"i2i_pro": 1, "ltx_video": 2}
    assert data["middleware_queue_size"] == 71
    assert data["middleware_queue_by_type"] == {"i2i_pro": 23, "ltx_video": 33}
    assert data["concurrency_locks"] == 3
    assert data["healthy_workers"] == 7
    assert data["error_workers"] == 1
    assert data["quarantined_workers"] == 1
    assert data["workers_by_status"] == {
        "running": 3,
        "idle": 4,
        "error": 1,
        "quarantined": 1,
    }


@pytest.mark.asyncio
async def test_sync_user_concurrency_payload_repairs_excess_lock():
    sync_func = AsyncMock()

    result = await system_service.sync_user_concurrency_payload(
        user_id=123,
        get_system_task_stats_func=AsyncMock(
            return_value=(
                {
                    "task-1": {"user_id": 123},
                    "task-2": {"user_id": 999},
                },
                {123: 2},
            )
        ),
        sync_user_concurrency_func=sync_func,
    )

    assert result["status"] == "success"
    sync_func.assert_awaited_once_with(123, 1)


@pytest.mark.asyncio
async def test_get_active_bot_tasks_payload_merges_user_and_backend_status():
    tasks = {
        "task-1": {
            "user_id": 123,
            "backend_task_id": "backend-1",
            "task_type": "i2i_pro",
        },
        "task-2": {
            "user_id": 456,
            "task_type": "ltx_video",
        },
    }

    result = await system_service.get_active_bot_tasks_payload(
        get_system_task_stats_func=AsyncMock(return_value=(tasks, {})),
        session_factory=lambda: _FakeDbSession(
            [
                SimpleNamespace(
                    id=123,
                    user_group="金丹期",
                    current_identity="核心弟子",
                    full_name="炼丹道人",
                    username="tester_handle",
                )
            ]
        ),
        request_backend_status_func=AsyncMock(
            return_value=_FakeResponse({"status": "pending", "queue_pos": 4})
        ),
    )

    assert result["status"] == "success"
    assert result["count"] == 2
    assert result["tasks"]["task-1"]["user_group"] == "金丹期"
    assert result["tasks"]["task-1"]["user_identity"] == "核心弟子"
    assert result["tasks"]["task-1"]["display_name"] == "炼丹道人"
    assert result["tasks"]["task-1"]["execution_status"] == "pending"
    assert result["tasks"]["task-1"]["queue_position"] == 4
    assert result["tasks"]["task-2"]["user_group"] == "未知"
    assert result["tasks"]["task-2"]["display_name"] == "User_456"
    assert result["tasks"]["task-2"]["execution_status"] == "submitting"


@pytest.mark.asyncio
async def test_fetch_backend_task_statuses_uses_short_cache(monkeypatch):
    request_backend_status_func = AsyncMock(
        return_value=_FakeResponse({"status": "pending", "queue_pos": 5})
    )
    monkeypatch.setattr(
        system_service,
        "BACKEND_TASK_STATUS_CACHE_TTL_SECONDS",
        5.0,
    )

    first = await system_service._fetch_backend_task_statuses(
        tasks={"task-1": {"backend_task_id": "backend-1"}},
        api_base="http://127.0.0.1:8003",
        request_backend_status_func=request_backend_status_func,
    )
    second = await system_service._fetch_backend_task_statuses(
        tasks={"task-1": {"backend_task_id": "backend-1"}},
        api_base="http://127.0.0.1:8003",
        request_backend_status_func=request_backend_status_func,
    )

    assert first == {"backend-1": {"status": "pending", "queue_pos": 5}}
    assert second == {"backend-1": {"status": "pending", "queue_pos": 5}}
    request_backend_status_func.assert_awaited_once_with("backend-1")


@pytest.mark.asyncio
async def test_fetch_backend_task_statuses_prunes_old_cache(monkeypatch):
    request_backend_status_func = AsyncMock(
        side_effect=[
            _FakeResponse({"status": "pending"}),
            _FakeResponse({"status": "running"}),
            _FakeResponse({"status": "done"}),
        ]
    )
    monkeypatch.setattr(
        system_service,
        "BACKEND_TASK_STATUS_CACHE_TTL_SECONDS",
        30.0,
    )
    monkeypatch.setattr(
        system_service,
        "BACKEND_TASK_STATUS_CACHE_MAX_ENTRIES",
        1,
    )

    await system_service._fetch_backend_task_statuses(
        tasks={"task-1": {"backend_task_id": "backend-1"}},
        api_base="http://127.0.0.1:8003",
        request_backend_status_func=request_backend_status_func,
    )
    await system_service._fetch_backend_task_statuses(
        tasks={"task-2": {"backend_task_id": "backend-2"}},
        api_base="http://127.0.0.1:8003",
        request_backend_status_func=request_backend_status_func,
    )
    await system_service._fetch_backend_task_statuses(
        tasks={"task-1": {"backend_task_id": "backend-1"}},
        api_base="http://127.0.0.1:8003",
        request_backend_status_func=request_backend_status_func,
    )

    assert len(system_service._backend_task_status_cache) == 1
    assert [
        call.args[0] for call in request_backend_status_func.await_args_list
    ] == ["backend-1", "backend-2", "backend-1"]


@pytest.mark.asyncio
async def test_dashboard_health_check_returns_503_when_database_init_failed():
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/health",
        "headers": [],
        "app": SimpleNamespace(
            state=SimpleNamespace(
                dashboard_health={
                    "database_ready": False,
                    "startup_complete": True,
                    "database_error": "db unavailable",
                }
            )
        ),
    }

    response = await system_router.health_check(Request(scope))

    assert response.status_code == 503
    assert b'"status":"degraded"' in response.body
    assert b'"database_error":"db unavailable"' in response.body


@pytest.mark.asyncio
async def test_dashboard_health_check_returns_ok_when_startup_completed():
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/health",
        "headers": [],
        "app": SimpleNamespace(
            state=SimpleNamespace(
                dashboard_health={
                    "database_ready": True,
                    "startup_complete": True,
                    "database_error": None,
                }
            )
        ),
    }

    response = await system_router.health_check(Request(scope))

    assert response.status_code == 200
    assert b'"status":"ok"' in response.body
