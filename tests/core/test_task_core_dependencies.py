import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core import task_core
from src.constants import MODE_PORNMASTER_FLUX2_SINGLE_EDIT
from src import task_core_process_defaults
from src.core.task_core_dependencies import TaskCoreProcessDependencies
from src.core.task_core_types import (
    CoreDomainError,
    TaskSubmissionExecutionResult,
    TaskSubmissionSideEffectPlan,
    VideoTaskRequest,
)
from src.core import task_core_submission
from src.core import task_dispatcher
from src.services import task_web_side_effects


@pytest.mark.asyncio
async def test_process_and_submit_task_uses_explicit_process_dependencies():
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
    attach_side_effects = AsyncMock()
    compensate_failed = AsyncMock()
    release_lock = AsyncMock()
    shield = AsyncMock()
    logger = MagicMock()
    build_video_task_request = MagicMock(return_value=VideoTaskRequest())

    dependencies = TaskCoreProcessDependencies(
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
    )

    result = await task_core.process_and_submit_task(
        user_id=123,
        username="tester",
        task_type="custom_video",
        inputs={"prompt": "hello"},
        task_id="registry-1",
        dependencies=dependencies,
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
    check_lock.assert_awaited_once_with(
        123,
        idempotency_key="task_concurrency:registry-1",
    )
    prepare_payload.assert_awaited_once()
    deduct_credits.assert_awaited_once_with(123, 18, "custom_video", "tester")
    execute_saga.assert_awaited_once()
    assert (
        execute_saga.await_args.kwargs[
            "submission_context"
        ].concurrency_acquisition_key
        == "task_concurrency:registry-1"
    )
    attach_side_effects.assert_called_once()
    side_effect_plan = attach_side_effects.call_args.kwargs["submission_side_effect_plan"]
    assert side_effect_plan == TaskSubmissionSideEffectPlan(attach_web_monitor=True)
    compensate_failed.assert_not_called()
    release_lock.assert_not_called()
    shield.assert_not_called()


@pytest.mark.asyncio
async def test_prepare_timeout_releases_the_exact_task_concurrency_owner():
    strategy = MagicMock()
    strategy.get_cost.return_value = 6

    async def never_prepares(**_kwargs):
        await asyncio.Event().wait()

    async def shield(awaitable):
        return await awaitable

    dependencies = TaskCoreProcessDependencies(
        get_strategy_func=MagicMock(return_value=strategy),
        video_task_types=set(),
        build_video_task_request_func=MagicMock(return_value=VideoTaskRequest()),
        check_concurrency_lock_func=AsyncMock(return_value=(True, "")),
        prepare_task_submission_payload_func=never_prepares,
        check_and_deduct_credits_func=AsyncMock(return_value=(True, "")),
        execute_task_submission_saga_func=AsyncMock(),
        attach_submission_side_effects_func=AsyncMock(),
        compensate_failed_submission_func=AsyncMock(),
        release_concurrency_lock_func=AsyncMock(),
        shield_func=shield,
        logger=MagicMock(),
    )

    with pytest.raises(asyncio.TimeoutError):
        await task_core.process_and_submit_task(
            user_id=123,
            username="tester",
            task_type="quick_image",
            inputs={"prompt": "hello"},
            task_id="deterministic-task",
            submission_prepare_timeout_seconds=0.001,
            dependencies=dependencies,
        )

    dependencies.release_concurrency_lock_func.assert_awaited_once_with(
        123,
        idempotency_key="task_concurrency:deterministic-task",
    )
    dependencies.check_and_deduct_credits_func.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_and_submit_task_uses_internal_cost_override_for_deduction():
    strategy = MagicMock()
    strategy.get_cost.return_value = 1
    dependencies = TaskCoreProcessDependencies(
        get_strategy_func=MagicMock(return_value=strategy),
        video_task_types=set(),
        build_video_task_request_func=MagicMock(return_value=VideoTaskRequest()),
        check_concurrency_lock_func=AsyncMock(return_value=(True, "")),
        prepare_task_submission_payload_func=AsyncMock(
            return_value=SimpleNamespace(
                final_priority=7,
                saved_inputs=["input.png"],
                user_logger=SimpleNamespace(user_id=123, username="tester"),
            )
        ),
        check_and_deduct_credits_func=AsyncMock(return_value=(True, "")),
        execute_task_submission_saga_func=AsyncMock(
            return_value=TaskSubmissionExecutionResult(
                registry_task_id="registry-2",
                backend_task_id="backend-2",
                submission_context=SimpleNamespace(saved_inputs=["saved.png"]),
            )
        ),
        attach_submission_side_effects_func=AsyncMock(),
        compensate_failed_submission_func=AsyncMock(),
        release_concurrency_lock_func=AsyncMock(),
        shield_func=AsyncMock(),
        logger=MagicMock(),
    )

    result = await task_core.process_and_submit_task(
        user_id=123,
        username="tester",
        task_type="face_swap",
        inputs={"images": ["body.png", "face.png"]},
        task_id="registry-1",
        cost_override=2,
        dependencies=dependencies,
    )

    strategy.get_cost.assert_not_called()
    dependencies.check_and_deduct_credits_func.assert_awaited_once_with(
        123,
        2,
        "face_swap",
        "tester",
    )
    dependencies.execute_task_submission_saga_func.assert_awaited_once()
    assert dependencies.execute_task_submission_saga_func.await_args.kwargs["cost"] == 2
    assert result["cost"] == 2


@pytest.mark.asyncio
async def test_process_and_submit_task_keeps_legacy_lock_dependency_compatible():
    strategy = MagicMock()
    strategy.get_cost.return_value = 1

    async def legacy_check_lock(_user_id):
        return True, ""

    dependencies = TaskCoreProcessDependencies(
        get_strategy_func=MagicMock(return_value=strategy),
        video_task_types=set(),
        build_video_task_request_func=MagicMock(return_value=VideoTaskRequest()),
        check_concurrency_lock_func=legacy_check_lock,
        prepare_task_submission_payload_func=AsyncMock(
            return_value=SimpleNamespace(saved_inputs=[])
        ),
        check_and_deduct_credits_func=AsyncMock(return_value=(True, "")),
        execute_task_submission_saga_func=AsyncMock(
            return_value=TaskSubmissionExecutionResult(
                registry_task_id="registry-1",
                backend_task_id="backend-1",
                submission_context=SimpleNamespace(saved_inputs=[]),
            )
        ),
        attach_submission_side_effects_func=AsyncMock(),
        compensate_failed_submission_func=AsyncMock(),
        release_concurrency_lock_func=AsyncMock(),
        shield_func=AsyncMock(),
        logger=MagicMock(),
    )

    result = await task_core.process_and_submit_task(
        user_id=123,
        username="tester",
        task_type="face_swap",
        inputs={"images": ["body.png", "face.png"]},
        task_id="registry-1",
        cost_override=5,
        dependencies=dependencies,
    )

    assert result["cost"] == 5
    dependencies.check_and_deduct_credits_func.assert_awaited_once_with(
        123,
        5,
        "face_swap",
        "tester",
    )


@pytest.mark.asyncio
async def test_private_submission_persists_actual_cost_before_debit():
    events = []
    strategy = MagicMock()
    strategy.get_cost.return_value = 6

    async def record_cost(**kwargs):
        events.append(("ledger_cost", kwargs["cost"]))

    async def deduct(*args, **kwargs):
        events.append(("debit", args[1], kwargs["idempotency_key"]))
        return True, ""

    async def execute(**kwargs):
        events.append(("dispatch", kwargs["cost"]))
        return TaskSubmissionExecutionResult(
            registry_task_id="deterministic-task",
            backend_task_id="backend-task",
            submission_context=SimpleNamespace(saved_inputs=[]),
        )

    dependencies = TaskCoreProcessDependencies(
        get_strategy_func=MagicMock(return_value=strategy),
        video_task_types=set(),
        build_video_task_request_func=MagicMock(return_value=VideoTaskRequest()),
        check_concurrency_lock_func=AsyncMock(return_value=(True, "")),
        prepare_task_submission_payload_func=AsyncMock(
            return_value=SimpleNamespace(
                final_priority=7,
                saved_inputs=[],
                metadata={},
                delivery_context={},
                user_logger=SimpleNamespace(user_id=123, username="tester"),
            )
        ),
        check_and_deduct_credits_func=deduct,
        execute_task_submission_saga_func=execute,
        attach_submission_side_effects_func=AsyncMock(),
        compensate_failed_submission_func=AsyncMock(),
        release_concurrency_lock_func=AsyncMock(),
        shield_func=AsyncMock(),
        logger=MagicMock(),
    )

    await task_core.process_and_submit_task(
        user_id=123,
        username="tester",
        task_type="quick_image",
        inputs={"prompt": "hello"},
        task_id="deterministic-task",
        submission_idempotency_key="task_debit:private:1",
        submission_before_debit_func=record_cost,
        dependencies=dependencies,
    )

    assert events == [
        ("ledger_cost", 6),
        ("debit", 6, "task_debit:private:1"),
        ("dispatch", 6),
    ]


@pytest.mark.asyncio
async def test_uncertain_private_dispatch_does_not_run_saga_refund_compensation():
    strategy = MagicMock()
    strategy.get_cost.return_value = 6
    compensate = AsyncMock()
    dependencies = TaskCoreProcessDependencies(
        get_strategy_func=MagicMock(return_value=strategy),
        video_task_types=set(),
        build_video_task_request_func=MagicMock(return_value=VideoTaskRequest()),
        check_concurrency_lock_func=AsyncMock(return_value=(True, "")),
        prepare_task_submission_payload_func=AsyncMock(
            return_value=SimpleNamespace(
                final_priority=7,
                saved_inputs=["input.png"],
                metadata={},
                delivery_context={},
                user_logger=SimpleNamespace(user_id=123, username="tester"),
            )
        ),
        check_and_deduct_credits_func=AsyncMock(return_value=(True, "")),
        execute_task_submission_saga_func=AsyncMock(
            side_effect=RuntimeError("outcome uncertain")
        ),
        attach_submission_side_effects_func=AsyncMock(),
        compensate_failed_submission_func=compensate,
        release_concurrency_lock_func=AsyncMock(),
        shield_func=AsyncMock(),
        logger=MagicMock(),
    )

    with pytest.raises(CoreDomainError, match="不会重复派发或自动退款"):
        await task_core.process_and_submit_task(
            user_id=123,
            username="tester",
            task_type="quick_image",
            inputs={"prompt": "hello"},
            task_id="deterministic-task",
            submission_should_compensate_func=lambda _error: False,
            dependencies=dependencies,
        )

    compensate.assert_not_awaited()
    dependencies.release_concurrency_lock_func.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_private_submission_persists_ledger_before_idempotent_refund():
    events = []
    strategy = MagicMock()
    strategy.get_cost.return_value = 6

    async def mark_failed_before_refund(**kwargs):
        events.append(("ledger_failed", kwargs["cost"]))

    async def compensate(**kwargs):
        events.append(("refund", kwargs["refund_idempotency_key"]))

    async def shield(awaitable):
        return await awaitable

    dependencies = TaskCoreProcessDependencies(
        get_strategy_func=MagicMock(return_value=strategy),
        video_task_types=set(),
        build_video_task_request_func=MagicMock(return_value=VideoTaskRequest()),
        check_concurrency_lock_func=AsyncMock(return_value=(True, "")),
        prepare_task_submission_payload_func=AsyncMock(
            return_value=SimpleNamespace(
                final_priority=7,
                saved_inputs=["input.png"],
                metadata={},
                delivery_context={},
                user_logger=SimpleNamespace(user_id=123, username="tester"),
            )
        ),
        check_and_deduct_credits_func=AsyncMock(return_value=(True, "")),
        execute_task_submission_saga_func=AsyncMock(
            side_effect=RuntimeError("failed before dispatch")
        ),
        attach_submission_side_effects_func=AsyncMock(),
        compensate_failed_submission_func=compensate,
        release_concurrency_lock_func=AsyncMock(),
        shield_func=shield,
        logger=MagicMock(),
    )

    with pytest.raises(CoreDomainError, match="灵石已全额退还"):
        await task_core.process_and_submit_task(
            user_id=123,
            username="tester",
            task_type="quick_image",
            inputs={"prompt": "hello"},
            task_id="deterministic-task",
            submission_before_compensation_func=mark_failed_before_refund,
            submission_refund_idempotency_key=(
                "task_refund:task:deterministic-task"
            ),
            submission_refund_task_type="refund_private_submission",
            submission_release_idempotency_key=(
                "task_concurrency:deterministic-task"
            ),
            dependencies=dependencies,
        )

    assert events == [
        ("ledger_failed", 6),
        (
            "refund",
            "task_refund:task:deterministic-task",
        ),
    ]
    dependencies.release_concurrency_lock_func.assert_awaited_once_with(
        123,
        idempotency_key=(
            "task_concurrency:deterministic-task"
        ),
    )


@pytest.mark.asyncio
async def test_process_and_submit_task_merges_registry_metadata_before_registration():
    strategy = MagicMock()
    strategy.get_cost.return_value = 2
    submission_context = SimpleNamespace(
        final_priority=7,
        saved_inputs=["input.png"],
        metadata={"saved_inputs": ["input.png"]},
        user_logger=SimpleNamespace(user_id=123, username="tester"),
    )
    execute_saga = AsyncMock(
        return_value=TaskSubmissionExecutionResult(
            registry_task_id="registry-2",
            backend_task_id="backend-2",
            submission_context=submission_context,
        )
    )
    dependencies = TaskCoreProcessDependencies(
        get_strategy_func=MagicMock(return_value=strategy),
        video_task_types=set(),
        build_video_task_request_func=MagicMock(return_value=VideoTaskRequest()),
        check_concurrency_lock_func=AsyncMock(return_value=(True, "")),
        prepare_task_submission_payload_func=AsyncMock(
            return_value=submission_context
        ),
        check_and_deduct_credits_func=AsyncMock(return_value=(True, "")),
        execute_task_submission_saga_func=execute_saga,
        attach_submission_side_effects_func=AsyncMock(),
        compensate_failed_submission_func=AsyncMock(),
        release_concurrency_lock_func=AsyncMock(),
        shield_func=AsyncMock(),
        logger=MagicMock(),
    )
    recovery_metadata = {
        "_bot_task_recovery": {
            "version": 1,
            "send_result": False,
            "requires_continuation": True,
        }
    }

    await task_core.process_and_submit_task(
        user_id=123,
        username="tester",
        task_type="edit",
        inputs={"prompt": "hello"},
        task_id="registry-1",
        registry_metadata=recovery_metadata,
        dependencies=dependencies,
    )

    assert submission_context.metadata == {
        "saved_inputs": ["input.png"],
        **recovery_metadata,
    }
    assert (
        execute_saga.await_args.kwargs["submission_context"]
        is submission_context
    )


@pytest.mark.asyncio
async def test_attach_submission_side_effects_raises_domain_error_when_monitor_attach_fails():
    schedule_apply = MagicMock()

    with pytest.raises(task_core.CoreDomainError, match="后台监控挂载失败: boom"):
        await task_web_side_effects.attach_submission_side_effects(
            backend_task_id="backend-1",
            internal_user_id=1,
            username="tester",
            registry_task_id="reg-1",
            submission_context=SimpleNamespace(),
            cost=8,
            submission_side_effect_plan=TaskSubmissionSideEffectPlan(
                attach_web_monitor=True,
                source_post_id=9,
            ),
            attach_web_task_monitor_func=MagicMock(side_effect=RuntimeError("boom")),
            schedule_apply_interaction_func=schedule_apply,
            core_domain_error_cls=task_core.CoreDomainError,
        )

    schedule_apply.assert_not_called()


@pytest.mark.asyncio
async def test_runtime_default_dependencies_pass_free_edit_flag_to_dispatch(
    monkeypatch,
):
    import config

    captured = {}

    def fake_build_default_task_core_process_dependencies(**kwargs):
        return SimpleNamespace(**kwargs)

    async def fake_execute_task_submission_saga_default(**kwargs):
        captured["saga_kwargs"] = kwargs
        return TaskSubmissionExecutionResult(
            registry_task_id="registry-1",
            backend_task_id="backend-1",
            submission_context=SimpleNamespace(saved_inputs=[]),
        )

    async def fake_dispatch_to_worker(
        task_id,
        task_type,
        inputs,
        priority,
        *,
        feature_flags=None,
    ):
        captured["dispatch"] = {
            "task_id": task_id,
            "task_type": task_type,
            "inputs": inputs,
            "priority": priority,
            "feature_flags": feature_flags,
        }
        return "backend-1"

    monkeypatch.setattr(config, "ENABLE_FREE_EDIT_V2", True)
    monkeypatch.setattr(
        task_core_process_defaults,
        "build_default_task_core_process_dependencies",
        fake_build_default_task_core_process_dependencies,
    )
    monkeypatch.setattr(
        task_core_submission,
        "execute_task_submission_saga_default",
        fake_execute_task_submission_saga_default,
    )
    monkeypatch.setattr(
        task_dispatcher,
        "dispatch_to_worker",
        fake_dispatch_to_worker,
    )

    dependencies = (
        task_core_process_defaults.build_runtime_default_task_core_process_dependencies()
    )

    strategy = dependencies.get_strategy_func(MODE_PORNMASTER_FLUX2_SINGLE_EDIT)
    assert strategy.feature_flags.free_edit_v2_enabled is True

    await dependencies.execute_task_submission_saga_func(
        task_type=MODE_PORNMASTER_FLUX2_SINGLE_EDIT,
        inputs={"saved_input_images": ["ref.png"]},
        registry_task_id="registry-1",
        cost=2,
        submission_context=SimpleNamespace(),
    )
    await captured["saga_kwargs"]["dispatch_to_worker_func"](
        "registry-1",
        MODE_PORNMASTER_FLUX2_SINGLE_EDIT,
        {"saved_input_images": ["ref.png"]},
        9,
    )

    assert captured["dispatch"]["feature_flags"].free_edit_v2_enabled is True
