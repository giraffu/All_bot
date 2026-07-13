from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.handlers.callbacks import task_callbacks


@pytest.mark.asyncio
async def test_cancel_task_callback_shows_non_blocking_message_when_pending_cancel_succeeds(
    monkeypatch,
):
    query = SimpleNamespace(
        data="cancel_task_task-1",
        answer=AsyncMock(),
    )
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=12345, username="tester"),
    )

    monkeypatch.setattr(
        task_callbacks,
        "get_or_create_user_by_telegram",
        AsyncMock(return_value=(SimpleNamespace(id=99), False)),
    )
    monkeypatch.setattr(
        task_callbacks,
        "cancel_user_task",
        AsyncMock(
            return_value={
                "state": "cancelled",
                "message": "任务已从排队队列移除",
            }
        ),
    )

    await task_callbacks.cancel_task_callback(update, context=SimpleNamespace())

    query.answer.assert_awaited_once_with(
        text="任务已从排队队列移除", show_alert=False
    )


@pytest.mark.asyncio
async def test_cancel_task_callback_shows_alert_when_task_already_running(monkeypatch):
    query = SimpleNamespace(
        data="cancel_task_task-2",
        answer=AsyncMock(),
    )
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=12345, username="tester"),
    )

    monkeypatch.setattr(
        task_callbacks,
        "get_or_create_user_by_telegram",
        AsyncMock(return_value=(SimpleNamespace(id=99), False)),
    )
    monkeypatch.setattr(
        task_callbacks,
        "cancel_user_task",
        AsyncMock(
            return_value={
                "state": "not_cancellable",
                "message": "任务已进入生成，撤销失败",
            }
        ),
    )

    await task_callbacks.cancel_task_callback(update, context=SimpleNamespace())

    query.answer.assert_awaited_once_with(
        text="任务已进入生成，撤销失败", show_alert=True
    )
