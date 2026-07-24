from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.constants import MODE_IMAGE_TO_VIDEO, MODE_WAN22_VIDEO_V2
from src.services.task_service_generation_image import process_standard_generation_task
from src.services.task_service_generation_video import (
    process_image_to_video_generation_task,
)
from src.services.task_service_generation_wan22 import (
    process_wan22_video_v2_generation_task,
)
from src.domain_config.wan22_aio_video import (
    WAN22_LEGACY_IMAGE_TO_VIDEO_MODEL_PROFILE,
)


@pytest.mark.asyncio
async def test_wan22_v2_entrypoint_forwards_qqcc_lora_items(monkeypatch):
    submit_aio = AsyncMock(return_value=(b"video-bytes", "task-wan22-v2"))
    monkeypatch.setattr(
        "src.services.task_service_generation_wan22.process_wan22_video_v2_aio_generation_task",
        submit_aio,
    )

    result = await process_wan22_video_v2_generation_task(
        context=SimpleNamespace(),
        chat_id=123,
        user_id=789,
        username="tester",
        prompt="positive",
        negative_prompt="negative",
        images=["start.png"],
        use_end_frame=False,
        lora_name="wan22_explicit_005",
        lora_strength=0.8,
        lora_items=[
            {"name": "wan22_explicit_005", "strength": 0.8},
            {"name": "wan22_explicit_008", "strength": 1.0},
        ],
    )

    assert result == (b"video-bytes", "task-wan22-v2")
    assert submit_aio.await_args.kwargs["lora_name"] == "wan22_explicit_005"
    assert submit_aio.await_args.kwargs["lora_strength"] == 0.8
    assert submit_aio.await_args.kwargs["lora_items"] == [
        {"name": "wan22_explicit_005", "strength": 0.8},
        {"name": "wan22_explicit_008", "strength": 1.0},
    ]


@pytest.mark.asyncio
async def test_process_image_to_video_task_persists_legacy_lora_context(monkeypatch):
    captured_flow = {}

    async def fake_run_bot_task_application(*, flow):
        captured_flow["flow"] = flow
        return (b"video-bytes", "task-image-to-video")

    monkeypatch.setattr(
        "src.services.wan22_aio_video_generation.resolve_internal_user_id",
        AsyncMock(return_value=456),
    )
    monkeypatch.setattr(
        "src.services.wan22_aio_video_generation.get_acceleration_notice",
        AsyncMock(return_value=""),
    )
    monkeypatch.setattr(
        "src.services.wan22_aio_video_generation.run_bot_task_application",
        fake_run_bot_task_application,
    )

    context = SimpleNamespace(
        user_data={}, bot=MagicMock(), t=lambda key, **kwargs: key
    )
    result = await process_image_to_video_generation_task(
        context=context,
        chat_id=123,
        user_id=789,
        username="tester",
        prompt="positive",
        images=["start.png"],
        task_type=MODE_IMAGE_TO_VIDEO,
        resolution_preset="standard",
        duration=8,
        lora_name="BreastGrow",
        lora_strength=1.0,
        lora_items=[
            {"name": "BreastGrow", "strength": 0.75},
            {"name": "Footjob", "strength": 1.4},
        ],
        cleanup=False,
        deduct_quota=False,
        cost_override=13,
    )

    assert result == (b"video-bytes", "task-image-to-video")
    flow = captured_flow["flow"]
    assert flow.request.inputs["lora_name"] == "BreastGrow"
    assert flow.request.inputs["lora_items"] == [
        {"name": "BreastGrow", "strength": 0.75},
        {"name": "Footjob", "strength": 1.4},
    ]
    assert flow.request.inputs["resolution_preset"] == "standard"
    assert flow.request.inputs["duration"] == 8
    assert flow.request.inputs["extract_last_frame"] is True
    assert flow.billing.requested_duration == 8
    assert flow.request.deduct_quota is False
    assert flow.request.cost_override == 13
    assert flow.presentation.result_meta == {
        "wan22_resolution_preset": "standard",
        "wan22_duration_seconds": 8,
        "wan22_negative_prompt": flow.presentation.result_meta["wan22_negative_prompt"],
        "wan22_use_end_frame": False,
        "wan22_model_profile": WAN22_LEGACY_IMAGE_TO_VIDEO_MODEL_PROFILE,
        "wan22_chain_task_ids": [],
        "lora_name": "BreastGrow",
        "lora_strength": 0.75,
        "lora_items": [
            {"name": "BreastGrow", "strength": 0.75},
            {"name": "Footjob", "strength": 1.4},
        ],
        "_generation_context": {
            "version": 1,
            "lora_name": "BreastGrow",
            "public_model_id": "video_breast_growth",
            "lora_strength": 0.75,
            "resolution": "standard",
            "duration_seconds": 8,
        },
    }


@pytest.mark.asyncio
async def test_standard_generation_wan22_v2_forwards_resolution_and_duration(
    monkeypatch,
):
    captured_kwargs = {}

    async def fake_process_wan22_video_v2_generation_task(**kwargs):
        captured_kwargs.update(kwargs)
        return (b"video-bytes", "task-wan22-v2")

    monkeypatch.setattr(
        "src.services.task_service_generation_image.resolve_internal_user_id",
        AsyncMock(return_value=456),
    )
    monkeypatch.setattr(
        "src.services.task_service_generation_image.process_wan22_video_v2_generation_task",
        fake_process_wan22_video_v2_generation_task,
    )

    context = SimpleNamespace(
        user_data={}, bot=MagicMock(), t=lambda key, **kwargs: key
    )
    result = await process_standard_generation_task(
        context=context,
        chat_id=123,
        user_id=789,
        username="tester",
        prompt="positive",
        images=["start.png"],
        is_video=True,
        task_type=MODE_WAN22_VIDEO_V2,
        negative_prompt="custom negative",
        resolution="hd",
        duration="10s",
        lora_items=[
            {"name": "BreastGrow", "strength": 0.75},
            {"name": "Footjob", "strength": 1.4},
        ],
        deduct_quota=False,
        cost_override=17,
        cleanup=False,
    )

    assert result == (b"video-bytes", "task-wan22-v2")
    assert captured_kwargs["resolution_preset"] == "hd"
    assert captured_kwargs["duration"] == "10s"
    assert captured_kwargs["negative_prompt"] == "custom negative"
    assert captured_kwargs["lora_items"] == [
        {"name": "BreastGrow", "strength": 0.75},
        {"name": "Footjob", "strength": 1.4},
    ]
    assert captured_kwargs["deduct_quota"] is False
    assert captured_kwargs["cost_override"] == 17
