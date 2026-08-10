from unittest.mock import AsyncMock

import pytest

from src.services.advanced_video_pro_submission_service import (
    AdvancedVideoProSubmissionError,
    build_advanced_video_pro_submission_plan,
    submit_advanced_video_pro_plan,
    validate_advanced_video_pro_frame_aspects,
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


def test_i2v_normalizes_legacy_fixed_aspect_to_source():
    plan = build_advanced_video_pro_submission_plan(
        mode="i2v", prompt="move", images=["start.png"], aspect_ratio="9:16"
    )
    assert plan.aspect_ratio == "source"


def test_small_resolution_uses_new_price():
    plan = build_advanced_video_pro_submission_plan(
        mode="t2v", prompt="move", resolution_preset="small"
    )
    assert plan.cost == 15


def test_flf2v_rejects_frame_ratio_difference_over_one_percent(tmp_path):
    from PIL import Image

    first = tmp_path / "first.png"
    last = tmp_path / "last.png"
    Image.new("RGB", (600, 900)).save(first)
    Image.new("RGB", (900, 600)).save(last)
    with pytest.raises(AdvancedVideoProSubmissionError, match="比例需与首帧一致"):
        validate_advanced_video_pro_frame_aspects([str(first), str(last)])


def test_flf2v_accepts_frame_ratio_difference_within_one_percent(tmp_path):
    from PIL import Image

    first = tmp_path / "first.png"
    last = tmp_path / "last.png"
    Image.new("RGB", (600, 900)).save(first)
    Image.new("RGB", (602, 900)).save(last)
    assert validate_advanced_video_pro_frame_aspects([str(first), str(last)]) == (
        (600, 900),
        (602, 900),
    )


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
