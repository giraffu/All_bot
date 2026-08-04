import pytest

from src.domain_config.minimax_h3 import (
    MINIMAX_H3_FLF2V,
    MINIMAX_H3_I2V,
    MINIMAX_H3_REF2V,
    MINIMAX_H3_T2V,
    MiniMaxH3ValidationError,
    build_minimax_h3_spec,
)


@pytest.mark.parametrize("duration,cost,frames", [(5, 10, 124), (10, 20, 243), (15, 30, 362)])
def test_minimax_h3_t2v_duration_cost_and_frame_grid(duration, cost, frames):
    spec = build_minimax_h3_spec(MINIMAX_H3_T2V, {"duration": duration})
    assert (spec.cost, spec.frame_count, spec.fps) == (cost, frames, 24)
    assert spec.mode == "t2v"
    assert spec.width % 32 == spec.height % 32 == 0


@pytest.mark.parametrize(
    "task_type,images",
    [
        (MINIMAX_H3_I2V, ["first.png"]),
        (MINIMAX_H3_FLF2V, ["first.png", "last.png"]),
        (MINIMAX_H3_REF2V, ["a.png", "b.png", "c.png", "d.png"]),
    ],
)
def test_minimax_h3_accepts_ordered_mode_inputs(task_type, images):
    inputs = {"images": images, "aspect_ratio": "9:16", "resolution_preset": "hd"}
    if task_type == MINIMAX_H3_REF2V:
        inputs["reference_descriptions"] = [f"character {i}" for i in range(len(images))]
    spec = build_minimax_h3_spec(task_type, inputs)
    assert spec.images == tuple(images)
    assert spec.height > spec.width


def test_minimax_h3_ref2v_uses_reference_price():
    spec = build_minimax_h3_spec(MINIMAX_H3_REF2V, {"images": ["a.png"], "duration": 15})
    assert spec.cost == 36
    assert "ref2va" in spec.model_name


@pytest.mark.parametrize(
    "task_type,images",
    [
        (MINIMAX_H3_T2V, ["unexpected.png"]),
        (MINIMAX_H3_I2V, []),
        (MINIMAX_H3_FLF2V, ["one.png"]),
        (MINIMAX_H3_REF2V, ["1.png", "2.png", "3.png", "4.png", "5.png"]),
    ],
)
def test_minimax_h3_rejects_wrong_image_count(task_type, images):
    with pytest.raises(MiniMaxH3ValidationError):
        build_minimax_h3_spec(task_type, {"images": images})


@pytest.mark.parametrize("field,value", [("lora_name", "x.safetensors"), ("timeline_data", "{}"), ("model_name", "other")])
def test_minimax_h3_rejects_execution_overrides(field, value):
    with pytest.raises(MiniMaxH3ValidationError, match="不允许覆盖"):
        build_minimax_h3_spec(MINIMAX_H3_T2V, {field: value})


def test_minimax_h3_reference_descriptions_follow_image_count():
    with pytest.raises(MiniMaxH3ValidationError, match="数量"):
        build_minimax_h3_spec(
            MINIMAX_H3_REF2V,
            {"images": ["a.png", "b.png"], "reference_descriptions": ["only one"]},
        )
