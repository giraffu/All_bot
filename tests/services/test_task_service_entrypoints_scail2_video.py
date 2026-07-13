from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.constants import (
    MODE_SCAIL2_ACTION_TRANSFER,
    MODE_SCAIL2_ACTION_TRANSFER_LONG,
    MODE_SCAIL2_FACE_SWAP_V2,
)
from src.domain_config.scail2_video import (
    SCAIL2_DEFAULT_NEGATIVE_PROMPT,
    SCAIL2_FACE_SWAP_V2_DEFAULT_POSITIVE_PROMPT,
)
from src.services import task_service_entrypoints_specialized as entrypoints


@pytest.mark.asyncio
async def test_process_scail2_video_task_builds_bot_flow_payload(monkeypatch):
    captured = {}

    async def fake_run_bot_task_application(*, flow):
        captured["flow"] = flow
        return "ok"

    monkeypatch.setattr(
        entrypoints,
        "resolve_internal_user_id",
        AsyncMock(return_value=999),
    )
    monkeypatch.setattr(
        entrypoints,
        "get_acceleration_notice",
        AsyncMock(return_value=""),
    )
    monkeypatch.setattr(
        entrypoints,
        "run_bot_task_application",
        fake_run_bot_task_application,
    )

    context = SimpleNamespace(
        t=lambda key, **kwargs: f"{key}:{kwargs}",
        user_data={},
    )

    result = await entrypoints.process_scail2_video_task(
        context=context,
        chat_id=456,
        user_id=123,
        username="tester",
        task_type=MODE_SCAIL2_ACTION_TRANSFER,
        reference_image_path="/tmp/reference.png",
        motion_video_path="/tmp/motion.mp4",
        prompt="ancient costume dancer, cinematic",
        duration=8,
        message_id=789,
    )

    assert result == "ok"
    flow = captured["flow"]
    assert flow.request.internal_user_id == 999
    assert flow.request.task_type == MODE_SCAIL2_ACTION_TRANSFER
    assert flow.request.inputs["images"] == ["/tmp/reference.png", "/tmp/motion.mp4"]
    assert flow.request.inputs["prompt"] == "ancient costume dancer, cinematic"
    assert flow.request.inputs["duration"] == 8
    assert flow.request.inputs["resolution"] == "512x896"
    assert flow.request.inputs["negative_prompt"] == SCAIL2_DEFAULT_NEGATIVE_PROMPT
    assert flow.billing.requested_duration == 8
    assert flow.cleanup_policy.cleanup_paths == ["/tmp/reference.png", "/tmp/motion.mp4"]


@pytest.mark.asyncio
async def test_process_scail2_video_task_accepts_long_action_transfer_duration(monkeypatch):
    captured = {}

    async def fake_run_bot_task_application(*, flow):
        captured["flow"] = flow
        return "ok"

    monkeypatch.setattr(
        entrypoints,
        "resolve_internal_user_id",
        AsyncMock(return_value=999),
    )
    monkeypatch.setattr(
        entrypoints,
        "get_acceleration_notice",
        AsyncMock(return_value=""),
    )
    monkeypatch.setattr(
        entrypoints,
        "run_bot_task_application",
        fake_run_bot_task_application,
    )

    context = SimpleNamespace(
        t=lambda key, **kwargs: f"{key}:{kwargs}",
        user_data={},
    )

    await entrypoints.process_scail2_video_task(
        context=context,
        chat_id=456,
        user_id=123,
        username="tester",
        task_type=MODE_SCAIL2_ACTION_TRANSFER_LONG,
        reference_image_path="/tmp/reference.png",
        motion_video_path="/tmp/motion.mp4",
        prompt="cinematic long motion",
        duration=20,
        message_id=789,
    )

    flow = captured["flow"]
    assert flow.request.task_type == MODE_SCAIL2_ACTION_TRANSFER
    assert flow.request.inputs["duration"] == 20
    assert flow.runtime_state.actual_cost == 260
    assert flow.billing.requested_duration == 20


@pytest.mark.asyncio
async def test_process_scail2_video_task_uses_default_prompt_when_empty(monkeypatch):
    captured = {}

    async def fake_run_bot_task_application(*, flow):
        captured["flow"] = flow
        return "ok"

    monkeypatch.setattr(
        entrypoints,
        "resolve_internal_user_id",
        AsyncMock(return_value=999),
    )
    monkeypatch.setattr(
        entrypoints,
        "get_acceleration_notice",
        AsyncMock(return_value=""),
    )
    monkeypatch.setattr(
        entrypoints,
        "run_bot_task_application",
        fake_run_bot_task_application,
    )

    context = SimpleNamespace(
        t=lambda key, **kwargs: f"{key}:{kwargs}",
        user_data={},
    )

    await entrypoints.process_scail2_video_task(
        context=context,
        chat_id=456,
        user_id=123,
        username="tester",
        task_type=MODE_SCAIL2_FACE_SWAP_V2,
        reference_image_path="/tmp/reference.png",
        motion_video_path="/tmp/motion.mp4",
        prompt="",
        duration=5,
        message_id=789,
    )

    flow = captured["flow"]
    assert flow.request.inputs["prompt"] == SCAIL2_FACE_SWAP_V2_DEFAULT_POSITIVE_PROMPT
    assert flow.request.prompt == SCAIL2_FACE_SWAP_V2_DEFAULT_POSITIVE_PROMPT
