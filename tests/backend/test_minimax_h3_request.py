import pytest
from pydantic import ValidationError

from backend.app.models import MiniMaxH3Request


def test_minimax_h3_request_accepts_five_ordered_references():
    request = MiniMaxH3Request(
        task_id="h3-1", prompt="scene", images=["1", "2", "3", "4", "5"],
        reference_descriptions=["a", "b", "c", "d", "e"], width=736, height=416, frame_count=124,
    )
    assert request.images == ["1", "2", "3", "4", "5"]


def test_minimax_h3_request_rejects_more_than_five_references():
    with pytest.raises(ValidationError):
        MiniMaxH3Request(task_id="h3-1", prompt="scene", images=["1", "2", "3", "4", "5", "6"], width=736, height=416, frame_count=124)


def test_minimax_h3_request_accepts_thirteen_addons_with_strengths():
    request = MiniMaxH3Request(
        task_id="h3-1",
        prompt="scene",
        width=736,
        height=416,
        frame_count=124,
        lora_items=[
            {"name": name, "strength": 0.5}
            for name in (f"addon-{index}" for index in range(13))
        ],
    )
    assert len(request.lora_items or []) == 13


def test_minimax_h3_request_rejects_more_than_thirteen_addons():
    with pytest.raises(ValidationError):
        MiniMaxH3Request(
            task_id="h3-1",
            prompt="scene",
            width=736,
            height=416,
            frame_count=124,
            lora_items=[{"name": str(index), "strength": 1.0} for index in range(14)],
        )
