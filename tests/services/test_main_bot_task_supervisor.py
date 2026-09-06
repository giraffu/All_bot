import asyncio
from types import SimpleNamespace

import pytest

from src.services.main_bot_task_supervisor import (
    spawn_main_bot_task,
    stop_main_bot_tasks,
)


@pytest.mark.asyncio
async def test_main_bot_task_supervisor_cancels_and_awaits_owned_tasks():
    started = asyncio.Event()
    cancelled = asyncio.Event()
    application = SimpleNamespace(bot_data={})

    async def worker():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    task = spawn_main_bot_task(application, worker(), name="test-worker")
    await started.wait()

    await stop_main_bot_tasks(application)

    assert task.done()
    assert task.cancelled()
    assert cancelled.is_set()
    assert application.bot_data["bg_tasks"] == set()


@pytest.mark.asyncio
async def test_completed_main_bot_task_is_removed_from_registry():
    application = SimpleNamespace(bot_data={})

    task = spawn_main_bot_task(application, asyncio.sleep(0), name="short-task")
    await task
    await asyncio.sleep(0)

    assert application.bot_data["bg_tasks"] == set()


@pytest.mark.asyncio
async def test_failed_main_bot_task_is_logged_and_removed(caplog):
    application = SimpleNamespace(bot_data={})

    async def worker():
        raise RuntimeError("worker failed")

    with caplog.at_level("ERROR"):
        task = spawn_main_bot_task(application, worker(), name="failed-worker")
        await asyncio.gather(task, return_exceptions=True)
        await asyncio.sleep(0)

    assert application.bot_data["bg_tasks"] == set()
    assert "main-bot:failed-worker" in caplog.text
    assert "RuntimeError" in caplog.text
