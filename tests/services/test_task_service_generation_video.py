from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.constants import MODE_IMAGE_TO_VIDEO
from src.services.task_service_generation_video import (
    process_image_to_video_generation_task,
)
from src.domain_config.wan22_aio_video import (
    WAN22_LEGACY_IMAGE_TO_VIDEO_MODEL_PROFILE,
)


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

    context = SimpleNamespace(user_data={}, bot=MagicMock(), t=lambda key, **kwargs: key)
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
        cleanup=False,
    )

    assert result == (b"video-bytes", "task-image-to-video")
    flow = captured_flow["flow"]
    assert flow.request.inputs["lora_name"] == "BreastGrow"
    assert flow.request.inputs["resolution_preset"] == "standard"
    assert flow.request.inputs["duration"] == 8
    assert flow.request.inputs["extract_last_frame"] is True
    assert flow.billing.requested_duration == 8
    assert flow.presentation.result_meta == {
        "wan22_resolution_preset": "standard",
        "wan22_duration_seconds": 8,
        "wan22_negative_prompt": flow.presentation.result_meta["wan22_negative_prompt"],
        "wan22_use_end_frame": False,
        "wan22_model_profile": WAN22_LEGACY_IMAGE_TO_VIDEO_MODEL_PROFILE,
        "wan22_chain_task_ids": [],
        "lora_name": "BreastGrow",
        "lora_strength": 1.0,
    }
