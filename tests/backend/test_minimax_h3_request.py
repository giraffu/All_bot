import pytest
from pydantic import ValidationError

from backend.app.models import MiniMaxH3Request


def test_minimax_h3_request_accepts_four_ordered_references():
    request = MiniMaxH3Request(
        task_id="h3-1", prompt="scene", images=["1", "2", "3", "4"],
        reference_descriptions=["a", "b", "c", "d"], width=736, height=416, frame_count=124,
    )
    assert request.images == ["1", "2", "3", "4"]


def test_minimax_h3_request_rejects_more_than_four_references():
    with pytest.raises(ValidationError):
        MiniMaxH3Request(task_id="h3-1", prompt="scene", images=["1", "2", "3", "4", "5"], width=736, height=416, frame_count=124)


def test_minimax_h3_request_accepts_six_addons_with_strengths():
    request = MiniMaxH3Request(
        task_id="h3-1",
        prompt="scene",
        width=736,
        height=416,
        frame_count=124,
        lora_items=[
            {"name": name, "strength": 0.5}
            for name in (
                "naughty_times", "sex_pose", "breasts",
                "vagassist", "pussy", "penis",
            )
        ],
    )
    assert len(request.lora_items or []) == 6


def test_minimax_h3_request_rejects_more_than_six_addons():
    with pytest.raises(ValidationError):
        MiniMaxH3Request(
            task_id="h3-1",
            prompt="scene",
            width=736,
            height=416,
            frame_count=124,
            lora_items=[{"name": str(index), "strength": 1.0} for index in range(7)],
        )
