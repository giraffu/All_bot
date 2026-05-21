from unittest.mock import AsyncMock

import pytest

from scripts import clear_stuck_tasks
from src.core.task_core import TaskTerminationFinalizationResult


@pytest.mark.asyncio
async def test_clean_stuck_tasks_uses_core_finalize_and_syncs_lock(monkeypatch):
    finalize_terminated = AsyncMock(
        return_value=TaskTerminationFinalizationResult(
            terminated=True,
            refunded=True,
        )
    )
    sync_lock = AsyncMock()
    close_redis = AsyncMock()

    active_tasks = {
        "registry-task-1": {
            "user_id": 123,
            "username": "tester",
            "cost": 5,
            "created_at": 0,
        },
        "registry-task-2": {
            "user_id": 456,
            "username": "fresh",
            "cost": 2,
            "created_at": 7900,
        },
    }

    monkeypatch.setattr(clear_stuck_tasks.time, "time", lambda: 8000)
    monkeypatch.setattr(
        clear_stuck_tasks,
        "get_system_task_stats",
        AsyncMock(
            side_effect=[
                (active_tasks, {}),
                (
                    {
                        "registry-task-2": active_tasks["registry-task-2"],
                    },
                    {},
                ),
            ]
        ),
    )
    monkeypatch.setattr(
        clear_stuck_tasks,
        "finalize_terminated_task",
        finalize_terminated,
    )
    monkeypatch.setattr(clear_stuck_tasks, "sync_user_concurrency", sync_lock)
    monkeypatch.setattr(clear_stuck_tasks.redis_client, "close", close_redis)

    await clear_stuck_tasks.clean_stuck_tasks_and_reset_locks()

    finalize_terminated.assert_awaited_once_with(
        registry_task_id="registry-task-1",
        user_id=123,
        username="tester",
        cost=5,
        should_refund=True,
        refund_task_type="refund_admin_force_script",
    )
    sync_lock.assert_awaited_once_with(123, 0)
    close_redis.assert_awaited_once()


@pytest.mark.asyncio
async def test_clean_stuck_tasks_no_active_tasks_is_noop(monkeypatch):
    finalize_terminated = AsyncMock()
    sync_lock = AsyncMock()
    close_redis = AsyncMock()

    monkeypatch.setattr(
        clear_stuck_tasks,
        "get_system_task_stats",
        AsyncMock(return_value=({}, {})),
    )
    monkeypatch.setattr(
        clear_stuck_tasks,
        "finalize_terminated_task",
        finalize_terminated,
    )
    monkeypatch.setattr(clear_stuck_tasks, "sync_user_concurrency", sync_lock)
    monkeypatch.setattr(clear_stuck_tasks.redis_client, "close", close_redis)

    await clear_stuck_tasks.clean_stuck_tasks_and_reset_locks()

    finalize_terminated.assert_not_awaited()
    sync_lock.assert_not_awaited()
    close_redis.assert_awaited_once()
