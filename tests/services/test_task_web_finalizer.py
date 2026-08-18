from unittest.mock import AsyncMock
from types import SimpleNamespace

import pytest

from src.services import task_web_finalizer
from src.core import gallery_core
from src.web_api.services import character_reference_service
from src.web_api.services import prompt_result_store


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


def _build_v2_dispatching_record(**kwargs) -> dict:
    record = _build_record(**kwargs)
    record.update(
        {
            "version": 2,
            "phase": "dispatching",
            "created_at": "2026-08-18T00:00:00+00:00",
            "updated_at": "2026-08-18T00:00:00+00:00",
            "not_found_count": 0,
            "first_not_found_at": None,
            "source_post_id": None,
            "apply_recorded": False,
        }
    )
    return record


@pytest.mark.asyncio
async def test_prepare_submission_intent_persists_full_context_before_dispatch(
    monkeypatch,
):
    writes = AsyncMock()
    monkeypatch.setattr(
        task_web_finalizer.redis_client,
        "add_pending_web_finalizer",
        writes,
    )
    context = task_web_finalizer.TaskSubmissionContext(
        task_type="txt2img",
        is_video_task=False,
        user_logger=SimpleNamespace(user_id=123, username="tester"),
        prompt="moonlit courtyard",
        saved_inputs=["123/input_images/source.png"],
        metadata={},
        allow_contribute=True,
        final_priority=3,
    )

    await task_web_finalizer.prepare_web_submission_intent(
        internal_user_id=123,
        username="tester",
        registry_task_id="registry-1",
        submission_context=context,
        cost=8,
        source_post_id=99,
    )

    assert writes.await_count == 2
    prepared = writes.await_args_list[0].args[1]
    dispatching = writes.await_args_list[1].args[1]
    assert prepared["version"] == 2
    assert prepared["phase"] == "prepared"
    assert prepared["backend_task_id"] == "registry-1"
    assert prepared["submission_context"]["saved_inputs"] == [
        "123/input_images/source.png"
    ]
    assert prepared["source_post_id"] == 99
    assert dispatching["phase"] == "dispatching"


@pytest.mark.asyncio
async def test_accepting_intent_records_apply_once(monkeypatch):
    current = _build_v2_dispatching_record()
    current["source_post_id"] = 99
    apply_interaction = AsyncMock()

    async def persist(_task_id, next_record):
        nonlocal current
        current = next_record

    monkeypatch.setattr(
        task_web_finalizer.redis_client,
        "get_pending_web_finalizer",
        AsyncMock(side_effect=lambda _task_id: current),
    )
    monkeypatch.setattr(
        task_web_finalizer.redis_client,
        "add_pending_web_finalizer",
        AsyncMock(side_effect=persist),
    )
    monkeypatch.setattr(gallery_core, "record_apply_interaction", apply_interaction)
    context = task_web_finalizer._deserialize_submission_context(
        internal_user_id=123,
        username="tester",
        payload=current["submission_context"],
    )

    for _ in range(2):
        await task_web_finalizer.enqueue_pending_web_finalizer(
            backend_task_id="registry-1",
            internal_user_id=123,
            username="tester",
            registry_task_id="registry-1",
            submission_context=context,
            cost=8,
            source_post_id=99,
        )

    apply_interaction.assert_awaited_once_with(123, 99)
    assert current["phase"] == "accepted"
    assert current["apply_recorded"] is True


def _build_free_edit_v3_record(*, stage: str = "bf16") -> dict:
    record = _build_record(
        registry_task_id="logical-v3",
        backend_task_id=("stage1-v3" if stage == "bf16" else "stage2-v3"),
        cost=5,
    )
    record["submission_context"].update(
        {
            "task_type": "pornmaster_flux2_edit_bf16",
            "prompt": "preserve composition",
            "saved_inputs": ["123/input_images/original.png"],
            "metadata": {"_web_free_edit_v3": {"kind": "free_edit_v3"}},
        }
    )
    record["continuation"] = {
        "version": 1,
        "kind": "free_edit_v3",
        "stage": stage,
        "stage2_task_type": "face_swap_v2",
        "stage2_backend_task_id": "stage2-v3",
        "original_image": "123/input_images/original.png",
        "stage1_result_path": (
            "123/output_images/stage1.png" if stage != "bf16" else None
        ),
        "final_allow_contribute": True,
    }
    return record


def _build_scail2_face_swap_record(*, stage: str = "face_swap_v2") -> dict:
    record = _build_record(
        registry_task_id="logical-video",
        backend_task_id=(
            "logical-video" if stage == "face_swap_v2" else "stage2-video"
        ),
        cost=40,
    )
    record["submission_context"].update(
        {
            "task_type": "scail2_face_swap_v2",
            "is_video_task": True,
            "prompt": "keep original scene",
            "saved_inputs": [
                "123/input_images/reference.png",
                "123/input_images/motion.mp4",
            ],
            "metadata": {},
            "final_priority": 7,
            "video_request": {
                "requested_duration": 5,
                "billing_resolution": "512x896",
            },
        }
    )
    record["continuation"] = {
        "version": 1,
        "kind": "scail2_face_swap_v2",
        "stage": stage,
        "stage2_backend_task_id": "stage2-video",
        "original_reference": "123/input_images/reference.png",
        "motion_video": "123/input_images/motion.mp4",
        "duration": 5,
        "normal_priority": 7,
        "stage1_result_path": (
            "123/output_images/swapped-first-frame.png"
            if stage != "face_swap_v2"
            else None
        ),
        "final_allow_contribute": True,
    }
    return record


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
async def test_v2_intent_requires_three_not_found_observations_over_sixty_seconds(
    monkeypatch,
):
    current = {"record": _build_v2_dispatching_record(cost=13)}
    persisted = []
    cancellation = AsyncMock()
    remove = AsyncMock()
    _mock_finalizer_lock(monkeypatch)
    monkeypatch.setattr(
        task_web_finalizer.redis_client,
        "get_pending_web_finalizer",
        AsyncMock(side_effect=lambda _task_id: current["record"]),
    )

    async def persist(_task_id, next_record):
        current["record"] = next_record
        persisted.append(next_record.copy())

    monkeypatch.setattr(
        task_web_finalizer.redis_client,
        "add_pending_web_finalizer",
        AsyncMock(side_effect=persist),
    )
    monkeypatch.setattr(
        task_web_finalizer.image_service,
        "get_task_status",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        task_web_finalizer,
        "finalize_monitored_web_task_cancellation_default",
        cancellation,
    )
    monkeypatch.setattr(
        task_web_finalizer.redis_client,
        "remove_pending_web_finalizer",
        remove,
    )
    timestamps = iter([1000.0, 1030.0, 1061.0])
    monkeypatch.setattr(task_web_finalizer, "_now_timestamp", lambda: next(timestamps))

    assert await task_web_finalizer.process_pending_web_finalizer("registry-1") is False
    assert await task_web_finalizer.process_pending_web_finalizer("registry-1") is False
    assert await task_web_finalizer.process_pending_web_finalizer("registry-1") is True

    assert [item["not_found_count"] for item in persisted[:3]] == [1, 2, 3]
    assert persisted[-1]["phase"] == "terminal"
    cancellation.assert_awaited_once()
    remove.assert_awaited_once_with("registry-1")


@pytest.mark.asyncio
async def test_v2_intent_does_not_count_central_transport_failure_as_not_found(
    monkeypatch,
):
    record = _build_v2_dispatching_record()
    record["created_at"] = task_web_finalizer._now_iso()
    persist = AsyncMock()
    _mock_finalizer_lock(monkeypatch)
    _mock_pending_record(monkeypatch, record)
    monkeypatch.setattr(
        task_web_finalizer.redis_client,
        "add_pending_web_finalizer",
        persist,
    )
    monkeypatch.setattr(
        task_web_finalizer.image_service,
        "get_task_status",
        AsyncMock(side_effect=TimeoutError("central timed out")),
    )

    with pytest.raises(TimeoutError, match="central timed out"):
        await task_web_finalizer.process_pending_web_finalizer("registry-1")

    persist.assert_not_awaited()
    assert record["not_found_count"] == 0


@pytest.mark.asyncio
async def test_stale_uncertain_intent_alerts_without_refund(monkeypatch):
    record = _build_v2_dispatching_record()
    record["created_at"] = "1970-01-01T00:00:00+00:00"
    persist = AsyncMock()
    cancellation = AsyncMock()
    _mock_finalizer_lock(monkeypatch)
    _mock_pending_record(monkeypatch, record)
    monkeypatch.setattr(
        task_web_finalizer.redis_client,
        "add_pending_web_finalizer",
        persist,
    )
    monkeypatch.setattr(
        task_web_finalizer.image_service,
        "get_task_status",
        AsyncMock(side_effect=TimeoutError("central timed out")),
    )
    monkeypatch.setattr(
        task_web_finalizer,
        "finalize_monitored_web_task_cancellation_default",
        cancellation,
    )

    with pytest.raises(TimeoutError):
        await task_web_finalizer.process_pending_web_finalizer("registry-1")

    alerted = persist.await_args.args[1]
    assert alerted["phase"] == "reconciling"
    assert alerted["uncertain_alerted_at"]
    cancellation.assert_not_awaited()


@pytest.mark.asyncio
async def test_standard_free_edit_terminal_updates_character_view_from_metadata(
    monkeypatch,
):
    record = _build_record(registry_task_id="character-view-task")
    record["submission_context"]["task_type"] = "free_edit_v2_5"
    record["submission_context"]["metadata"] = {
        "_character_reference_view": {
            "version": 1,
            "character_id": "character-1",
            "view_type": "face_side",
        },
        "record_history": False,
    }
    finalize_character = AsyncMock()
    monkeypatch.setattr(
        character_reference_service,
        "finalize_character_reference",
        finalize_character,
    )
    monkeypatch.setattr(
        task_web_finalizer,
        "route_backend_terminal_snapshot",
        AsyncMock(),
    )

    await task_web_finalizer._finalize_terminal_record(
        record,
        {
            "status": "done",
            "result_path": "bot-data/character-views/side.png",
        },
    )

    finalize_character.assert_awaited_once_with(
        task_id="character-view-task",
        status="done",
        result_path="bot-data/character-views/side.png",
    )


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
async def test_prompt_optimizer_text_result_is_stored_without_media_path(monkeypatch):
    record = _build_record(
        registry_task_id="prompt-task",
        backend_task_id="prompt-task",
        cost=1,
    )
    optimizer_metadata = {
        "profile_ref": "ltx_eros_v14_i2v@1",
        "template_ref": "ltx_scene_script_cinematic@1",
        "allowed_output_fields": ["positive_prompt"],
    }
    record["submission_context"].update(
        {
            "task_type": "prompt_optimize",
            "metadata": {"_prompt_optimizer": optimizer_metadata},
        }
    )
    result_meta = {
        "prompt_optimizer": {
            "schema_version": "allbot.prompt_optimizer.v1",
            "profile_ref": optimizer_metadata["profile_ref"],
            "template_ref": optimizer_metadata["template_ref"],
            "primary_field": "positive_prompt",
            "optimized_fields": {"positive_prompt": "optimized prompt"},
            "warnings": [],
        }
    }
    _mock_finalizer_lock(monkeypatch)
    _mock_pending_record(monkeypatch, record)
    monkeypatch.setattr(
        task_web_finalizer.image_service,
        "get_task_status",
        AsyncMock(
            return_value={
                "status": "done",
                "result_kind": "text",
                "result_text": "optimized prompt",
                "result_meta": result_meta,
            }
        ),
    )
    monkeypatch.setattr(
        task_web_finalizer,
        "_deserialize_submission_context",
        lambda **_kwargs: SimpleNamespace(
            metadata={"_prompt_optimizer": optimizer_metadata}
        ),
    )
    store_result = AsyncMock()
    monkeypatch.setattr(prompt_result_store, "store_prompt_result", store_result)
    cleanup = AsyncMock()
    monkeypatch.setattr(task_web_finalizer, "cleanup_task_runtime_state", cleanup)
    remove = AsyncMock()
    monkeypatch.setattr(
        task_web_finalizer.redis_client,
        "remove_pending_web_finalizer",
        remove,
    )

    finalized = await task_web_finalizer.process_pending_web_finalizer("prompt-task")

    assert finalized is True
    store_result.assert_awaited_once_with(
        task_id="prompt-task",
        user_id=123,
        task_type="prompt_optimize",
        result_kind="text",
        result_text="optimized prompt",
        result_meta=result_meta,
        expected_optimizer_metadata=optimizer_metadata,
    )
    cleanup.assert_awaited_once_with(
        internal_user_id=123,
        registry_task_id="prompt-task",
    )
    remove.assert_awaited_once_with("prompt-task")


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
async def test_process_all_pending_web_finalizers_handles_recovered_records(
    monkeypatch,
):
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
        AsyncMock(
            side_effect=lambda registry_task_id: pending_records.get(registry_task_id)
        ),
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


@pytest.mark.asyncio
async def test_free_edit_v3_stage1_success_dispatches_face_swap_once(monkeypatch):
    record = _build_free_edit_v3_record()
    _mock_finalizer_lock(monkeypatch)
    _mock_pending_record(monkeypatch, record)
    add_record = AsyncMock()
    transition_registry = AsyncMock()
    submit_face_swap = AsyncMock(return_value="stage2-v3")

    monkeypatch.setattr(
        task_web_finalizer.image_service,
        "get_task_status",
        AsyncMock(
            side_effect=[
                {
                    "status": "done",
                    "result_path": "123/output_images/stage1.png",
                },
                None,
            ]
        ),
    )
    monkeypatch.setattr(
        task_web_finalizer.image_service,
        "submit_face_swap_task",
        submit_face_swap,
    )
    monkeypatch.setattr(
        task_web_finalizer.redis_client,
        "add_pending_web_finalizer",
        add_record,
    )
    monkeypatch.setattr(
        task_web_finalizer.TaskRegistry,
        "transition_backend_task",
        transition_registry,
    )

    finalized = await task_web_finalizer.process_pending_web_finalizer("logical-v3")

    assert finalized is True
    submit_face_swap.assert_awaited_once_with(
        "stage2-v3",
        face_image_path="123/input_images/original.png",
        body_image_path="123/output_images/stage1.png",
        priority=100,
        task_type="face_swap_v2",
    )
    transition_registry.assert_awaited_once_with(
        "logical-v3",
        backend_task_id="stage2-v3",
        task_type="pornmaster_flux2_edit_bf16",
        saved_input_images=["123/input_images/original.png"],
        allow_contribute=True,
        user_cancel_allowed=False,
        status="pending",
    )
    persisted = add_record.await_args_list[-1].args[1]
    assert persisted["backend_task_id"] == "stage2-v3"
    assert persisted["continuation"]["stage"] == "face_swap"
    assert persisted["continuation"]["stage2_task_type"] == "face_swap_v2"
    assert persisted["submission_context"]["allow_contribute"] is True
    assert "_web_free_edit_v3" not in persisted["submission_context"]["metadata"]


@pytest.mark.asyncio
async def test_free_edit_v3_dispatching_recovery_reuses_existing_stage2(monkeypatch):
    record = _build_free_edit_v3_record(stage="face_swap_dispatching")
    _mock_finalizer_lock(monkeypatch)
    _mock_pending_record(monkeypatch, record)
    add_record = AsyncMock()
    submit_face_swap = AsyncMock()

    monkeypatch.setattr(
        task_web_finalizer.image_service,
        "get_task_status",
        AsyncMock(return_value={"status": "running"}),
    )
    monkeypatch.setattr(
        task_web_finalizer.image_service,
        "submit_face_swap_task",
        submit_face_swap,
    )
    monkeypatch.setattr(
        task_web_finalizer.redis_client,
        "add_pending_web_finalizer",
        add_record,
    )
    monkeypatch.setattr(
        task_web_finalizer.TaskRegistry,
        "transition_backend_task",
        AsyncMock(),
    )

    finalized = await task_web_finalizer.process_pending_web_finalizer("logical-v3")

    assert finalized is True
    submit_face_swap.assert_not_awaited()
    assert add_record.await_args.args[1]["continuation"]["stage"] == "face_swap"


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy_stage2_task_type", [None, "face_swap"])
async def test_free_edit_v3_legacy_continuation_defaults_stage2_to_v2(
    monkeypatch,
    legacy_stage2_task_type,
):
    record = _build_free_edit_v3_record()
    if legacy_stage2_task_type is None:
        record["continuation"].pop("stage2_task_type")
    else:
        record["continuation"]["stage2_task_type"] = legacy_stage2_task_type
    _mock_finalizer_lock(monkeypatch)
    _mock_pending_record(monkeypatch, record)
    submit_face_swap = AsyncMock(return_value="stage2-v3")

    monkeypatch.setattr(
        task_web_finalizer.image_service,
        "get_task_status",
        AsyncMock(
            side_effect=[
                {"status": "done", "result_path": "123/output_images/stage1.png"},
                None,
            ]
        ),
    )
    monkeypatch.setattr(
        task_web_finalizer.image_service,
        "submit_face_swap_task",
        submit_face_swap,
    )
    monkeypatch.setattr(
        task_web_finalizer.redis_client,
        "add_pending_web_finalizer",
        AsyncMock(),
    )
    monkeypatch.setattr(
        task_web_finalizer.TaskRegistry,
        "transition_backend_task",
        AsyncMock(),
    )

    assert await task_web_finalizer.process_pending_web_finalizer("logical-v3") is True
    assert submit_face_swap.await_args.kwargs["task_type"] == "face_swap_v2"


@pytest.mark.asyncio
async def test_free_edit_v3_stage1_without_result_refunds_root_task(monkeypatch):
    record = _build_free_edit_v3_record()
    _mock_finalizer_lock(monkeypatch)
    _mock_pending_record(monkeypatch, record)
    failure = AsyncMock()
    remove = AsyncMock()
    monkeypatch.setattr(
        task_web_finalizer.image_service,
        "get_task_status",
        AsyncMock(return_value={"status": "done", "result_path": None}),
    )
    monkeypatch.setattr(
        task_web_finalizer,
        "finalize_monitored_web_task_failure_default",
        failure,
    )
    monkeypatch.setattr(
        task_web_finalizer.redis_client,
        "remove_pending_web_finalizer",
        remove,
    )

    assert await task_web_finalizer.process_pending_web_finalizer("logical-v3") is True
    failure.assert_awaited_once_with(
        internal_user_id=123,
        username="tester",
        cost=5,
        registry_task_id="logical-v3",
        final_status="error",
        logger_override=task_web_finalizer.logger,
    )
    remove.assert_awaited_once_with("logical-v3")


@pytest.mark.asyncio
async def test_scail2_face_swap_stage2_uses_normal_priority_and_preprocessed_contract(
    monkeypatch,
):
    record = _build_scail2_face_swap_record()
    _mock_finalizer_lock(monkeypatch)
    _mock_pending_record(monkeypatch, record)
    add_record = AsyncMock()
    transition_registry = AsyncMock()
    submit_scail2 = AsyncMock(return_value="stage2-video")
    monkeypatch.setattr(
        task_web_finalizer.image_service,
        "get_task_status",
        AsyncMock(
            side_effect=[
                {
                    "status": "done",
                    "result_path": "123/output_images/swapped-first-frame.png",
                },
                None,
            ]
        ),
    )
    monkeypatch.setattr(
        task_web_finalizer.image_service,
        "submit_scail2_video_task",
        submit_scail2,
    )
    monkeypatch.setattr(
        task_web_finalizer.redis_client,
        "add_pending_web_finalizer",
        add_record,
    )
    monkeypatch.setattr(
        task_web_finalizer.TaskRegistry,
        "transition_backend_task",
        transition_registry,
    )

    assert (
        await task_web_finalizer.process_pending_web_finalizer("logical-video") is True
    )
    submit_scail2.assert_awaited_once_with(
        "stage2-video",
        task_type="scail2_face_swap_v2",
        reference_image_path="123/output_images/swapped-first-frame.png",
        motion_video_path="123/input_images/motion.mp4",
        prompt="keep original scene",
        negative_prompt=" ",
        length=5,
        priority=7,
        reference_preprocessed=True,
    )
    transition_registry.assert_awaited_once_with(
        "logical-video",
        backend_task_id="stage2-video",
        task_type="scail2_face_swap_v2",
        saved_input_images=[
            "123/input_images/reference.png",
            "123/input_images/motion.mp4",
        ],
        allow_contribute=True,
        user_cancel_allowed=False,
        status="pending",
    )
    assert add_record.await_args_list[-1].args[1]["continuation"]["stage"] == ("scail2")
