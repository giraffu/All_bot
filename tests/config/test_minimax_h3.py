import pytest

from src.domain_config.minimax_h3 import (
    MINIMAX_H3_ADDON_MODELS,
    MINIMAX_H3_FLF2V,
    MINIMAX_H3_I2V,
    MINIMAX_H3_REF2V,
    MINIMAX_H3_T2V,
    MiniMaxH3ValidationError,
    build_minimax_h3_spec,
    normalize_minimax_h3_duration_seconds,
)


def test_minimax_h3_addon_catalog_exposes_five_user_models_but_not_acceleration():
    assert set(MINIMAX_H3_ADDON_MODELS) == {"breasts", "anus", "vagina", "sex_pose", "penis"}
    assert all(
        "lightx" not in path.lower()
        for item in MINIMAX_H3_ADDON_MODELS.values()
        for path in item.model_paths
    )


def test_minimax_h3_addon_model_and_strength_are_normalized():
    spec = build_minimax_h3_spec(
        MINIMAX_H3_T2V,
        {"duration": 5, "lora_name": "penis", "lora_strength": 1.25},
    )
    assert spec.addon_model == "penis"
    assert spec.addon_strength == 1.25


@pytest.mark.parametrize("inputs", [
    {"lora_name": "unknown"},
    {"lora_name": "penis", "lora_strength": 0.05},
    {"lora_name": "penis", "lora_strength": 2.05},
    {"lora_strength": 1.0},
])
def test_minimax_h3_rejects_invalid_addon_configuration(inputs):
    with pytest.raises(MiniMaxH3ValidationError):
        build_minimax_h3_spec(MINIMAX_H3_T2V, {"duration": 5, **inputs})


@pytest.mark.parametrize(
    "preset,duration,cost,frames",
    [
        ("preview", 5, 10, 124),
        ("small", 5, 15, 124),
        ("standard", 10, 40, 243),
        ("hd", 15, 90, 362),
    ],
)
def test_minimax_h3_t2v_resolution_duration_cost_and_frame_grid(preset, duration, cost, frames):
    spec = build_minimax_h3_spec(
        MINIMAX_H3_T2V, {"duration": duration, "resolution_preset": preset}
    )
    assert (spec.cost, spec.frame_count, spec.fps) == (cost, frames, 24)
    assert spec.mode == "t2v"
    assert spec.width % 32 == spec.height % 32 == 0


@pytest.mark.parametrize("raw,expected", [(5, 5), ("5", 5), ("5s", 5)])
def test_minimax_h3_duration_normalizes_to_integer_seconds(raw, expected):
    assert normalize_minimax_h3_duration_seconds(raw) == expected


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
    if task_type in {MINIMAX_H3_I2V, MINIMAX_H3_FLF2V}:
        inputs["aspect_ratio"] = "source"
    if task_type == MINIMAX_H3_REF2V:
        inputs["reference_descriptions"] = [f"character {i}" for i in range(len(images))]
    spec = build_minimax_h3_spec(task_type, inputs)
    assert spec.images == tuple(images)
    if task_type == MINIMAX_H3_REF2V:
        assert spec.height > spec.width
    else:
        assert spec.aspect_ratio == "source"
        assert (spec.width, spec.height) == (0, 0)


def test_minimax_h3_ref2v_uses_reference_price():
    spec = build_minimax_h3_spec(MINIMAX_H3_REF2V, {"images": ["a.png"], "duration": 15})
    assert spec.cost == 36
    assert "ref2va" in spec.model_name


@pytest.mark.parametrize(
    "preset,normal,reference",
    [("preview", 10, 12), ("small", 15, 18), ("standard", 20, 24), ("hd", 30, 36)],
)
def test_minimax_h3_resolution_price_matrix(preset, normal, reference):
    assert build_minimax_h3_spec(
        MINIMAX_H3_T2V, {"resolution_preset": preset}
    ).cost == normal
    assert build_minimax_h3_spec(
        MINIMAX_H3_REF2V,
        {"images": ["a.png"], "resolution_preset": preset},
    ).cost == reference


def test_minimax_h3_image_modes_require_source_aspect():
    with pytest.raises(MiniMaxH3ValidationError, match="跟随首帧"):
        build_minimax_h3_spec(
            MINIMAX_H3_I2V,
            {"images": ["first.png"], "aspect_ratio": "9:16"},
        )


def test_minimax_h3_non_image_modes_reject_source_aspect():
    with pytest.raises(MiniMaxH3ValidationError, match="固定画面比例"):
        build_minimax_h3_spec(MINIMAX_H3_T2V, {"aspect_ratio": "source"})


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


@pytest.mark.parametrize("field,value", [("timeline_data", "{}"), ("model_name", "other")])
def test_minimax_h3_rejects_execution_overrides(field, value):
    with pytest.raises(MiniMaxH3ValidationError, match="不允许覆盖"):
        build_minimax_h3_spec(MINIMAX_H3_T2V, {field: value})


def test_minimax_h3_reference_descriptions_follow_image_count():
    with pytest.raises(MiniMaxH3ValidationError, match="数量"):
        build_minimax_h3_spec(
            MINIMAX_H3_REF2V,
            {"images": ["a.png", "b.png"], "reference_descriptions": ["only one"]},
        )
