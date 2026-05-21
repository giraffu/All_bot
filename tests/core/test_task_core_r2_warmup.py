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

    submission_context = task_core.TaskSubmissionContext(
        task_type="image",
        is_video_task=False,
        user_logger=fake_user_logger,
        prompt="hello",
        saved_inputs=[],
        metadata={},
        allow_contribute=True,
        final_priority=0,
        video_request=task_core.VideoTaskRequest(
            requested_duration=10,
            output_width=1024,
            output_height=1024,
        ),
    )

    await task_core.monitor_task_and_release_lock(
        backend_task_id="task-1",
        internal_user_id=123,
        username="tester",
        registry_task_id="registry-1",
        submission_context=submission_context,
        cost=1,
    )

    fake_user_logger.log_task.assert_awaited_once()
    assert fake_user_logger.log_task.await_args.kwargs["requested_duration"] == 10
    warmup_mock.assert_called_once_with(
        user_id=123,
        task_id="registry-1",
        output_file="123/output_images/task-1.png",
        media_type="image",
        source="web",
    )


@pytest.mark.asyncio
async def test_monitor_task_and_release_lock_uses_cancellation_finalize_for_cancelled(
    monkeypatch,
):
    async def _monitor_progress(_task_id, _is_video):
        yield {"status": "cancelled"}

    finalize_cancel = AsyncMock()
    finalize_failure = AsyncMock()

    monkeypatch.setattr(task_core.image_service, "monitor_progress", _monitor_progress)
    monkeypatch.setattr(task_core, "finalize_task_cancellation", finalize_cancel)
    monkeypatch.setattr(task_core, "finalize_task_failure", finalize_failure)

    submission_context = task_core.TaskSubmissionContext(
        task_type="image",
        is_video_task=False,
        user_logger=MagicMock(),
        prompt="cancel me",
        saved_inputs=[],
        metadata={},
        allow_contribute=True,
        final_priority=0,
    )

    await task_core.monitor_task_and_release_lock(
        backend_task_id="task-cancelled",
        internal_user_id=123,
        username="tester",
        registry_task_id="registry-cancelled",
        submission_context=submission_context,
        cost=5,
    )

    finalize_cancel.assert_awaited_once_with(
        internal_user_id=123,
        username="tester",
        cost=5,
        task_submitted=True,
        registry_task_id="registry-cancelled",
    )
    finalize_failure.assert_not_awaited()


@pytest.mark.asyncio
async def test_monitor_task_and_release_lock_uses_failure_finalize_for_error(
    monkeypatch,
):
    async def _monitor_progress(_task_id, _is_video):
        yield {"status": "error"}

    finalize_cancel = AsyncMock()
    finalize_failure = AsyncMock()

    monkeypatch.setattr(task_core.image_service, "monitor_progress", _monitor_progress)
    monkeypatch.setattr(task_core, "finalize_task_cancellation", finalize_cancel)
    monkeypatch.setattr(task_core, "finalize_task_failure", finalize_failure)

    submission_context = task_core.TaskSubmissionContext(
        task_type="image",
        is_video_task=False,
        user_logger=MagicMock(),
        prompt="fail me",
        saved_inputs=[],
        metadata={},
        allow_contribute=True,
        final_priority=0,
    )

    await task_core.monitor_task_and_release_lock(
        backend_task_id="task-error",
        internal_user_id=321,
        username="tester",
        registry_task_id="registry-error",
        submission_context=submission_context,
        cost=7,
    )

    finalize_cancel.assert_not_awaited()
    finalize_failure.assert_awaited_once_with(
        internal_user_id=321,
        username="tester",
        cost=7,
        should_refund=True,
        registry_task_id="registry-error",
        refund_task_type="refund_async_failed_error",
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


@pytest.mark.asyncio
async def test_process_and_submit_task_passes_requested_duration_to_web_monitor(monkeypatch):
    monitor_mock = AsyncMock()

    def _capture_background_task(coro):
        coro.close()
        return None

    monkeypatch.setattr(
        task_core, "check_concurrency_lock", AsyncMock(return_value=(True, ""))
    )
    monkeypatch.setattr(
        task_core, "check_and_deduct_credits", AsyncMock(return_value=(True, ""))
    )
    monkeypatch.setattr(
        task_core,
        "get_user_priority_and_identity",
        AsyncMock(return_value=(0, "user", "外门弟子")),
    )
    monkeypatch.setattr(task_core, "load_prompts", lambda: {})
    monkeypatch.setattr(task_core.TaskRegistry, "add_task", AsyncMock(return_value="reg-1"))
    monkeypatch.setattr(
        task_core.TaskRegistry, "update_backend_task_id", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        task_core, "dispatch_to_worker", AsyncMock(return_value="backend-task-1")
    )
    monkeypatch.setattr(task_core, "monitor_task_and_release_lock", monitor_mock)
    monkeypatch.setattr(task_core.asyncio, "create_task", _capture_background_task)

    result = await task_core.process_and_submit_task(
        user_id=123,
        username="tester",
        task_type="ltx_video",
        inputs={
            "prompt": "wide cinematic dolly shot",
            "images": [],
            "resolution": "1280x704",
            "duration": "20s",
        },
        task_id="task-1",
        client_type="web",
    )

    assert result["task_id"] == "reg-1"
    monitor_mock.assert_called_once()
    submission_context = monitor_mock.call_args.kwargs["submission_context"]
    assert submission_context.requested_duration == 20
    assert submission_context.output_duration == 20


@pytest.mark.asyncio
async def test_persist_successful_task_result_reuses_core_path_for_bot(monkeypatch):
    fake_user_logger = MagicMock()
    fake_user_logger.save_output_image.return_value = "456/output_images/task-2.png"
    fake_user_logger.log_task = AsyncMock()
    refresh_mock = AsyncMock()
    warmup_mock = MagicMock()

    monkeypatch.setattr(
        task_core.image_service,
        "download_result",
        AsyncMock(return_value=b"image-bytes"),
    )
    monkeypatch.setattr(
        task_core,
        "extract_media_metadata_from_bytes_best_effort",
        lambda *_args, **_kwargs: (768, 1024, None),
    )
    monkeypatch.setattr(task_core, "UserLogger", lambda *_args, **_kwargs: fake_user_logger)
    monkeypatch.setattr(task_core, "schedule_web_history_r2_warmup", warmup_mock)
    monkeypatch.setattr(
        "src.services.permission_service.permission_service.refresh_user_group",
        refresh_mock,
    )

    result = await task_core.persist_successful_task_result(
        backend_task_id="task-2",
        registry_task_id="task-2",
        internal_user_id=456,
        username="tester",
        prompt="hello",
        task_type="image",
        input_images=["input.png"],
        allow_contribute=True,
        is_video=False,
        billing_resolution="1024",
        requested_duration=None,
        source="bot",
        refresh_user_group_after_log=True,
    )

    assert result.media_bytes == b"image-bytes"
    assert result.output_file == "456/output_images/task-2.png"
    assert result.width == 768
    assert result.height == 1024
    assert result.duration is None
    fake_user_logger.log_task.assert_awaited_once()
    refresh_mock.assert_awaited_once_with(456)
    warmup_mock.assert_not_called()
