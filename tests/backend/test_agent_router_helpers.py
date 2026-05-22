from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.agent_router_helpers import (
    check_task_payload,
    parse_allowed_types,
    pop_task_payload,
    task_heartbeat_payload,
    update_status_payload,
    verify_agent_token,
)


def test_parse_allowed_types_trims_csv_values():
    assert parse_allowed_types(None) is None
    assert parse_allowed_types("img2img, face_swap") == ["img2img", "face_swap"]


@pytest.mark.asyncio
async def test_pop_task_payload_returns_missing_message_when_task_details_absent():
    queue_manager = SimpleNamespace(
        dequeue_task=AsyncMock(return_value=("task-1", 1.0)),
        get_task_status=AsyncMock(return_value=None),
    )

    payload = await pop_task_payload(types="img2img", queue_manager=queue_manager)

    assert payload == {"task": None, "message": "Task details not found"}
    queue_manager.dequeue_task.assert_awaited_once_with(allowed_types=["img2img"])


@pytest.mark.asyncio
async def test_check_task_payload_raises_when_task_missing():
    queue_manager = SimpleNamespace(get_task_status=AsyncMock(return_value=None))

    with pytest.raises(HTTPException) as exc_info:
        await check_task_payload(task_id="task-1", queue_manager=queue_manager)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Task not found"


@pytest.mark.asyncio
async def test_update_status_payload_clears_current_task_and_fails_task():
    redis = SimpleNamespace(
        hset=AsyncMock(),
        hdel=AsyncMock(),
    )
    queue_manager = SimpleNamespace(
        redis=redis,
        update_task_heartbeat=AsyncMock(),
        update_progress=AsyncMock(),
        fail_task=AsyncMock(),
    )
    req = SimpleNamespace(
        task_id="task-1",
        agent_id="agent-1",
        status="failed",
        progress=0.0,
        error="boom",
    )

    payload = await update_status_payload(req=req, queue_manager=queue_manager)

    assert payload == {"status": "ok"}
    redis.hset.assert_any_await("comfy:task:task-1", "worker_id", "agent-1")
    redis.hset.assert_any_await(
        "comfy:agent:heartbeat:agent-1", "current_task_id", "task-1"
    )
    redis.hdel.assert_awaited_once_with(
        "comfy:agent:heartbeat:agent-1",
        "current_task_id",
    )
    queue_manager.fail_task.assert_awaited_once_with("task-1", "boom")


@pytest.mark.asyncio
async def test_task_heartbeat_payload_binds_agent_when_present():
    redis = SimpleNamespace(
        hset=AsyncMock(),
        hdel=AsyncMock(),
    )
    queue_manager = SimpleNamespace(
        redis=redis,
        update_task_heartbeat=AsyncMock(),
    )
    req = SimpleNamespace(task_id="task-1", agent_id="agent-1")

    payload = await task_heartbeat_payload(req=req, queue_manager=queue_manager)

    assert payload == {"status": "ok"}
    queue_manager.update_task_heartbeat.assert_awaited_once_with("task-1")
    redis.hset.assert_any_await("comfy:task:task-1", "worker_id", "agent-1")
    redis.hset.assert_any_await(
        "comfy:agent:heartbeat:agent-1", "current_task_id", "task-1"
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
