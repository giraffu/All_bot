from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core import task_core_submission
from src.core.task_core_submission import (
    compensate_failed_submission,
    dispatch_registered_task,
    execute_task_submission_saga,
    register_task_submission,
)
from src.core.task_core_types import CoreDomainError


@pytest.mark.asyncio
async def test_dispatch_registered_task_marks_failed_and_maps_busy_error():
    dispatch_to_worker = AsyncMock(side_effect=Exception("Connection refused"))
    update_backend_task_id = AsyncMock()
    mark_task_status = AsyncMock()

    with pytest.raises(CoreDomainError, match="当前服务器繁忙，请稍后再试"):
        await dispatch_registered_task(
            registry_task_id="registry-1",
            task_type="face_swap",
            inputs={"a": 1},
            final_priority=5,
            dispatch_to_worker_func=dispatch_to_worker,
            update_backend_task_id_func=update_backend_task_id,
            mark_task_status_func=mark_task_status,
            is_task_backend_busy_error_func=lambda message: "Connection refused" in message,
            logger=SimpleNamespace(error=lambda *args, **kwargs: None),
        )

    update_backend_task_id.assert_not_called()
    mark_task_status.assert_awaited_once_with("registry-1", "failed")


@pytest.mark.asyncio
async def test_execute_task_submission_saga_returns_composed_result():
    submission_context = SimpleNamespace(
        user_logger=SimpleNamespace(user_id=42, username="tester"),
        final_priority=7,
        task_type="face_swap",
        log_prompt="prompt",
        registry_saved_inputs=lambda: [],
        is_video_task=False,
        allow_contribute=True,
        metadata={},
        client_type="bot",
    )
    register_task_submission_func = AsyncMock(return_value="registry-2")
    dispatch_registered_task_func = AsyncMock(return_value="backend-2")

    result = await execute_task_submission_saga(
        task_type="face_swap",
        inputs={"foo": "bar"},
        registry_task_id="seed-id",
        cost=10,
        submission_context=submission_context,
        register_task_submission_func=register_task_submission_func,
        dispatch_registered_task_func=dispatch_registered_task_func,
    )

    register_task_submission_func.assert_awaited_once_with(
        registry_task_id="seed-id",
        user_id=42,
        username="tester",
        cost=10,
        credits_deducted=True,
        submission_context=submission_context,
    )
    dispatch_registered_task_func.assert_awaited_once_with(
        registry_task_id="registry-2",
        task_type="face_swap",
        inputs={"foo": "bar"},
        final_priority=7,
    )
    assert result.registry_task_id == "registry-2"
    assert result.backend_task_id == "backend-2"
    assert result.submission_context is submission_context


@pytest.mark.asyncio
async def test_submission_ledger_hook_is_durable_before_external_dispatch():
    events = []
    submission_context = SimpleNamespace(
        user_logger=SimpleNamespace(user_id=42, username="tester"),
        final_priority=7,
        registry_saved_inputs=lambda: ["saved.png"],
    )

    async def register(**_kwargs):
        events.append("registered")
        return "deterministic-task"

    async def before_dispatch(**kwargs):
        events.append("ledger_dispatching")
        assert kwargs == {
            "registry_task_id": "deterministic-task",
            "task_type": "face_swap",
            "cost": 10,
            "saved_inputs": ["saved.png"],
        }

    async def dispatch(**_kwargs):
        events.append("external_dispatch")
        return "deterministic-task"

    await execute_task_submission_saga(
        task_type="face_swap",
        inputs={"foo": "bar"},
        registry_task_id="deterministic-task",
        cost=10,
        submission_context=submission_context,
        register_task_submission_func=register,
        dispatch_registered_task_func=dispatch,
        before_dispatch_func=before_dispatch,
    )

    assert events == ["registered", "ledger_dispatching", "external_dispatch"]


@pytest.mark.asyncio
async def test_register_task_submission_persists_client_type():
    add_task = AsyncMock(return_value="registry-qqcc")
    submission_context = SimpleNamespace(
        task_type="random_faceswap",
        log_prompt="prompt",
        registry_saved_inputs=lambda: ["input.jpg"],
        is_video_task=False,
        final_priority=3,
        allow_contribute=False,
        client_type="bot:qqcc",
        user_cancel_allowed=False,
        concurrency_acquisition_key="task_concurrency:registry-qqcc",
        metadata={"mode": "random_faceswap"},
    )

    result = await register_task_submission(
        registry_task_id="registry-qqcc",
        user_id=42,
        username="qqcc",
        cost=2,
        submission_context=submission_context,
        add_task_func=add_task,
    )

    assert result == "registry-qqcc"
    add_task.assert_awaited_once()
    kwargs = add_task.await_args.kwargs
    assert kwargs["client_type"] == "bot:qqcc"
    assert kwargs["user_cancel_allowed"] is False
    assert kwargs["credits_deducted"] is True
    assert kwargs["concurrency_acquisition_key"] == (
        "task_concurrency:registry-qqcc"
    )
    assert kwargs["metadata"] == {"mode": "random_faceswap"}


@pytest.mark.asyncio
async def test_register_task_submission_persists_delivery_context():
    add_task = AsyncMock(return_value="registry-bot")
    submission_context = SimpleNamespace(
        task_type="img2img_lora",
        log_prompt="prompt",
        registry_saved_inputs=lambda: ["input.jpg"],
        is_video_task=False,
        final_priority=8,
        allow_contribute=True,
        client_type="bot",
        delivery_context={"chat_id": 12345, "message_id": 678},
        metadata={},
    )

    await register_task_submission(
        registry_task_id="registry-bot",
        user_id=42,
        username="tester",
        cost=3,
        submission_context=submission_context,
        add_task_func=add_task,
    )

    kwargs = add_task.await_args.kwargs
    assert kwargs["chat_id"] == 12345
    assert kwargs["message_id"] == 678


@pytest.mark.asyncio
async def test_register_task_submission_persists_non_deducted_tasks():
    add_task = AsyncMock(return_value="registry-free")
    submission_context = SimpleNamespace(
        task_type="ltx_video",
        log_prompt="prompt",
        registry_saved_inputs=lambda: [],
        is_video_task=True,
        final_priority=3,
        allow_contribute=False,
        client_type="bot",
        metadata={},
    )

    await register_task_submission(
        registry_task_id="registry-free",
        user_id=42,
        username="free",
        cost=18,
        credits_deducted=False,
        submission_context=submission_context,
        add_task_func=add_task,
    )

    assert add_task.await_args.kwargs["credits_deducted"] is False


@pytest.mark.asyncio
async def test_compensate_failed_submission_logs_pending_refund_when_refund_fails():
    refund_credits = AsyncMock(side_effect=RuntimeError("refund boom"))
    add_pending_refund = AsyncMock()
    remove_task = AsyncMock()

    await compensate_failed_submission(
        user_id=123,
        username="tester",
        cost=20,
        error=RuntimeError("dispatch boom"),
        credits_deducted=True,
        registry_task_id="registry-3",
        refund_credits_func=refund_credits,
        add_pending_refund_func=add_pending_refund,
        remove_task_func=remove_task,
        logger=SimpleNamespace(critical=lambda *args, **kwargs: None),
    )

    add_pending_refund.assert_awaited_once_with(
        123,
        20,
        "Task Failed: dispatch boom",
        "tester",
    )
    remove_task.assert_awaited_once_with("registry-3")


@pytest.mark.asyncio
async def test_private_submission_failure_refund_uses_deterministic_idempotency_key():
    refund_credits = AsyncMock()

    await compensate_failed_submission(
        user_id=123,
        username="tester",
        cost=20,
        error=RuntimeError("dispatch boom"),
        credits_deducted=True,
        registry_task_id="deterministic-task",
        refund_credits_func=refund_credits,
        add_pending_refund_func=AsyncMock(),
        remove_task_func=AsyncMock(),
        logger=SimpleNamespace(critical=lambda *args, **kwargs: None),
        refund_idempotency_key=(
            "task_refund:submission_failed:deterministic-task"
        ),
    )

    refund_credits.assert_awaited_once_with(
        123,
        20,
        task_type="refund_saga_failed",
        username="tester",
        idempotency_key="task_refund:submission_failed:deterministic-task",
    )


@pytest.mark.asyncio
async def test_compensate_failed_submission_uses_runtime_default_shield_binding(
    monkeypatch,
):
    refund_credits = AsyncMock()
    add_pending_refund = AsyncMock()
    remove_task = AsyncMock()
    shield = MagicMock(side_effect=lambda coro: coro)

    monkeypatch.setattr(task_core_submission.asyncio, "shield", shield)

    await compensate_failed_submission(
        user_id=123,
        username="tester",
        cost=20,
        error=RuntimeError("dispatch boom"),
        credits_deducted=True,
        registry_task_id="registry-4",
        refund_credits_func=refund_credits,
        add_pending_refund_func=add_pending_refund,
        remove_task_func=remove_task,
        logger=SimpleNamespace(critical=lambda *args, **kwargs: None),
    )

    assert shield.call_count == 2
    refund_credits.assert_awaited_once_with(
        123,
        20,
        task_type="refund_saga_failed",
        username="tester",
    )
    add_pending_refund.assert_not_awaited()
    remove_task.assert_awaited_once_with("registry-4")


@pytest.mark.asyncio
async def test_execute_task_submission_saga_default_reuses_single_default_dependencies(
    monkeypatch,
):
    submission_context = SimpleNamespace(
        user_logger=SimpleNamespace(user_id=42, username="tester"),
        final_priority=7,
        task_type="face_swap",
        log_prompt="prompt",
        registry_saved_inputs=lambda: [],
        is_video_task=False,
        allow_contribute=True,
        metadata={},
        client_type="bot",
    )
    dependencies = SimpleNamespace(
        add_task_func=AsyncMock(return_value="registry-5"),
        update_backend_task_id_func=AsyncMock(),
        mark_task_status_func=AsyncMock(),
        remove_task_func=AsyncMock(),
        add_pending_refund_func=AsyncMock(),
        dispatch_to_worker_func=AsyncMock(return_value="backend-5"),
        is_task_backend_busy_error_func=lambda _message: False,
        logger=SimpleNamespace(error=lambda *args, **kwargs: None),
    )
    build_mock = MagicMock(return_value=dependencies)

    monkeypatch.setattr(
        task_core_submission,
        "build_default_task_core_submission_dependencies",
        build_mock,
    )

    result = await task_core_submission.execute_task_submission_saga_default(
        task_type="face_swap",
        inputs={"foo": "bar"},
        registry_task_id="seed-id",
        cost=10,
        submission_context=submission_context,
    )

    assert build_mock.call_count == 1
    assert result.registry_task_id == "registry-5"
    assert result.backend_task_id == "backend-5"


@pytest.mark.asyncio
async def test_execute_task_submission_saga_default_uses_custom_dispatch_func(
    monkeypatch,
):
    submission_context = SimpleNamespace(
        user_logger=SimpleNamespace(user_id=42, username="tester"),
        final_priority=7,
        task_type="pornmaster_flux2_single_edit",
        log_prompt="prompt",
        registry_saved_inputs=lambda: [],
        is_video_task=False,
        allow_contribute=True,
        metadata={},
        client_type="bot",
    )
    custom_dispatch = AsyncMock(return_value="backend-custom")
    dependencies = SimpleNamespace(
        add_task_func=AsyncMock(return_value="registry-custom"),
        update_backend_task_id_func=AsyncMock(),
        mark_task_status_func=AsyncMock(),
        remove_task_func=AsyncMock(),
        add_pending_refund_func=AsyncMock(),
        dispatch_to_worker_func=custom_dispatch,
        is_task_backend_busy_error_func=lambda _message: False,
        logger=SimpleNamespace(error=lambda *args, **kwargs: None),
    )
    build_mock = MagicMock(return_value=dependencies)

    monkeypatch.setattr(
        task_core_submission,
        "build_default_task_core_submission_dependencies",
        build_mock,
    )

    result = await task_core_submission.execute_task_submission_saga_default(
        task_type="pornmaster_flux2_single_edit",
        inputs={"saved_input_images": ["ref.png"]},
        registry_task_id="seed-id",
        cost=2,
        submission_context=submission_context,
        dispatch_to_worker_func=custom_dispatch,
    )

    assert result.backend_task_id == "backend-custom"
    assert build_mock.call_args.kwargs["dispatch_to_worker_func"] is custom_dispatch
    custom_dispatch.assert_awaited_once_with(
        "registry-custom",
        "pornmaster_flux2_single_edit",
        {"saved_input_images": ["ref.png"]},
        7,
    )
