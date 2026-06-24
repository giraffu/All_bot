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
    assert kwargs["metadata"] == {"mode": "random_faceswap"}


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
