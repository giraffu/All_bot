from unittest.mock import AsyncMock

import pytest

from src.services.advanced_video_pro_submission_service import (
    AdvancedVideoProSubmissionError,
    build_advanced_video_pro_submission_plan,
    submit_advanced_video_pro_plan,
)


@pytest.mark.parametrize(
    ("mode", "images", "descriptions", "task_type", "cost"),
    [
        ("t2v", [], [], "minimax_h3_t2v", 10),
        ("i2v", ["start.png"], [], "minimax_h3_i2v", 10),
        ("flf2v", ["start.png", "end.png"], [], "minimax_h3_flf2v", 10),
        ("ref2v", ["alice.png"], ["Alice, red hair"], "minimax_h3_ref2v", 12),
    ],
)
def test_builds_all_pro_video_modes(mode, images, descriptions, task_type, cost):
    plan = build_advanced_video_pro_submission_plan(
        mode=mode,
        prompt="cinematic motion",
        images=images,
        reference_descriptions=descriptions,
    )
    assert plan.task_type == task_type
    assert plan.cost == cost


def test_rejects_wrong_media_count():
    with pytest.raises(AdvancedVideoProSubmissionError, match="恰好 2 张"):
        build_advanced_video_pro_submission_plan(
            mode="flf2v", prompt="motion", images=["only.png"]
        )


@pytest.mark.asyncio
async def test_submit_uses_public_bot_generation_seam():
    process = AsyncMock(return_value=(b"video", "output.mp4"))
    plan = build_advanced_video_pro_submission_plan(
        mode="ref2v",
        prompt="Alice waves",
        images=["alice.png"],
        reference_descriptions=["Alice, red hair"],
        duration=10,
        resolution_preset="standard",
        aspect_ratio="9:16",
    )
    result = await submit_advanced_video_pro_plan(
        plan,
        context=object(),
        chat_id=1,
        user_id=2,
        username="alice",
        process_task_func=process,
    )
    assert result == (b"video", "output.mp4")
    kwargs = process.await_args.kwargs
    assert kwargs["task_type"] == "minimax_h3_ref2v"
    assert kwargs["reference_descriptions"] == ["Alice, red hair"]
    assert kwargs["duration"] == 10
    assert kwargs["resolution_preset"] == "standard"
    assert kwargs["aspect_ratio"] == "9:16"
