import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core import task_core


@pytest.mark.asyncio
async def test_monitor_task_and_release_lock_schedules_web_history_r2_warmup(monkeypatch):
    async def _monitor_progress(_task_id, _is_video):
        yield {"status": "done", "result_path": "bot-data/worker/task-1.png"}

    fake_user_logger = MagicMock()
    fake_user_logger.save_output_image.return_value = "123/output_images/task-1.png"
    fake_user_logger.log_task = AsyncMock()

    warmup_mock = MagicMock()

    monkeypatch.setattr(task_core.image_service, "monitor_progress", _monitor_progress)
    monkeypatch.setattr(
        task_core.image_service,
        "download_result",
        AsyncMock(return_value=b"fake-image-bytes"),
    )
    monkeypatch.setattr(
        task_core,
        "extract_media_metadata_from_bytes_best_effort",
        lambda *_args, **_kwargs: (1024, 1024, None),
    )
    monkeypatch.setattr(task_core, "UserLogger", lambda *_args, **_kwargs: fake_user_logger)
    monkeypatch.setattr(task_core, "schedule_web_history_r2_warmup", warmup_mock)
    monkeypatch.setattr(task_core, "release_concurrency_lock", AsyncMock())
    monkeypatch.setattr(task_core.TaskRegistry, "remove_task", AsyncMock())
    monkeypatch.setattr(task_core, "refund_credits", AsyncMock())

    await task_core.monitor_task_and_release_lock(
        task_id="task-1",
        internal_user_id=123,
        username="tester",
        registry_task_id="registry-1",
        is_video=False,
        task_type="image",
        prompt="hello",
        input_images=[],
        allow_contribute=True,
        cost=1,
        billing_resolution=None,
        output_width=1024,
        output_height=1024,
        output_duration=None,
    )

    fake_user_logger.log_task.assert_awaited_once()
    warmup_mock.assert_called_once_with(
        user_id=123,
        task_id="task-1",
        output_file="123/output_images/task-1.png",
        media_type="image",
        source="web",
    )


@pytest.mark.asyncio
async def test_schedule_web_history_r2_warmup_still_prunes_when_copy_fails(monkeypatch):
    original_create_task = asyncio.create_task
    scheduled_tasks = []

    def _capture_create_task(coro):
        task = original_create_task(coro)
        scheduled_tasks.append(task)
        return task

    copy_mock = AsyncMock(side_effect=RuntimeError("copy failed"))
    thumb_mock = AsyncMock(return_value=None)
    prune_mock = AsyncMock(return_value=None)
    warning_mock = MagicMock()

    monkeypatch.setattr(task_core.asyncio, "create_task", _capture_create_task)
    monkeypatch.setattr(
        task_core,
        "resolve_storage_object",
        lambda _output_file: ("bot-data", "123/output_images/task-1.png"),
    )
    monkeypatch.setattr(task_core.storage, "async_copy_to_r2", copy_mock)
    monkeypatch.setattr(task_core, "generate_and_upload_thumbnail", thumb_mock)
    monkeypatch.setattr(
        task_core.storage,
        "async_prune_user_web_history_r2_cache",
        prune_mock,
    )
    monkeypatch.setattr(task_core.logger, "warning", warning_mock)

    task_core.schedule_web_history_r2_warmup(
        user_id=123,
        task_id="task-1",
        output_file="123/output_images/task-1.png",
        media_type="image",
        source="web",
    )

    assert len(scheduled_tasks) == 1
    await scheduled_tasks[0]

    copy_mock.assert_awaited_once_with(
        "bot-data",
        "123/output_images/task-1.png",
        "history/task-1/original.png",
    )
    thumb_mock.assert_awaited_once_with(
        "123/output_images/task-1.png",
        "image",
        "history/task-1/thumb.webp",
    )
    prune_mock.assert_awaited_once_with(123)
    warning_mock.assert_called_once()
