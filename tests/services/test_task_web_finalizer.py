from unittest.mock import AsyncMock

import pytest

from src.services import task_web_finalizer


def _build_record(
    *,
    registry_task_id: str = "registry-1",
    backend_task_id: str = "backend-1",
    cost: int = 8,
) -> dict:
    return {
        "backend_task_id": backend_task_id,
        "internal_user_id": 123,
        "username": "tester",
        "registry_task_id": registry_task_id,
        "submission_context": {
            "task_type": "txt2img",
            "is_video_task": False,
            "prompt": "moonlit courtyard",
            "saved_inputs": ["input.png"],
            "metadata": {},
            "allow_contribute": True,
            "final_priority": 3,
            "video_request": {},
        },
        "cost": cost,
    }


def _mock_finalizer_lock(monkeypatch, token: str | None = "lock-token"):
    acquire_mock = AsyncMock(return_value=token)
    release_mock = AsyncMock()
    monkeypatch.setattr(
        task_web_finalizer.redis_client,
        "acquire_pending_web_finalizer_lock",
        acquire_mock,
    )
    monkeypatch.setattr(
        task_web_finalizer.redis_client,
        "release_pending_web_finalizer_lock",
        release_mock,
    )
    return acquire_mock, release_mock


def _mock_pending_record(monkeypatch, record):
    get_pending_mock = AsyncMock(return_value=record)
    monkeypatch.setattr(
        task_web_finalizer.redis_client,
        "get_pending_web_finalizer",
        get_pending_mock,
    )
    return get_pending_mock


@pytest.mark.asyncio
async def test_process_pending_web_finalizer_finalizes_done_and_removes_record(
    monkeypatch,
):
    record = _build_record()
    success_mock = AsyncMock()
    cancellation_mock = AsyncMock()
    failure_mock = AsyncMock()
    remove_mock = AsyncMock()
    context_obj = object()
    acquire_mock, release_mock = _mock_finalizer_lock(monkeypatch)
    _mock_pending_record(monkeypatch, record)

    async def _get_status(_backend_task_id):
        return {
            "status": "done",
            "result_path": "bot-data/history/task-1/output.png",
            "extra_outputs": {"last_frame": "bot-data/history/task-1/last.png"},
        }

    monkeypatch.setattr(
        task_web_finalizer.image_service,
        "get_task_status",
        AsyncMock(side_effect=_get_status),
    )
    monkeypatch.setattr(
        task_web_finalizer,
        "_deserialize_submission_context",
        lambda **_kwargs: context_obj,
    )
    monkeypatch.setattr(
        task_web_finalizer,
        "finalize_monitored_web_task_success_default",
        success_mock,
    )
    monkeypatch.setattr(
        task_web_finalizer,
        "finalize_monitored_web_task_cancellation_default",
        cancellation_mock,
    )
    monkeypatch.setattr(
        task_web_finalizer,
        "finalize_monitored_web_task_failure_default",
        failure_mock,
    )
    monkeypatch.setattr(
        task_web_finalizer.redis_client,
        "remove_pending_web_finalizer",
        remove_mock,
    )

    finalized = await task_web_finalizer.process_pending_web_finalizer(
        "registry-1",
        record=record,
    )

    assert finalized is True
    acquire_mock.assert_awaited_once_with("registry-1")
    success_mock.assert_awaited_once_with(
        backend_task_id="backend-1",
        internal_user_id=123,
        username="tester",
        registry_task_id="registry-1",
        submission_context=context_obj,
        result_path="bot-data/history/task-1/output.png",
        extra_outputs={"last_frame": "bot-data/history/task-1/last.png"},
        logger_override=task_web_finalizer.logger,
    )
    cancellation_mock.assert_not_awaited()
    failure_mock.assert_not_awaited()
    remove_mock.assert_awaited_once_with("registry-1")
    release_mock.assert_awaited_once_with("registry-1", "lock-token")


@pytest.mark.asyncio
async def test_process_pending_web_finalizer_finalizes_error_and_removes_record(
    monkeypatch,
):
    record = _build_record(cost=11)
    failure_mock = AsyncMock()
    remove_mock = AsyncMock()
    _, release_mock = _mock_finalizer_lock(monkeypatch)
    _mock_pending_record(monkeypatch, record)

    monkeypatch.setattr(
        task_web_finalizer.image_service,
        "get_task_status",
        AsyncMock(return_value={"status": "error", "error_msg": "worker failed"}),
    )
    monkeypatch.setattr(
        task_web_finalizer,
        "finalize_monitored_web_task_failure_default",
        failure_mock,
    )
    monkeypatch.setattr(
        task_web_finalizer,
        "finalize_monitored_web_task_success_default",
        AsyncMock(),
    )
    monkeypatch.setattr(
        task_web_finalizer,
        "finalize_monitored_web_task_cancellation_default",
        AsyncMock(),
    )
    monkeypatch.setattr(
        task_web_finalizer.redis_client,
        "remove_pending_web_finalizer",
        remove_mock,
    )

    finalized = await task_web_finalizer.process_pending_web_finalizer(
        "registry-1",
        record=record,
    )

    assert finalized is True
    failure_mock.assert_awaited_once_with(
        internal_user_id=123,
        username="tester",
        cost=11,
        registry_task_id="registry-1",
        final_status="error",
        logger_override=task_web_finalizer.logger,
    )
    remove_mock.assert_awaited_once_with("registry-1")
    release_mock.assert_awaited_once_with("registry-1", "lock-token")


@pytest.mark.asyncio
async def test_process_pending_web_finalizer_finalizes_cancelled_and_removes_record(
    monkeypatch,
):
    record = _build_record(cost=5)
    cancellation_mock = AsyncMock()
    remove_mock = AsyncMock()
    _, release_mock = _mock_finalizer_lock(monkeypatch)
    _mock_pending_record(monkeypatch, record)

    monkeypatch.setattr(
        task_web_finalizer.image_service,
        "get_task_status",
        AsyncMock(return_value={"status": "cancelled"}),
    )
    monkeypatch.setattr(
        task_web_finalizer,
        "finalize_monitored_web_task_success_default",
        AsyncMock(),
    )
    monkeypatch.setattr(
        task_web_finalizer,
        "finalize_monitored_web_task_failure_default",
        AsyncMock(),
    )
    monkeypatch.setattr(
        task_web_finalizer,
        "finalize_monitored_web_task_cancellation_default",
        cancellation_mock,
    )
    monkeypatch.setattr(
        task_web_finalizer.redis_client,
        "remove_pending_web_finalizer",
        remove_mock,
    )

    finalized = await task_web_finalizer.process_pending_web_finalizer(
        "registry-1",
        record=record,
    )

    assert finalized is True
    cancellation_mock.assert_awaited_once_with(
        internal_user_id=123,
        username="tester",
        cost=5,
        registry_task_id="registry-1",
        logger_override=task_web_finalizer.logger,
    )
    remove_mock.assert_awaited_once_with("registry-1")
    release_mock.assert_awaited_once_with("registry-1", "lock-token")


@pytest.mark.asyncio
async def test_process_pending_web_finalizer_treats_backend_not_found_as_cancelled(
    monkeypatch,
):
    record = _build_record(cost=13)
    cancellation_mock = AsyncMock()
    remove_mock = AsyncMock()
    _, release_mock = _mock_finalizer_lock(monkeypatch)
    _mock_pending_record(monkeypatch, record)

    monkeypatch.setattr(
        task_web_finalizer.image_service,
        "get_task_status",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        task_web_finalizer,
        "finalize_monitored_web_task_success_default",
        AsyncMock(),
    )
    monkeypatch.setattr(
        task_web_finalizer,
        "finalize_monitored_web_task_failure_default",
        AsyncMock(),
    )
    monkeypatch.setattr(
        task_web_finalizer,
        "finalize_monitored_web_task_cancellation_default",
        cancellation_mock,
    )
    monkeypatch.setattr(
        task_web_finalizer.redis_client,
        "remove_pending_web_finalizer",
        remove_mock,
    )

    finalized = await task_web_finalizer.process_pending_web_finalizer(
        "registry-1",
        record=record,
    )

    assert finalized is True
    cancellation_mock.assert_awaited_once_with(
        internal_user_id=123,
        username="tester",
        cost=13,
        registry_task_id="registry-1",
        logger_override=task_web_finalizer.logger,
    )
    remove_mock.assert_awaited_once_with("registry-1")
    release_mock.assert_awaited_once_with("registry-1", "lock-token")


@pytest.mark.asyncio
async def test_process_pending_web_finalizer_skips_when_lock_is_already_claimed(
    monkeypatch,
):
    acquire_mock, release_mock = _mock_finalizer_lock(monkeypatch, token=None)
    get_status_mock = AsyncMock()

    monkeypatch.setattr(
        task_web_finalizer.image_service,
        "get_task_status",
        get_status_mock,
    )

    finalized = await task_web_finalizer.process_pending_web_finalizer(
        "registry-1",
        record=_build_record(),
    )

    assert finalized is False
    acquire_mock.assert_awaited_once_with("registry-1")
    get_status_mock.assert_not_awaited()
    release_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_all_pending_web_finalizers_handles_recovered_records(monkeypatch):
    pending_records = {
        "registry-done": _build_record(
            registry_task_id="registry-done",
            backend_task_id="backend-done",
        ),
        "registry-running": _build_record(
            registry_task_id="registry-running",
            backend_task_id="backend-running",
        ),
    }
    success_mock = AsyncMock()
    remove_mock = AsyncMock()
    context_obj = object()
    acquire_mock, release_mock = _mock_finalizer_lock(monkeypatch)

    async def _get_status(backend_task_id: str):
        if backend_task_id == "backend-done":
            return {
                "status": "done",
                "result_path": "bot-data/history/task-done/output.png",
            }
        return {"status": "running"}

    monkeypatch.setattr(
        task_web_finalizer.redis_client,
        "get_pending_web_finalizers",
        AsyncMock(return_value=pending_records),
    )
    monkeypatch.setattr(
        task_web_finalizer.redis_client,
        "get_pending_web_finalizer",
        AsyncMock(side_effect=lambda registry_task_id: pending_records.get(registry_task_id)),
    )
    monkeypatch.setattr(
        task_web_finalizer.image_service,
        "get_task_status",
        AsyncMock(side_effect=_get_status),
    )
    monkeypatch.setattr(
        task_web_finalizer,
        "_deserialize_submission_context",
        lambda **_kwargs: context_obj,
    )
    monkeypatch.setattr(
        task_web_finalizer,
        "finalize_monitored_web_task_success_default",
        success_mock,
    )
    monkeypatch.setattr(
        task_web_finalizer,
        "finalize_monitored_web_task_failure_default",
        AsyncMock(),
    )
    monkeypatch.setattr(
        task_web_finalizer,
        "finalize_monitored_web_task_cancellation_default",
        AsyncMock(),
    )
    monkeypatch.setattr(
        task_web_finalizer.redis_client,
        "remove_pending_web_finalizer",
        remove_mock,
    )

    finalized_count = await task_web_finalizer.process_all_pending_web_finalizers()

    assert finalized_count == 1
    assert acquire_mock.await_count == 2
    success_mock.assert_awaited_once()
    remove_mock.assert_awaited_once_with("registry-done")
    assert release_mock.await_count == 2


@pytest.mark.asyncio
async def test_process_pending_web_finalizer_skips_stale_snapshot_after_lock(
    monkeypatch,
):
    stale_record = _build_record()
    get_pending_mock = _mock_pending_record(monkeypatch, None)
    get_status_mock = AsyncMock()
    acquire_mock, release_mock = _mock_finalizer_lock(monkeypatch)

    monkeypatch.setattr(
        task_web_finalizer.image_service,
        "get_task_status",
        get_status_mock,
    )

    finalized = await task_web_finalizer.process_pending_web_finalizer(
        "registry-1",
        record=stale_record,
    )

    assert finalized is False
    acquire_mock.assert_awaited_once_with("registry-1")
    get_pending_mock.assert_awaited_once_with("registry-1")
    get_status_mock.assert_not_awaited()
    release_mock.assert_awaited_once_with("registry-1", "lock-token")
