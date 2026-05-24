import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core import task_core
from src.core import task_core_dependency_builders as dependency_builders
from src.core.task_core_dependencies import TaskCoreProcessDependencies
from src.core.task_core_types import TaskSubmissionExecutionResult, VideoTaskRequest


def test_build_task_core_warmup_dependencies_binds_explicit_capabilities():
    copy_to_r2 = AsyncMock()
    prune_cache = AsyncMock()
    thumbnail = AsyncMock()
    create_task = MagicMock()
    logger = MagicMock()

    dependencies = dependency_builders.build_task_core_warmup_dependencies(
        copy_to_r2_func=copy_to_r2,
        prune_user_web_history_r2_cache_func=prune_cache,
        resolve_storage_object_func=lambda path: ("bucket", path),
        generate_and_upload_thumbnail_func=thumbnail,
        create_task_func=create_task,
        logger=logger,
    )

    assert dependencies.resolve_storage_object_func("foo") == ("bucket", "foo")
    assert dependencies.copy_to_r2_func is copy_to_r2
    assert dependencies.prune_user_web_history_r2_cache_func is prune_cache
    assert dependencies.generate_and_upload_thumbnail_func is thumbnail
    assert dependencies.create_task_func is create_task
    assert dependencies.logger is logger


def test_build_task_core_runtime_and_submission_dependencies_bind_explicit_capabilities():
    release_lock = AsyncMock()
    add_task = AsyncMock()
    remove_task = AsyncMock()
    update_backend_task_id = AsyncMock()
    mark_task_status = AsyncMock()
    add_pending_refund = AsyncMock()
    dispatch_to_worker = AsyncMock()
    logger = MagicMock()

    runtime_dependencies = dependency_builders.build_task_core_runtime_dependencies(
        remove_task_func=remove_task,
        release_concurrency_lock_func=release_lock,
    )
    submission_dependencies = dependency_builders.build_task_core_submission_dependencies(
        add_task_func=add_task,
        update_backend_task_id_func=update_backend_task_id,
        mark_task_status_func=mark_task_status,
        remove_task_func=remove_task,
        add_pending_refund_func=add_pending_refund,
        dispatch_to_worker_func=dispatch_to_worker,
        is_task_backend_busy_error_func=task_core.is_task_backend_busy_error,
        logger=logger,
    )

    assert runtime_dependencies.release_concurrency_lock_func is release_lock
    assert runtime_dependencies.remove_task_func is remove_task
    assert submission_dependencies.add_task_func is add_task
    assert submission_dependencies.update_backend_task_id_func is update_backend_task_id
    assert submission_dependencies.mark_task_status_func is mark_task_status
    assert submission_dependencies.remove_task_func is remove_task
    assert submission_dependencies.add_pending_refund_func is add_pending_refund
    assert submission_dependencies.dispatch_to_worker_func is dispatch_to_worker
    assert (
        submission_dependencies.is_task_backend_busy_error_func
        is task_core.is_task_backend_busy_error
    )
    assert submission_dependencies.logger is logger


def test_build_task_core_process_dependencies_bind_explicit_services():
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
    build_video_task_request = MagicMock(return_value=("video", "custom_video", {"foo": "bar"}))

    dependencies = dependency_builders.build_task_core_process_dependencies(
        get_strategy_func=get_strategy,
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
    )

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


def test_build_task_core_persistence_and_monitor_dependencies_bind_explicit_capabilities():
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

    persistence_dependencies = dependency_builders.build_task_core_persistence_dependencies(
        download_result_func=download_result,
        download_video_result_func=download_video_result,
        refresh_user_group_func=refresh_user_group,
        user_logger_factory=user_logger_factory,
        extract_media_metadata_from_bytes_best_effort_func=extract_from_bytes,
        extract_media_metadata_from_storage_best_effort_func=extract_from_storage,
        schedule_web_history_r2_warmup_func=warmup,
    )
    monitor_dependencies = dependency_builders.build_task_core_monitor_dependencies(
        monitor_progress_func=monitor_progress,
        normalize_terminal_status_func=task_core.normalize_terminal_status,
        finalize_success_func=finalize_success,
        finalize_cancellation_func=finalize_cancellation,
        finalize_failure_func=finalize_failure,
        logger=logger,
    )

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


def test_build_task_core_finalization_dependencies_bind_explicit_services():
    refund_credits = AsyncMock()
    cleanup_runtime = AsyncMock()
    refund_cancelled = AsyncMock()
    force_terminate = AsyncMock()

    dependencies = dependency_builders.build_task_core_finalization_dependencies(
        refund_credits_func=refund_credits,
        cleanup_task_runtime_state_func=cleanup_runtime,
        refund_cancelled_task_func=refund_cancelled,
        force_terminate_task_func=force_terminate,
    )

    assert dependencies.refund_credits_func is refund_credits
    assert dependencies.cleanup_task_runtime_state_func is cleanup_runtime
    assert dependencies.refund_cancelled_task_func is refund_cancelled
    assert dependencies.force_terminate_task_func is force_terminate


def test_build_task_core_side_effect_dependencies_bind_explicit_services():
    attach_web_task_monitor = MagicMock()
    create_task = MagicMock()
    monitor_web_task = AsyncMock()
    record_apply_interaction = AsyncMock()

    dependencies = dependency_builders.build_task_core_side_effect_dependencies(
        attach_web_task_monitor_func=attach_web_task_monitor,
        monitor_web_task_func=monitor_web_task,
        record_apply_interaction_func=record_apply_interaction,
        create_task_func=create_task,
    )

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
        "_build_task_core_process_dependencies_impl",
        lambda **_kwargs: TaskCoreProcessDependencies(
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
        "build_default_task_core_side_effect_dependencies",
        lambda **_kwargs: dependencies,
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
