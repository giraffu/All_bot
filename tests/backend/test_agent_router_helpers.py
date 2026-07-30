from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, status

from app.agent_router_helpers import (
    check_task_payload,
    complete_task_payload,
    get_agent_control_payload,
    heartbeat_payload,
    parse_allowed_types,
    peek_task_payload,
    pop_task_payload,
    set_agent_control_payload,
    task_heartbeat_payload,
    update_status_payload,
    verify_agent_token,
)
from app.routers.agent import HeartbeatRequest


def test_parse_allowed_types_trims_csv_values():
    assert parse_allowed_types(None) is None
    assert parse_allowed_types("img2img, face_swap") == ["img2img", "face_swap"]
    assert parse_allowed_types(" , ") is None


def test_heartbeat_request_accepts_legacy_empty_numeric_health_fields():
    request = HeartbeatRequest(
        agent_id="agent-1",
        types="img2img",
        status="idle",
        last_error_at="",
        quarantined_until="",
    )

    assert request.last_error_at == ""
    assert request.quarantined_until == ""


def test_heartbeat_request_accepts_pool_bundle_versions_json_string():
    request = HeartbeatRequest(
        agent_id="agent-1",
        types="wan22_video_v2",
        model_bundle_versions='{"wan22_video_v2_baseline":"2026-06-10"}',
    )

    assert request.model_bundle_versions == '{"wan22_video_v2_baseline":"2026-06-10"}'


@pytest.mark.asyncio
async def test_pop_task_payload_returns_missing_message_when_task_details_absent():
    queue_manager = SimpleNamespace(
        dequeue_task=AsyncMock(return_value=("task-1", 1.0)),
        get_task_status=AsyncMock(return_value=None),
    )

    payload = await pop_task_payload(
        types="img2img",
        queue_manager=queue_manager,
        cancel_lock=True,
    )

    assert payload == {"task": None, "message": "Task details not found"}
    queue_manager.dequeue_task.assert_awaited_once_with(
        allowed_types=["img2img"],
        preferred_types=None,
        cancel_lock=True,
    )


@pytest.mark.asyncio
async def test_pop_task_payload_respects_agent_draining_state():
    queue_manager = SimpleNamespace(
        is_agent_pop_enabled=AsyncMock(return_value=(False, "maintenance")),
        dequeue_task=AsyncMock(),
    )

    payload = await pop_task_payload(
        types="img2img",
        agent_id="agent-1",
        queue_manager=queue_manager,
    )

    assert payload == {
        "task": None,
        "message": "Agent agent-1 is not accepting new tasks: maintenance",
    }
    queue_manager.dequeue_task.assert_not_awaited()


@pytest.mark.asyncio
async def test_peek_task_payload_returns_first_pending_match_without_dequeue():
    task = {"task_id": "task-1", "type": "img2img", "status": "pending"}
    queue_manager = SimpleNamespace(peek_pending_tasks=AsyncMock(return_value=[task]))

    payload = await peek_task_payload(
        types="img2img, face_swap",
        limit=1,
        queue_manager=queue_manager,
    )

    assert payload == {"task": task}
    queue_manager.peek_pending_tasks.assert_awaited_once_with(
        allowed_types=["img2img", "face_swap"],
        preferred_types=None,
        limit=1,
    )


@pytest.mark.asyncio
async def test_peek_task_payload_returns_no_task_message_when_empty():
    queue_manager = SimpleNamespace(peek_pending_tasks=AsyncMock(return_value=[]))

    payload = await peek_task_payload(
        types=None,
        limit=0,
        queue_manager=queue_manager,
    )

    assert payload == {"task": None, "message": "No pending tasks"}
    queue_manager.peek_pending_tasks.assert_awaited_once_with(
        allowed_types=None,
        preferred_types=None,
        limit=1,
    )


@pytest.mark.asyncio
async def test_pop_task_payload_passes_valid_preferred_subset():
    queue_manager = SimpleNamespace(
        dequeue_task=AsyncMock(return_value=None),
    )

    await pop_task_payload(
        types="img2img,scail2_face_swap_v2",
        preferred_types="scail2_face_swap_v2",
        queue_manager=queue_manager,
    )

    queue_manager.dequeue_task.assert_awaited_once_with(
        allowed_types=["img2img", "scail2_face_swap_v2"],
        preferred_types=["scail2_face_swap_v2"],
        cancel_lock=False,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("types", "preferred_types"),
    (
        (None, "scail2_face_swap_v2"),
        ("img2img", "scail2_face_swap_v2"),
    ),
)
async def test_pop_task_payload_rejects_invalid_preferred_types(
    types,
    preferred_types,
):
    queue_manager = SimpleNamespace(dequeue_task=AsyncMock())

    with pytest.raises(HTTPException) as exc_info:
        await pop_task_payload(
            types=types,
            preferred_types=preferred_types,
            queue_manager=queue_manager,
        )

    assert exc_info.value.status_code == 422
    queue_manager.dequeue_task.assert_not_awaited()


@pytest.mark.asyncio
async def test_invalid_preferred_types_supports_pinned_starlette_status_constants(
    monkeypatch,
):
    monkeypatch.delattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", raising=False)
    queue_manager = SimpleNamespace(dequeue_task=AsyncMock())

    with pytest.raises(HTTPException) as exc_info:
        await pop_task_payload(
            types="img2img",
            preferred_types="scail2_face_swap_v2",
            queue_manager=queue_manager,
        )

    assert exc_info.value.status_code == 422
    queue_manager.dequeue_task.assert_not_awaited()


@pytest.mark.asyncio
async def test_peek_task_payload_passes_valid_preferred_subset():
    queue_manager = SimpleNamespace(peek_pending_tasks=AsyncMock(return_value=[]))

    await peek_task_payload(
        types="img2img,scail2_face_swap_v2",
        preferred_types="scail2_face_swap_v2",
        limit=1,
        queue_manager=queue_manager,
    )

    queue_manager.peek_pending_tasks.assert_awaited_once_with(
        allowed_types=["img2img", "scail2_face_swap_v2"],
        preferred_types=["scail2_face_swap_v2"],
        limit=1,
    )


@pytest.mark.asyncio
async def test_check_task_payload_raises_when_task_missing():
    queue_manager = SimpleNamespace(get_task_status=AsyncMock(return_value=None))

    with pytest.raises(HTTPException) as exc_info:
        await check_task_payload(task_id="task-1", queue_manager=queue_manager)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Task not found"


@pytest.mark.asyncio
async def test_update_status_payload_clears_current_task_and_fails_task():
    queue_manager = SimpleNamespace(
        bind_agent_task=AsyncMock(),
        record_task_worker=AsyncMock(),
        clear_agent_current_task=AsyncMock(),
        update_task_heartbeat=AsyncMock(),
        update_progress=AsyncMock(),
        fail_task=AsyncMock(),
    )
    payload = await update_status_payload(
        task_id="task-1",
        agent_id="agent-1",
        status="failed",
        progress=0.0,
        error="boom",
        queue_manager=queue_manager,
    )

    assert payload == {"status": "ok"}
    queue_manager.bind_agent_task.assert_not_awaited()
    queue_manager.record_task_worker.assert_awaited_once_with("task-1", "agent-1")
    queue_manager.clear_agent_current_task.assert_awaited_once_with(
        "agent-1",
        task_id="task-1",
    )
    queue_manager.fail_task.assert_awaited_once_with("task-1", "boom")


@pytest.mark.asyncio
async def test_update_status_payload_clears_current_task_and_cancels_task():
    queue_manager = SimpleNamespace(
        bind_agent_task=AsyncMock(),
        record_task_worker=AsyncMock(),
        clear_agent_current_task=AsyncMock(),
        update_task_heartbeat=AsyncMock(),
        update_progress=AsyncMock(),
        fail_task=AsyncMock(),
        cancel_running_task=AsyncMock(),
    )
    payload = await update_status_payload(
        task_id="task-1",
        agent_id="agent-1",
        status="cancelled",
        progress=0.0,
        error="",
        queue_manager=queue_manager,
    )

    assert payload == {"status": "ok"}
    queue_manager.bind_agent_task.assert_not_awaited()
    queue_manager.record_task_worker.assert_awaited_once_with("task-1", "agent-1")
    queue_manager.clear_agent_current_task.assert_awaited_once_with(
        "agent-1",
        task_id="task-1",
    )
    queue_manager.cancel_running_task.assert_awaited_once_with("task-1")
    queue_manager.fail_task.assert_not_awaited()


@pytest.mark.asyncio
async def test_task_heartbeat_payload_binds_agent_when_present():
    queue_manager = SimpleNamespace(
        bind_agent_task=AsyncMock(),
        update_task_heartbeat=AsyncMock(),
    )
    payload = await task_heartbeat_payload(
        task_id="task-1",
        agent_id="agent-1",
        queue_manager=queue_manager,
    )

    assert payload == {"status": "ok"}
    queue_manager.update_task_heartbeat.assert_awaited_once_with("task-1")
    queue_manager.bind_agent_task.assert_awaited_once_with("task-1", "agent-1")


@pytest.mark.asyncio
async def test_heartbeat_payload_forwards_legacy_empty_health_values():
    queue_manager = SimpleNamespace(update_agent_heartbeat=AsyncMock())

    payload = await heartbeat_payload(
        agent_id="agent-1",
        types="img2img",
        status="idle",
        health_reason="",
        last_error="",
        last_error_at="",
        consecutive_failures=0,
        quarantined_until="",
        queue_manager=queue_manager,
    )

    assert payload == {"status": "ok"}
    queue_manager.update_agent_heartbeat.assert_awaited_once_with(
        "agent-1",
        "img2img",
        "idle",
        health_reason="",
        last_error="",
        last_error_at="",
        consecutive_failures=0,
        quarantined_until="",
        metadata=None,
    )


@pytest.mark.asyncio
async def test_heartbeat_payload_forwards_gpu_pool_metadata():
    queue_manager = SimpleNamespace(update_agent_heartbeat=AsyncMock())

    payload = await heartbeat_payload(
        agent_id="agent-1",
        types="wan22_video_v2",
        status="idle",
        metadata={"node_id": "gpu-252", "gpu_index": "1", "pool_managed": "true"},
        queue_manager=queue_manager,
    )

    assert payload == {"status": "ok"}
    assert queue_manager.update_agent_heartbeat.await_args.kwargs["metadata"] == {
        "node_id": "gpu-252",
        "gpu_index": "1",
        "pool_managed": "true",
    }


@pytest.mark.asyncio
async def test_agent_control_payloads_delegate_to_queue_manager():
    queue_manager = SimpleNamespace(
        set_agent_control_state=AsyncMock(
            return_value={"agent_id": "agent-1", "state": "draining"}
        ),
        get_agent_control_state=AsyncMock(return_value={"state": "draining"}),
    )

    set_payload = await set_agent_control_payload(
        agent_id="agent-1",
        state="draining",
        reason="canary",
        ttl_seconds=60,
        queue_manager=queue_manager,
    )
    get_payload = await get_agent_control_payload(
        agent_id="agent-1",
        queue_manager=queue_manager,
    )

    assert set_payload == {"agent_id": "agent-1", "state": "draining"}
    assert get_payload == {"agent_id": "agent-1", "state": "draining"}


@pytest.mark.asyncio
async def test_update_status_payload_forwards_phase_without_setting_current():
    queue_manager = SimpleNamespace(
        bind_agent_task=AsyncMock(),
        record_task_worker=AsyncMock(),
        update_task_heartbeat=AsyncMock(),
        update_task_runtime_metadata=AsyncMock(),
    )

    payload = await update_status_payload(
        task_id="task-1",
        agent_id="agent-1",
        status="running",
        progress=0.0,
        error="",
        execution_phase="finalizing",
        cancel_locked=None,
        set_current=False,
        queue_manager=queue_manager,
    )

    assert payload == {"status": "ok"}
    queue_manager.bind_agent_task.assert_not_awaited()
    queue_manager.record_task_worker.assert_awaited_once_with("task-1", "agent-1")
    queue_manager.update_task_runtime_metadata.assert_awaited_once_with(
        "task-1",
        progress=None,
        execution_phase="finalizing",
        cancel_locked=None,
    )


@pytest.mark.asyncio
async def test_complete_task_payload_binds_agent_before_clearing_current_task():
    queue_manager = SimpleNamespace(
        bind_agent_task=AsyncMock(),
        record_task_worker=AsyncMock(),
        clear_agent_current_task=AsyncMock(),
        complete_task=AsyncMock(),
    )
    payload = await complete_task_payload(
        task_id="task-1",
        agent_id="agent-1",
        result="/tmp/result.png",
        queue_manager=queue_manager,
    )

    assert payload == {"status": "ok"}
    queue_manager.bind_agent_task.assert_not_awaited()
    queue_manager.record_task_worker.assert_awaited_once_with("task-1", "agent-1")
    queue_manager.clear_agent_current_task.assert_awaited_once_with(
        "agent-1",
        task_id="task-1",
    )
    queue_manager.complete_task.assert_awaited_once_with(
        "task-1",
        "/tmp/result.png",
        extra_outputs=None,
    )


@pytest.mark.asyncio
async def test_complete_task_payload_forwards_extra_outputs():
    queue_manager = SimpleNamespace(
        bind_agent_task=AsyncMock(),
        record_task_worker=AsyncMock(),
        clear_agent_current_task=AsyncMock(),
        complete_task=AsyncMock(),
    )
    payload = await complete_task_payload(
        task_id="task-1",
        agent_id="agent-1",
        result="/tmp/result.mp4",
        extra_outputs={"last_frame": {"path": "/tmp/last_frame.png", "media_type": "image"}},
        queue_manager=queue_manager,
    )

    assert payload == {"status": "ok"}
    queue_manager.complete_task.assert_awaited_once_with(
        "task-1",
        "/tmp/result.mp4",
        extra_outputs={"last_frame": {"path": "/tmp/last_frame.png", "media_type": "image"}},
    )


def test_verify_agent_token_checks_configuration_and_bearer_value():
    logger = MagicMock()

    with pytest.raises(HTTPException) as missing_exc:
        verify_agent_token(authorization=None, agent_token=None, logger=logger)
    assert missing_exc.value.status_code == 500

    with pytest.raises(HTTPException) as invalid_exc:
        verify_agent_token(
            authorization="Bearer wrong",
            agent_token="secret",
            logger=logger,
        )
    assert invalid_exc.value.status_code == 401

    assert (
        verify_agent_token(
            authorization="Bearer secret",
            agent_token="secret",
            logger=logger,
        )
        is True
    )
