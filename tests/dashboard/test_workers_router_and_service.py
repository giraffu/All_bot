from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from dashboard.backend.presenters import worker_admin_presenter
from dashboard.backend.routers import workers as workers_router
from dashboard.backend.services import worker_admin_service


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar(self):
        return self.value


class _WorkerRowsResult:
    def __init__(self, logs):
        self.logs = list(logs)

    def scalars(self):
        return type("_Scalars", (), {"all": lambda _self: list(self.logs)})()


class _WorkerListRowsResult:
    def __init__(self, rows):
        self.rows = list(rows)

    def all(self):
        return list(self.rows)


class _FakeWorkersDb:
    def __init__(self, execute_results):
        self.execute_results = list(execute_results)
        self.executed_stmts = []

    async def execute(self, stmt):
        self.executed_stmts.append(str(stmt))
        if not self.execute_results:
            raise AssertionError("unexpected execute call")
        return self.execute_results.pop(0)


def _build_log(**overrides):
    base = {
        "id": 1,
        "worker_id": "worker-1",
        "task_id": "task-1",
        "task_type": "img2img",
        "status": "SUCCESS",
        "start_time": datetime(2026, 1, 1, 12, 0, 0),
        "end_time": datetime(2026, 1, 1, 12, 5, 0),
        "duration": 300.0,
        "error_message": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_build_worker_history_item_serializes_datetime_fields():
    result = worker_admin_presenter.build_worker_history_item(_build_log())

    assert result.start_time == "2026-01-01T12:00:00"
    assert result.end_time == "2026-01-01T12:05:00"
    assert result.worker_id == "worker-1"


@pytest.mark.asyncio
async def test_get_worker_history_payload_builds_paginated_response():
    db = _FakeWorkersDb([
        _ScalarResult(1),
        _WorkerRowsResult([_build_log()]),
    ])

    result = await worker_admin_service.get_worker_history_payload(
        worker_id="worker-1",
        page=2,
        size=10,
        db=db,
    )

    assert result.total == 1
    assert result.page == 2
    assert result.size == 10
    assert result.data[0].start_time == "2026-01-01T12:00:00"
    assert "worker_logs.worker_id = :worker_id_1" in db.executed_stmts[1]
    assert (
        "ORDER BY worker_logs.end_time DESC, worker_logs.start_time DESC"
        in db.executed_stmts[1]
    )


@pytest.mark.asyncio
async def test_get_worker_list_payload_returns_distinct_workers():
    db = _FakeWorkersDb([_WorkerListRowsResult([("worker-1",), ("worker-2",)])])

    result = await worker_admin_service.get_worker_list_payload(db=db)

    assert result == {"workers": ["worker-1", "worker-2"]}


@pytest.mark.asyncio
async def test_get_worker_history_router_routes_to_service(monkeypatch):
    expected = {"total": 0, "page": 1, "size": 20, "data": []}
    service_mock = AsyncMock(return_value=expected)
    monkeypatch.setattr(workers_router, "get_worker_history_payload", service_mock)
    db = object()

    result = await workers_router.get_worker_history(
        worker_id="worker-1",
        page=1,
        size=20,
        db=db,
    )

    assert result == expected
    service_mock.assert_awaited_once_with(
        worker_id="worker-1",
        page=1,
        size=20,
        db=db,
    )
