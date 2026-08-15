import pytest

from src.domain_config.minimax_h3 import (
    MINIMAX_H3_FLF2V,
    MINIMAX_H3_I2V,
    MINIMAX_H3_REF2V,
    MINIMAX_H3_T2V,
    MiniMaxH3ValidationError,
    build_minimax_h3_spec,
    normalize_minimax_h3_duration_seconds,
)


@pytest.mark.parametrize("inputs", [
    {"lora_name": "penis"},
    {"lora_strength": 1.0},
    {"lora_items": [{"name": "sex_pose", "strength": 0.75}]},
    {"addon_models": ["duplicate"]},
])
def test_minimax_h3_rejects_non_empty_client_addon_configuration(inputs):
    with pytest.raises(MiniMaxH3ValidationError, match="固定模型栈"):
        build_minimax_h3_spec(MINIMAX_H3_T2V, {"duration": 5, **inputs})


@pytest.mark.parametrize("inputs", [
    {"lora_name": ""},
    {"lora_strength": None},
    {"lora_items": []},
    {"addon_models": []},
])
def test_minimax_h3_accepts_empty_legacy_addon_placeholders(inputs):
    assert build_minimax_h3_spec(MINIMAX_H3_T2V, inputs).mode == "t2v"


def test_minimax_h3_uses_fixed_10eros_beta2_model_for_public_modes():
    for task_type, images in (
        (MINIMAX_H3_T2V, []),
        (MINIMAX_H3_I2V, ["first.png"]),
        (MINIMAX_H3_FLF2V, ["first.png", "last.png"]),
    ):
        spec = build_minimax_h3_spec(
            task_type,
            {"images": images, "aspect_ratio": "source" if images else "16:9"},
        )
        assert spec.model_name == "MiniMaxH3/10Eros_Max_h3_fl2va_beta2_pruned.safetensors"


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
    ],
)
def test_minimax_h3_accepts_ordered_mode_inputs(task_type, images):
    inputs = {"images": images, "aspect_ratio": "9:16", "resolution_preset": "hd"}
    if task_type in {MINIMAX_H3_I2V, MINIMAX_H3_FLF2V}:
        inputs["aspect_ratio"] = "source"
    spec = build_minimax_h3_spec(task_type, inputs)
    assert spec.images == tuple(images)
    assert spec.aspect_ratio == "source"
    assert (spec.width, spec.height) == (0, 0)


def test_minimax_h3_ref2v_is_historical_only_and_rejects_new_specs():
    with pytest.raises(MiniMaxH3ValidationError, match="未知"):
        build_minimax_h3_spec(MINIMAX_H3_REF2V, {"images": ["a.png"]})


@pytest.mark.parametrize(
    "preset,normal",
    [("preview", 10), ("small", 15), ("standard", 20), ("hd", 30)],
)
def test_minimax_h3_resolution_price_matrix(preset, normal):
    assert build_minimax_h3_spec(
        MINIMAX_H3_T2V, {"resolution_preset": preset}
    ).cost == normal


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
    ],
)
def test_minimax_h3_rejects_wrong_image_count(task_type, images):
    with pytest.raises(MiniMaxH3ValidationError):
        build_minimax_h3_spec(task_type, {"images": images})


@pytest.mark.parametrize("field,value", [("timeline_data", "{}"), ("model_name", "other"), ("sampler_name", "dpmpp_2m"), ("scheduler", "karras"), ("steps", 25)])
def test_minimax_h3_rejects_execution_overrides(field, value):
    with pytest.raises(MiniMaxH3ValidationError, match="不允许覆盖"):
        build_minimax_h3_spec(MINIMAX_H3_T2V, {field: value})


def test_minimax_h3_public_modes_reject_reference_descriptions():
    with pytest.raises(MiniMaxH3ValidationError, match="不支持"):
        build_minimax_h3_spec(
            MINIMAX_H3_T2V,
            {"reference_descriptions": ["historical ref2v field"]},
        )
