import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core import task_core
from src.core.task_core_dependencies import (
    TaskCorePersistenceDependencies,
    TaskCoreProcessDependencies,
)
from src.core import task_core_persistence
from src.core import task_core_web_history_warmup
from src.core.task_core_persistence_postprocess import (
    postprocess_successful_task_persistence,
)
from src.core.task_core_types import (
    TaskPersistencePostprocessPlan,
    TaskSuccessPersistenceResult,
)
from src.services import storage as storage_module
from src.services import task_web_lifecycle_monitor
from src.services import task_web_side_effects
from src.services import task_web_terminal_finalization


@pytest.mark.asyncio
async def test_monitor_task_and_release_lock_schedules_web_history_r2_warmup():
    async def _monitor_progress(_task_id, _is_video):
        yield {"status": "done", "result_path": "bot-data/worker/task-1.png"}

    fake_user_logger = MagicMock()
    fake_user_logger.save_output_image.return_value = "123/output_images/task-1.png"
    fake_user_logger.log_task = AsyncMock()
    download_result = AsyncMock(return_value=b"fake-image-bytes")
    cleanup_runtime = AsyncMock()
    warmup_mock = MagicMock()
    persistence_dependencies = TaskCorePersistenceDependencies(
        user_logger_factory=lambda *_args, **_kwargs: fake_user_logger,
        download_result_func=download_result,
        download_video_result_func=AsyncMock(),
        extract_media_metadata_from_bytes_best_effort_func=(
            lambda *_args, **_kwargs: (1024, 1024, None)
        ),
        extract_media_metadata_from_storage_best_effort_func=AsyncMock(),
        schedule_web_history_r2_warmup_func=warmup_mock,
        refresh_user_group_func=None,
    )

    async def _persist_successful_web_history(**kwargs):
        await task_core_persistence.persist_successful_task_result(
            backend_task_id=kwargs["backend_task_id"],
            registry_task_id=kwargs["registry_task_id"],
            internal_user_id=kwargs["internal_user_id"],
            username=kwargs["username"],
            prompt=kwargs["prompt"],
            task_type=kwargs["task_type"],
            input_images=kwargs["input_images"],
            allow_contribute=kwargs["allow_contribute"],
            is_video=kwargs["is_video"],
            result_path=kwargs["result_path"],
            billing_resolution=kwargs["billing_resolution"],
            output_width=kwargs["output_width"],
            output_height=kwargs["output_height"],
            output_duration=kwargs["output_duration"],
            requested_duration=kwargs["requested_duration"],
            postprocess_plan=TaskPersistencePostprocessPlan(
                source="web",
                warmup_web_history=True,
            ),
            dependencies=persistence_dependencies,
        )

    async def _finalize_success(**kwargs):
        await task_web_terminal_finalization.finalize_monitored_web_task_success(
            **kwargs,
            persist_successful_web_history_func=_persist_successful_web_history,
            cleanup_task_runtime_state_func=cleanup_runtime,
            logger=task_core.logger,
        )

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

    await task_web_lifecycle_monitor.monitor_task_and_release_lock(
        backend_task_id="task-1",
        internal_user_id=123,
        username="tester",
        registry_task_id="registry-1",
        submission_context=submission_context,
        cost=1,
        monitor_progress_func=_monitor_progress,
        normalize_terminal_status_func=task_core.normalize_terminal_status,
        finalize_success_func=_finalize_success,
        finalize_cancellation_func=AsyncMock(),
        finalize_failure_func=AsyncMock(),
        logger=task_core.logger,
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
async def test_monitor_task_and_release_lock_uses_cancellation_finalize_for_cancelled():
    async def _monitor_progress(_task_id, _is_video):
        yield {"status": "cancelled"}

    finalize_cancel = AsyncMock()
    finalize_failure = AsyncMock()

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

    await task_web_lifecycle_monitor.monitor_task_and_release_lock(
        backend_task_id="task-cancelled",
        internal_user_id=123,
        username="tester",
        registry_task_id="registry-cancelled",
        submission_context=submission_context,
        cost=5,
        monitor_progress_func=_monitor_progress,
        normalize_terminal_status_func=task_core.normalize_terminal_status,
        finalize_success_func=AsyncMock(),
        finalize_cancellation_func=finalize_cancel,
        finalize_failure_func=finalize_failure,
        logger=MagicMock(),
    )

    finalize_cancel.assert_awaited_once_with(
        internal_user_id=123,
        username="tester",
        cost=5,
        registry_task_id="registry-cancelled",
    )
    finalize_failure.assert_not_awaited()


@pytest.mark.asyncio
async def test_monitor_task_and_release_lock_uses_failure_finalize_for_error():
    async def _monitor_progress(_task_id, _is_video):
        yield {"status": "error"}

    finalize_cancel = AsyncMock()
    finalize_failure = AsyncMock()

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

    await task_web_lifecycle_monitor.monitor_task_and_release_lock(
        backend_task_id="task-error",
        internal_user_id=321,
        username="tester",
        registry_task_id="registry-error",
        submission_context=submission_context,
        cost=7,
        monitor_progress_func=_monitor_progress,
        normalize_terminal_status_func=task_core.normalize_terminal_status,
        finalize_success_func=AsyncMock(),
        finalize_cancellation_func=finalize_cancel,
        finalize_failure_func=finalize_failure,
        logger=MagicMock(),
    )

    finalize_cancel.assert_not_awaited()
    finalize_failure.assert_awaited_once_with(
        internal_user_id=321,
        username="tester",
        cost=7,
        registry_task_id="registry-error",
        final_status="error",
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

    monkeypatch.setattr(
        task_core_web_history_warmup.asyncio,
        "create_task",
        _capture_create_task,
    )
    monkeypatch.setattr(
        task_core,
        "resolve_storage_object",
        lambda _output_file: ("bot-data", "123/output_images/task-1.png"),
    )
    monkeypatch.setattr(storage_module.storage, "async_copy_to_r2", copy_mock)
    monkeypatch.setattr(task_core, "generate_and_upload_thumbnail", thumb_mock)
    monkeypatch.setattr(
        storage_module.storage,
        "async_prune_user_web_history_r2_cache",
        prune_mock,
    )
    monkeypatch.setattr(task_core.logger, "warning", warning_mock)

    task_core_web_history_warmup.schedule_web_history_r2_warmup(
        user_id=123,
        task_id="task-1",
        output_file="123/output_images/task-1.png",
        media_type="image",
        source="web",
        resolve_storage_object_func=task_core.resolve_storage_object,
        copy_to_r2_func=storage_module.storage.async_copy_to_r2,
        generate_and_upload_thumbnail_func=task_core.generate_and_upload_thumbnail,
        prune_user_web_history_r2_cache_func=(
            storage_module.storage.async_prune_user_web_history_r2_cache
        ),
        logger=task_core.logger,
        create_task_func=task_core_web_history_warmup.asyncio.create_task,
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
async def test_schedule_web_history_r2_warmup_handles_bot_source_without_prune():
    scheduled_coroutines = []
    copy_mock = AsyncMock(return_value=None)
    thumb_mock = AsyncMock(return_value=None)
    prune_mock = AsyncMock(return_value=None)

    def _capture_create_task(coro, **_kwargs):
        scheduled_coroutines.append(coro)
        return None

    task_core_web_history_warmup.schedule_web_history_r2_warmup(
        user_id=123,
        task_id="task-bot",
        output_file="123/output_images/task-bot.png",
        media_type="image",
        source="bot",
        resolve_storage_object_func=lambda _output_file: (
            "bot-data",
            "123/output_images/task-bot.png",
        ),
        copy_to_r2_func=copy_mock,
        generate_and_upload_thumbnail_func=thumb_mock,
        prune_user_web_history_r2_cache_func=prune_mock,
        logger=MagicMock(),
        create_task_func=_capture_create_task,
    )

    assert len(scheduled_coroutines) == 1
    await scheduled_coroutines[0]
    copy_mock.assert_awaited_once_with(
        "bot-data",
        "123/output_images/task-bot.png",
        "history/task-bot/original.png",
    )
    thumb_mock.assert_awaited_once_with(
        "123/output_images/task-bot.png",
        "image",
        "history/task-bot/thumb.webp",
    )
    prune_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_schedule_web_history_r2_warmup_uses_runtime_default_create_task_binding(
    monkeypatch,
):
    scheduled_coroutines = []
    copy_mock = AsyncMock(return_value=None)
    thumb_mock = AsyncMock(return_value=None)
    prune_mock = AsyncMock(return_value=None)

    def _capture_create_task(coro):
        scheduled_coroutines.append(coro)
        return None

    monkeypatch.setattr(
        task_core_web_history_warmup.asyncio,
        "create_task",
        _capture_create_task,
    )

    task_core_web_history_warmup.schedule_web_history_r2_warmup(
        user_id=123,
        task_id="task-runtime",
        output_file="123/output_images/task-runtime.png",
        media_type="image",
        source="web",
        resolve_storage_object_func=lambda _output_file: (
            "bot-data",
            "123/output_images/task-runtime.png",
        ),
        copy_to_r2_func=copy_mock,
        generate_and_upload_thumbnail_func=thumb_mock,
        prune_user_web_history_r2_cache_func=prune_mock,
        logger=MagicMock(),
    )

    assert len(scheduled_coroutines) == 1
    await scheduled_coroutines[0]
    copy_mock.assert_awaited_once()
    thumb_mock.assert_awaited_once()
    prune_mock.assert_awaited_once_with(123)


@pytest.mark.asyncio
async def test_attach_web_task_monitor_awaits_pending_finalizer_enqueue(monkeypatch):
    enqueue_pending_web_finalizer = AsyncMock()
    submission_context = MagicMock()

    monkeypatch.setattr(
        "src.services.task_web_finalizer.enqueue_pending_web_finalizer",
        enqueue_pending_web_finalizer,
    )

    await task_web_side_effects.attach_web_task_monitor(
        backend_task_id="backend-1",
        internal_user_id=123,
        username="tester",
        registry_task_id="registry-1",
        submission_context=submission_context,
        cost=5,
        monitor_web_task_func=AsyncMock(),
    )

    enqueue_pending_web_finalizer.assert_awaited_once_with(
        backend_task_id="backend-1",
        internal_user_id=123,
        username="tester",
        registry_task_id="registry-1",
        submission_context=submission_context,
        cost=5,
        source_post_id=None,
    )


@pytest.mark.asyncio
async def test_process_and_submit_task_passes_requested_duration_to_web_monitor():
    strategy = MagicMock()
    strategy.get_cost.return_value = 6
    captured_monitor_calls = []
    submission_context = task_core.TaskSubmissionContext(
        task_type="ltx_video",
        is_video_task=True,
        user_logger=MagicMock(),
        prompt="wide cinematic dolly shot",
        saved_inputs=[],
        metadata={},
        allow_contribute=True,
        final_priority=0,
        video_request=task_core.VideoTaskRequest(
            requested_duration=20,
            output_duration=20,
            output_width=1280,
            output_height=704,
        ),
    )

    def _capture_monitor(**kwargs):
        captured_monitor_calls.append(kwargs)

    def _attach_side_effects(**kwargs):
        return task_web_side_effects.attach_submission_side_effects(
            backend_task_id=kwargs["backend_task_id"],
            internal_user_id=kwargs["internal_user_id"],
            username=kwargs["username"],
            registry_task_id=kwargs["registry_task_id"],
            submission_context=kwargs["submission_context"],
            cost=kwargs["cost"],
            submission_side_effect_plan=kwargs["submission_side_effect_plan"],
            attach_web_task_monitor_func=_capture_monitor,
            schedule_apply_interaction_func=lambda *_args, **_kwargs: None,
            core_domain_error_cls=task_core.CoreDomainError,
        )

    dependencies = TaskCoreProcessDependencies(
        get_strategy_func=MagicMock(return_value=strategy),
        video_task_types={"ltx_video"},
        build_video_task_request_func=MagicMock(
            return_value=task_core.VideoTaskRequest(
                requested_duration=20,
                output_duration=20,
                output_width=1280,
                output_height=704,
            )
        ),
        check_concurrency_lock_func=AsyncMock(return_value=(True, "")),
        prepare_task_submission_payload_func=AsyncMock(return_value=submission_context),
        check_and_deduct_credits_func=AsyncMock(return_value=(True, "")),
        execute_task_submission_saga_func=AsyncMock(
            return_value=task_core.TaskSubmissionExecutionResult(
                registry_task_id="reg-1",
                backend_task_id="backend-task-1",
                submission_context=submission_context,
            )
        ),
        attach_submission_side_effects_func=_attach_side_effects,
        compensate_failed_submission_func=AsyncMock(),
        release_concurrency_lock_func=AsyncMock(),
        shield_func=AsyncMock(),
        logger=MagicMock(),
    )

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
        submission_side_effect_plan=task_core.TaskSubmissionSideEffectPlan(
            attach_web_monitor=True
        ),
        dependencies=dependencies,
    )

    assert result["task_id"] == "reg-1"
    assert len(captured_monitor_calls) == 1
    captured_submission_context = captured_monitor_calls[0]["submission_context"]
    assert captured_submission_context.requested_duration == 20
    assert captured_submission_context.output_duration == 20


@pytest.mark.asyncio
async def test_persist_successful_task_result_reuses_core_path_for_bot():
    fake_user_logger = MagicMock()
    fake_user_logger.save_output_image.return_value = "456/output_images/task-2.png"
    fake_user_logger.log_task = AsyncMock()
    refresh_mock = AsyncMock()
    warmup_mock = MagicMock()
    dependencies = TaskCorePersistenceDependencies(
        user_logger_factory=lambda *_args, **_kwargs: fake_user_logger,
        download_result_func=AsyncMock(return_value=b"image-bytes"),
        download_video_result_func=AsyncMock(),
        extract_media_metadata_from_bytes_best_effort_func=(
            lambda *_args, **_kwargs: (768, 1024, None)
        ),
        extract_media_metadata_from_storage_best_effort_func=AsyncMock(),
        schedule_web_history_r2_warmup_func=warmup_mock,
        refresh_user_group_func=refresh_mock,
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
        dependencies=dependencies,
    )

    assert result.media_bytes == b"image-bytes"
    assert result.output_file == "456/output_images/task-2.png"
    assert result.width == 768
    assert result.height == 1024
    assert result.duration is None
    fake_user_logger.log_task.assert_awaited_once()
    refresh_mock.assert_awaited_once_with(456)
    warmup_mock.assert_not_called()


@pytest.mark.asyncio
async def test_persist_successful_task_result_uses_storage_metadata_when_bytes_missing():
    fake_user_logger = MagicMock()
    fake_user_logger.log_task = AsyncMock()
    warmup_mock = MagicMock()
    extract_from_storage_mock = AsyncMock(return_value=(640, 480, 12))
    dependencies = TaskCorePersistenceDependencies(
        user_logger_factory=lambda *_args, **_kwargs: fake_user_logger,
        download_result_func=AsyncMock(),
        download_video_result_func=AsyncMock(return_value=None),
        extract_media_metadata_from_bytes_best_effort_func=MagicMock(),
        extract_media_metadata_from_storage_best_effort_func=extract_from_storage_mock,
        schedule_web_history_r2_warmup_func=warmup_mock,
        refresh_user_group_func=None,
    )

    result = await task_core.persist_successful_task_result(
        backend_task_id="task-3",
        registry_task_id="task-3",
        internal_user_id=789,
        username="tester",
        prompt="video prompt",
        task_type="ltx_video",
        input_images=["input.png"],
        allow_contribute=False,
        is_video=True,
        billing_resolution="720p",
        requested_duration=12,
        result_path="bot-data/worker/task-3.mp4",
        postprocess_plan=TaskPersistencePostprocessPlan(
            source="web",
            warmup_web_history=True,
        ),
        dependencies=dependencies,
    )

    assert result.media_bytes is None
    assert result.output_file == "bot-data/worker/task-3.mp4"
    assert result.width == 640
    assert result.height == 480
    assert result.duration == 12
    fake_user_logger.save_output_image.assert_not_called()
    extract_from_storage_mock.assert_awaited_once_with(
        "bot-data/worker/task-3.mp4",
        "video",
        (None, None, None),
    )
    fake_user_logger.log_task.assert_awaited_once()
    warmup_mock.assert_called_once_with(
        user_id=789,
        task_id="task-3",
        output_file="bot-data/worker/task-3.mp4",
        media_type="video",
        source="web",
    )


@pytest.mark.asyncio
async def test_postprocess_successful_task_persistence_logs_refreshes_and_warms_up():
    fake_user_logger = MagicMock()
    fake_user_logger.log_task = AsyncMock()
    refresh_mock = AsyncMock()
    warmup_mock = MagicMock()

    persistence_result = TaskSuccessPersistenceResult(
        media_bytes=b"image-bytes",
        output_file="123/output_images/task-4.png",
        width=512,
        height=512,
        duration=None,
    )

    await postprocess_successful_task_persistence(
        user_logger=fake_user_logger,
        persistence_result=persistence_result,
        registry_task_id="task-4",
        internal_user_id=123,
        prompt="prompt",
        task_type="image",
        input_images=["input.png"],
        allow_contribute=True,
        source="web",
        billing_resolution="512",
        requested_duration=None,
        media_type="image",
        refresh_user_group_after_log=True,
        warmup_web_history=True,
        refresh_user_group_func=refresh_mock,
        schedule_web_history_r2_warmup_func=warmup_mock,
    )

    fake_user_logger.log_task.assert_awaited_once_with(
        "prompt",
        ["input.png"],
        "123/output_images/task-4.png",
        task_id="task-4",
        type="image",
        allow_contribute=True,
        source="web",
        billing_resolution="512",
        width=512,
        height=512,
        duration=None,
        requested_duration=None,
        extra_outputs=None,
    )
    refresh_mock.assert_awaited_once_with(123)
    warmup_mock.assert_called_once_with(
        user_id=123,
        task_id="task-4",
        output_file="123/output_images/task-4.png",
        media_type="image",
        source="web",
    )


@pytest.mark.asyncio
async def test_persist_successful_web_history_routes_through_persistence_boundary(monkeypatch):
    persist_mock = AsyncMock()
    monkeypatch.setattr(
        task_core_persistence, "persist_successful_task_result", persist_mock
    )

    await task_core_persistence._persist_successful_web_history(
        backend_task_id="backend-1",
        registry_task_id="registry-1",
        internal_user_id=123,
        username="tester",
        prompt="prompt",
        task_type="image",
        input_images=["input.png"],
        allow_contribute=True,
        is_video=False,
        result_path="bot-data/worker/task-1.png",
        billing_resolution="1024",
        output_width=1024,
        output_height=1024,
        output_duration=None,
        requested_duration=None,
    )

    persist_mock.assert_awaited_once_with(
        backend_task_id="backend-1",
        registry_task_id="registry-1",
        internal_user_id=123,
        username="tester",
        prompt="prompt",
        task_type="image",
        input_images=["input.png"],
        allow_contribute=True,
        is_video=False,
        result_path="bot-data/worker/task-1.png",
        extra_outputs=None,
        billing_resolution="1024",
        output_width=1024,
        output_height=1024,
        output_duration=None,
        requested_duration=None,
        postprocess_plan=TaskPersistencePostprocessPlan(
            source="web",
            warmup_web_history=True,
        ),
    )


@pytest.mark.asyncio
async def test_web_history_default_forwards_private_asset_postprocess_plan(monkeypatch):
    persist_mock = AsyncMock()
    monkeypatch.setattr(
        task_core_persistence, "_persist_successful_web_history", persist_mock
    )
    postprocess_plan = TaskPersistencePostprocessPlan(
        source="web",
        record_history=False,
        refresh_user_group_after_log=False,
        warmup_web_history=False,
    )

    await task_core_persistence.persist_successful_web_history_default(
        backend_task_id="backend-1",
        registry_task_id="registry-1",
        internal_user_id=123,
        username="tester",
        prompt="front portrait",
        task_type="character_reference_build",
        input_images=["source.png"],
        allow_contribute=False,
        is_video=False,
        result_path="private/view.png",
        billing_resolution=None,
        output_width=None,
        output_height=None,
        output_duration=None,
        requested_duration=None,
        postprocess_plan=postprocess_plan,
    )

    assert persist_mock.await_args.kwargs["postprocess_plan"] == postprocess_plan
