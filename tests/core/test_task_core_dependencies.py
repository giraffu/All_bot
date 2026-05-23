from types import SimpleNamespace
import inspect
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core import task_core
from src.core.task_core_dependencies import TaskCoreProcessDependencies
from src.core.task_core_types import TaskSubmissionExecutionResult, VideoTaskRequest


@pytest.mark.asyncio
async def test_build_task_core_warmup_dependencies_bind_current_runtime_services(
    monkeypatch,
):
    copy_to_r2 = AsyncMock()
    prune_cache = AsyncMock()
    thumbnail = AsyncMock()
    create_task = MagicMock()
    logger = MagicMock()

    monkeypatch.setattr(
        task_core, "resolve_storage_object", lambda path: ("bucket", path)
    )
    monkeypatch.setattr(
        task_core,
        "_get_storage_service",
        lambda: SimpleNamespace(
            async_copy_to_r2=copy_to_r2,
            async_prune_user_web_history_r2_cache=prune_cache,
        ),
    )
    monkeypatch.setattr(task_core, "generate_and_upload_thumbnail", thumbnail)
    monkeypatch.setattr(task_core.asyncio, "create_task", create_task)
    monkeypatch.setattr(task_core, "logger", logger)

    dependencies = task_core._build_task_core_warmup_dependencies()

    assert dependencies.resolve_storage_object_func("foo") == ("bucket", "foo")
    assert dependencies.copy_to_r2_func is copy_to_r2
    assert dependencies.prune_user_web_history_r2_cache_func is prune_cache
    assert dependencies.generate_and_upload_thumbnail_func is thumbnail
    assert dependencies.create_task_func is create_task
    assert dependencies.logger is logger


@pytest.mark.asyncio
async def test_build_task_core_runtime_and_submission_dependencies_bind_current_adapters(
    monkeypatch,
):
    release_lock = AsyncMock()
    add_task = AsyncMock()
    remove_task = AsyncMock()
    update_backend_task_id = AsyncMock()
    mark_task_status = AsyncMock()
    add_pending_refund = AsyncMock()
    dispatch_to_worker = AsyncMock()
    logger = MagicMock()

    monkeypatch.setattr(task_core, "release_concurrency_lock", release_lock)
    monkeypatch.setattr(
        task_core,
        "_get_task_registry",
        lambda: SimpleNamespace(
            add_task=add_task,
            remove_task=remove_task,
            update_backend_task_id=update_backend_task_id,
            mark_task_status=mark_task_status,
        ),
    )
    monkeypatch.setattr(task_core, "dispatch_to_worker", dispatch_to_worker)
    monkeypatch.setattr(task_core, "logger", logger)
    monkeypatch.setattr(
        task_core,
        "_get_submission_outbox",
        lambda: SimpleNamespace(add_pending_refund=add_pending_refund),
    )

    runtime_dependencies = task_core._build_task_core_runtime_dependencies()
    submission_dependencies = task_core._build_task_core_submission_dependencies()

    assert runtime_dependencies.release_concurrency_lock_func is release_lock
    assert runtime_dependencies.remove_task_func is remove_task
    assert submission_dependencies.add_task_func is add_task
    assert submission_dependencies.update_backend_task_id_func is update_backend_task_id
    assert submission_dependencies.mark_task_status_func is mark_task_status
    assert submission_dependencies.remove_task_func is remove_task
    assert submission_dependencies.add_pending_refund_func is add_pending_refund
    assert submission_dependencies.dispatch_to_worker_func is dispatch_to_worker
    assert submission_dependencies.is_task_backend_busy_error_func is task_core.is_task_backend_busy_error
    assert submission_dependencies.logger is logger


@pytest.mark.asyncio
async def test_build_task_core_process_dependencies_bind_current_runtime_services(
    monkeypatch,
):
    get_strategy = MagicMock()
    check_lock = AsyncMock()
    prepare_payload = AsyncMock()
    deduct_credits = AsyncMock()
    execute_saga = AsyncMock()
    attach_side_effects = MagicMock()
    compensate_failed = AsyncMock()
    release_lock = AsyncMock()
    shield = AsyncMock()
    logger = MagicMock()

    monkeypatch.setattr(task_core.StrategyFactory, "get_strategy", get_strategy)
    monkeypatch.setattr(task_core, "build_video_task_request", lambda t, i: ("video", t, i))
    monkeypatch.setattr(task_core, "check_concurrency_lock", check_lock)
    monkeypatch.setattr(task_core, "_prepare_task_submission_payload", prepare_payload)
    monkeypatch.setattr(task_core, "check_and_deduct_credits", deduct_credits)
    monkeypatch.setattr(task_core, "_execute_task_submission_saga", execute_saga)
    monkeypatch.setattr(task_core, "_attach_submission_side_effects", attach_side_effects)
    monkeypatch.setattr(task_core, "_compensate_failed_submission", compensate_failed)
    monkeypatch.setattr(task_core, "release_concurrency_lock", release_lock)
    monkeypatch.setattr(task_core.asyncio, "shield", shield)
    monkeypatch.setattr(task_core, "logger", logger)
    monkeypatch.setattr("src.constants.VIDEO_TASK_TYPES", {"custom_video"})

    dependencies = task_core._build_task_core_process_dependencies()

    assert dependencies.get_strategy_func is get_strategy
    assert dependencies.video_task_types == {"custom_video"}
    assert dependencies.build_video_task_request_func("custom_video", {"foo": "bar"}) == (
        "video",
        "custom_video",
        {"foo": "bar"},
    )
    assert dependencies.check_concurrency_lock_func is check_lock
    assert dependencies.prepare_task_submission_payload_func is prepare_payload
    assert dependencies.check_and_deduct_credits_func is deduct_credits
    assert dependencies.execute_task_submission_saga_func is execute_saga
    assert dependencies.attach_submission_side_effects_func is attach_side_effects
    assert dependencies.compensate_failed_submission_func is compensate_failed
    assert dependencies.release_concurrency_lock_func is release_lock
    assert dependencies.shield_func is shield
    assert dependencies.logger is logger


@pytest.mark.asyncio
async def test_build_task_core_persistence_and_monitor_dependencies_bind_current_services(
    monkeypatch,
):
    user_logger_factory = MagicMock()
    download_result = AsyncMock()
    download_video_result = AsyncMock()
    refresh_user_group = AsyncMock()
    extract_from_bytes = MagicMock()
    extract_from_storage = AsyncMock()
    warmup = MagicMock()
    monitor_progress = AsyncMock()
    finalize_success = AsyncMock()
    finalize_cancellation = AsyncMock()
    finalize_failure = AsyncMock()
    logger = MagicMock()

    monkeypatch.setattr(task_core, "UserLogger", user_logger_factory)
    monkeypatch.setattr(
        task_core,
        "_get_image_service",
        lambda: SimpleNamespace(
            download_result=download_result,
            download_video_result=download_video_result,
            monitor_progress=monitor_progress,
        ),
    )
    monkeypatch.setattr(
        task_core,
        "extract_media_metadata_from_bytes_best_effort",
        extract_from_bytes,
    )
    monkeypatch.setattr(
        task_core,
        "extract_media_metadata_from_storage_best_effort",
        extract_from_storage,
    )
    monkeypatch.setattr(task_core, "schedule_web_history_r2_warmup", warmup)
    monkeypatch.setattr(
        task_core,
        "_get_permission_service",
        lambda: SimpleNamespace(refresh_user_group=refresh_user_group),
    )
    monkeypatch.setattr(task_core, "_finalize_monitored_web_task_success", finalize_success)
    monkeypatch.setattr(
        task_core,
        "_finalize_monitored_web_task_cancellation",
        finalize_cancellation,
    )
    monkeypatch.setattr(task_core, "_finalize_monitored_web_task_failure", finalize_failure)
    monkeypatch.setattr(task_core, "logger", logger)

    persistence_dependencies = task_core._build_task_core_persistence_dependencies()
    monitor_dependencies = task_core._build_task_core_monitor_dependencies()

    assert persistence_dependencies.user_logger_factory is user_logger_factory
    assert persistence_dependencies.download_result_func is download_result
    assert persistence_dependencies.download_video_result_func is download_video_result
    assert (
        persistence_dependencies.extract_media_metadata_from_bytes_best_effort_func
        is extract_from_bytes
    )
    assert (
        persistence_dependencies.extract_media_metadata_from_storage_best_effort_func
        is extract_from_storage
    )
    assert persistence_dependencies.schedule_web_history_r2_warmup_func is warmup
    assert persistence_dependencies.refresh_user_group_func is refresh_user_group

    assert monitor_dependencies.monitor_progress_func is monitor_progress
    assert (
        monitor_dependencies.normalize_terminal_status_func
        is task_core.normalize_terminal_status
    )
    assert monitor_dependencies.finalize_success_func is finalize_success
    assert monitor_dependencies.finalize_cancellation_func is finalize_cancellation
    assert monitor_dependencies.finalize_failure_func is finalize_failure
    assert monitor_dependencies.logger is logger


@pytest.mark.asyncio
async def test_build_task_core_finalization_dependencies_bind_current_services(
    monkeypatch,
):
    refund_credits = AsyncMock()
    cleanup_runtime = AsyncMock()
    refund_cancelled = AsyncMock()
    force_terminate = AsyncMock()

    monkeypatch.setattr(task_core, "refund_credits", refund_credits)
    monkeypatch.setattr(task_core, "cleanup_task_runtime_state", cleanup_runtime)
    monkeypatch.setattr(task_core, "refund_cancelled_task", refund_cancelled)
    monkeypatch.setattr(task_core, "force_terminate_task", force_terminate)

    dependencies = task_core._build_task_core_finalization_dependencies()

    assert dependencies.refund_credits_func is refund_credits
    assert dependencies.cleanup_task_runtime_state_func is cleanup_runtime
    assert dependencies.refund_cancelled_task_func is refund_cancelled
    assert dependencies.force_terminate_task_func is force_terminate


@pytest.mark.asyncio
async def test_build_task_core_side_effect_dependencies_bind_current_services(
    monkeypatch,
):
    attach_web_task_monitor = MagicMock()
    create_task = MagicMock()
    monitor_web_task = AsyncMock()
    record_apply_interaction = AsyncMock()

    monkeypatch.setattr(task_core, "_attach_web_task_monitor_impl", attach_web_task_monitor)
    monkeypatch.setattr(task_core, "monitor_task_and_release_lock", monitor_web_task)
    monkeypatch.setattr(task_core.asyncio, "create_task", create_task)
    monkeypatch.setattr(
        "src.core.gallery_core.record_apply_interaction",
        record_apply_interaction,
    )

    dependencies = task_core._build_task_core_side_effect_dependencies()

    assert dependencies.attach_web_task_monitor_func is attach_web_task_monitor
    assert dependencies.monitor_web_task_func is monitor_web_task
    assert dependencies.record_apply_interaction_func is record_apply_interaction
    assert dependencies.create_task_func is create_task


@pytest.mark.asyncio
async def test_process_and_submit_task_uses_process_dependencies_builder(monkeypatch):
    strategy = MagicMock()
    strategy.get_cost.return_value = 18
    check_lock = AsyncMock(return_value=(True, ""))
    prepare_payload = AsyncMock(
        return_value=SimpleNamespace(
            final_priority=7,
            saved_inputs=["input.png"],
            user_logger=SimpleNamespace(user_id=123, username="tester"),
        )
    )
    deduct_credits = AsyncMock(return_value=(True, ""))
    execute_saga = AsyncMock(
        return_value=TaskSubmissionExecutionResult(
            registry_task_id="registry-2",
            backend_task_id="backend-2",
            submission_context=SimpleNamespace(saved_inputs=["saved.png"]),
        )
    )
    attach_side_effects = MagicMock()
    compensate_failed = AsyncMock()
    release_lock = AsyncMock()
    shield = AsyncMock()
    logger = MagicMock()
    build_video_task_request = MagicMock(return_value=VideoTaskRequest())

    monkeypatch.setattr(
        task_core,
        "_build_task_core_process_dependencies",
        lambda: TaskCoreProcessDependencies(
            get_strategy_func=MagicMock(return_value=strategy),
            video_task_types={"custom_video"},
            build_video_task_request_func=build_video_task_request,
            check_concurrency_lock_func=check_lock,
            prepare_task_submission_payload_func=prepare_payload,
            check_and_deduct_credits_func=deduct_credits,
            execute_task_submission_saga_func=execute_saga,
            attach_submission_side_effects_func=attach_side_effects,
            compensate_failed_submission_func=compensate_failed,
            release_concurrency_lock_func=release_lock,
            shield_func=shield,
            logger=logger,
        ),
    )

    result = await task_core.process_and_submit_task(
        user_id=123,
        username="tester",
        task_type="custom_video",
        inputs={"prompt": "hello"},
        task_id="registry-1",
    )

    assert result == {
        "task_id": "registry-2",
        "registry_task_id": "registry-2",
        "backend_task_id": "backend-2",
        "cost": 18,
        "saved_inputs": ["saved.png"],
    }
    strategy.get_cost.assert_called_once_with({"prompt": "hello"})
    build_video_task_request.assert_called_once_with("custom_video", {"prompt": "hello"})
    check_lock.assert_awaited_once_with(123)
    prepare_payload.assert_awaited_once()
    deduct_credits.assert_awaited_once_with(123, 18, "custom_video", "tester")
    execute_saga.assert_awaited_once()
    attach_side_effects.assert_called_once()
    compensate_failed.assert_not_called()
    release_lock.assert_not_called()
    shield.assert_not_called()


@pytest.mark.asyncio
async def test_persist_successful_task_result_and_monitor_task_use_dependency_builders(
    monkeypatch,
):
    fake_persistence_impl = AsyncMock(
        return_value=TaskSubmissionExecutionResult(
            registry_task_id="ignored",
            backend_task_id="ignored",
            submission_context=SimpleNamespace(),
        )
    )
    fake_monitor_impl = AsyncMock(return_value=None)
    persistence_dependencies = SimpleNamespace(
        user_logger_factory=MagicMock(),
        download_result_func=AsyncMock(),
        download_video_result_func=AsyncMock(),
        extract_media_metadata_from_bytes_best_effort_func=MagicMock(),
        extract_media_metadata_from_storage_best_effort_func=AsyncMock(),
        schedule_web_history_r2_warmup_func=MagicMock(),
        refresh_user_group_func=AsyncMock(),
    )
    monitor_dependencies = SimpleNamespace(
        monitor_progress_func=AsyncMock(),
        normalize_terminal_status_func=MagicMock(),
        finalize_success_func=AsyncMock(),
        finalize_cancellation_func=AsyncMock(),
        finalize_failure_func=AsyncMock(),
        logger=MagicMock(),
    )

    monkeypatch.setattr(task_core, "_persist_successful_task_result_impl", fake_persistence_impl)
    monkeypatch.setattr(task_core, "_monitor_task_and_release_lock_impl", fake_monitor_impl)
    monkeypatch.setattr(
        task_core,
        "_build_task_core_persistence_dependencies",
        lambda: persistence_dependencies,
    )
    monkeypatch.setattr(
        task_core,
        "_build_task_core_monitor_dependencies",
        lambda: monitor_dependencies,
    )

    await task_core.persist_successful_task_result(
        backend_task_id="backend-1",
        registry_task_id="registry-1",
        internal_user_id=123,
        username="tester",
        prompt="hello",
        task_type="image",
        input_images=["input.png"],
        allow_contribute=True,
        is_video=False,
        billing_resolution="1024",
        requested_duration=None,
    )
    await task_core.monitor_task_and_release_lock(
        backend_task_id="backend-2",
        internal_user_id=456,
        username="tester",
        registry_task_id="registry-2",
        submission_context=SimpleNamespace(is_video_task=False),
        cost=8,
    )

    persistence_kwargs = fake_persistence_impl.await_args.kwargs
    assert persistence_kwargs["user_logger_factory"] is persistence_dependencies.user_logger_factory
    assert persistence_kwargs["download_result_func"] is persistence_dependencies.download_result_func
    assert (
        persistence_kwargs["download_video_result_func"]
        is persistence_dependencies.download_video_result_func
    )
    assert (
        persistence_kwargs["extract_media_metadata_from_bytes_best_effort_func"]
        is persistence_dependencies.extract_media_metadata_from_bytes_best_effort_func
    )
    assert (
        persistence_kwargs["extract_media_metadata_from_storage_best_effort_func"]
        is persistence_dependencies.extract_media_metadata_from_storage_best_effort_func
    )
    assert (
        persistence_kwargs["schedule_web_history_r2_warmup_func"]
        is persistence_dependencies.schedule_web_history_r2_warmup_func
    )
    assert (
        persistence_kwargs["refresh_user_group_func"]
        is persistence_dependencies.refresh_user_group_func
    )

    monitor_kwargs = fake_monitor_impl.await_args.kwargs
    assert monitor_kwargs["monitor_progress_func"] is monitor_dependencies.monitor_progress_func
    assert (
        monitor_kwargs["normalize_terminal_status_func"]
        is monitor_dependencies.normalize_terminal_status_func
    )
    assert monitor_kwargs["finalize_success_func"] is monitor_dependencies.finalize_success_func
    assert (
        monitor_kwargs["finalize_cancellation_func"]
        is monitor_dependencies.finalize_cancellation_func
    )
    assert monitor_kwargs["finalize_failure_func"] is monitor_dependencies.finalize_failure_func
    assert monitor_kwargs["logger"] is monitor_dependencies.logger


@pytest.mark.asyncio
async def test_finalization_wrappers_use_finalization_dependency_builder(monkeypatch):
    refund_cancelled_impl = AsyncMock(return_value=True)
    refund_failed_impl = AsyncMock(return_value=True)
    handle_failed_impl = AsyncMock(return_value="handled")
    finalize_failure_impl = AsyncMock(return_value=SimpleNamespace(refunded=True))
    finalize_cancellation_impl = AsyncMock(return_value=SimpleNamespace(refunded=True))
    finalize_terminated_impl = AsyncMock(return_value=SimpleNamespace(refunded=True))
    dependencies = SimpleNamespace(
        refund_credits_func=AsyncMock(),
        cleanup_task_runtime_state_func=AsyncMock(),
        refund_cancelled_task_func=AsyncMock(),
        force_terminate_task_func=AsyncMock(),
    )

    monkeypatch.setattr(task_core, "_refund_cancelled_task_impl", refund_cancelled_impl)
    monkeypatch.setattr(task_core, "_refund_failed_task_impl", refund_failed_impl)
    monkeypatch.setattr(task_core, "_handle_failed_task_exception_impl", handle_failed_impl)
    monkeypatch.setattr(task_core, "_finalize_task_failure_impl", finalize_failure_impl)
    monkeypatch.setattr(
        task_core,
        "_finalize_task_cancellation_impl",
        finalize_cancellation_impl,
    )
    monkeypatch.setattr(
        task_core,
        "_finalize_terminated_task_impl",
        finalize_terminated_impl,
    )
    monkeypatch.setattr(
        task_core,
        "_build_task_core_finalization_dependencies",
        lambda: dependencies,
    )

    await task_core.refund_cancelled_task(
        internal_user_id=1,
        username="u1",
        cost=2,
        task_submitted=True,
    )
    await task_core.refund_failed_task(
        internal_user_id=1,
        username="u1",
        cost=2,
        should_refund=True,
    )
    result_message = await task_core.handle_failed_task_exception(
        internal_user_id=1,
        username="u1",
        cost=2,
        should_refund=True,
        error=RuntimeError("boom"),
        generic_error_prefix="错误",
    )
    await task_core.finalize_task_failure(
        internal_user_id=1,
        username="u1",
        cost=2,
        should_refund=True,
        registry_task_id="reg-1",
    )
    await task_core.finalize_task_cancellation(
        internal_user_id=1,
        username="u1",
        cost=2,
        task_submitted=True,
        registry_task_id="reg-1",
    )
    await task_core.finalize_terminated_task(
        registry_task_id="reg-1",
        user_id=1,
        username="u1",
        cost=2,
        should_refund=True,
        refund_task_type="refund_admin_force",
    )

    assert result_message == "handled"
    assert (
        refund_cancelled_impl.await_args.kwargs["refund_credits_func"]
        is dependencies.refund_credits_func
    )
    assert (
        refund_failed_impl.await_args.kwargs["refund_credits_func"]
        is dependencies.refund_credits_func
    )
    assert (
        handle_failed_impl.await_args.kwargs["refund_credits_func"]
        is dependencies.refund_credits_func
    )
    assert (
        finalize_failure_impl.await_args.kwargs["refund_credits_func"]
        is dependencies.refund_credits_func
    )
    assert (
        finalize_failure_impl.await_args.kwargs["cleanup_task_runtime_state_func"]
        is dependencies.cleanup_task_runtime_state_func
    )
    assert (
        finalize_cancellation_impl.await_args.kwargs["refund_cancelled_task_func"]
        is dependencies.refund_cancelled_task_func
    )
    assert (
        finalize_cancellation_impl.await_args.kwargs["cleanup_task_runtime_state_func"]
        is dependencies.cleanup_task_runtime_state_func
    )
    assert (
        finalize_terminated_impl.await_args.kwargs["force_terminate_task_func"]
        is dependencies.force_terminate_task_func
    )
    assert (
        finalize_terminated_impl.await_args.kwargs["refund_credits_func"]
        is dependencies.refund_credits_func
    )


@pytest.mark.asyncio
async def test_side_effect_wrappers_use_side_effect_dependency_builder(monkeypatch):
    attach_web_task_monitor_impl = MagicMock()
    monitor_web_task = AsyncMock()
    record_apply_interaction = AsyncMock()
    create_task = MagicMock()
    dependencies = SimpleNamespace(
        attach_web_task_monitor_func=attach_web_task_monitor_impl,
        monitor_web_task_func=monitor_web_task,
        record_apply_interaction_func=record_apply_interaction,
        create_task_func=create_task,
    )
    submission_context = SimpleNamespace()

    monkeypatch.setattr(
        task_core,
        "_build_task_core_side_effect_dependencies",
        lambda: dependencies,
    )

    task_core._attach_web_task_monitor(
        backend_task_id="backend-1",
        internal_user_id=1,
        username="tester",
        registry_task_id="reg-1",
        submission_context=submission_context,
        cost=8,
    )
    task_core._schedule_apply_interaction(1, 99)

    attach_web_task_monitor_impl.assert_called_once_with(
        backend_task_id="backend-1",
        internal_user_id=1,
        username="tester",
        registry_task_id="reg-1",
        submission_context=submission_context,
        cost=8,
        monitor_web_task_func=monitor_web_task,
    )
    create_task.assert_called_once()
    scheduled_coro = create_task.call_args.args[0]
    assert inspect.iscoroutine(scheduled_coro)
    record_apply_interaction.assert_called_once_with(1, 99)
    scheduled_coro.close()


@pytest.mark.asyncio
async def test_attach_submission_side_effects_raises_domain_error_when_monitor_attach_fails(
    monkeypatch,
):
    monkeypatch.setattr(
        task_core,
        "_attach_web_task_monitor",
        MagicMock(side_effect=RuntimeError("boom")),
    )
    schedule_apply = MagicMock()
    monkeypatch.setattr(task_core, "_schedule_apply_interaction", schedule_apply)

    with pytest.raises(task_core.CoreDomainError, match="后台监控挂载失败: boom"):
        task_core._attach_submission_side_effects(
            client_type="web",
            backend_task_id="backend-1",
            internal_user_id=1,
            username="tester",
            registry_task_id="reg-1",
            submission_context=SimpleNamespace(),
            cost=8,
            source_post_id=9,
        )

    schedule_apply.assert_not_called()
