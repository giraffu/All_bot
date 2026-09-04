import json
from pathlib import Path

import pytest

from src.domain_config.minimax_h3 import (
    MINIMAX_H3_ADDON_MODELS,
    MINIMAX_H3_FLF2V,
    MINIMAX_H3_I2V,
    MINIMAX_H3_REF2V,
    MINIMAX_H3_T2V,
    MiniMaxH3ValidationError,
    build_minimax_h3_spec,
    get_minimax_h3_cost,
    normalize_minimax_h3_duration_seconds,
)


def test_web_locales_hide_model_names():
    public_copy = ""
    root = Path(__file__).resolve().parents[2]
    for language in ("zh", "en"):
        locale = json.loads((root / "shared/locales" / f"{language}.json").read_text())
        workbench = locale["lab"]["workbench"]
        expected_new_labels = (
            {
                "deepthroat": "深喉动作",
                "pov_missionary": "POV 传教士动作",
                "footjob": "足交动作",
                "cumshot": "射精动作",
            }
            if language == "zh"
            else {
                "deepthroat": "Deep-throat motion",
                "pov_missionary": "POV missionary motion",
                "footjob": "Footjob motion",
                "cumshot": "Ejaculation motion",
            }
        )
        assert workbench["minimax_h3_addon_options"] == expected_new_labels
        for model_id, label in expected_new_labels.items():
            assert workbench["minimax_h3_addon_options"][model_id] == label
        public_copy += " " + json.dumps(
            {
                "title": locale["lab"]["cards"]["minimax_h3_title"],
                "description": locale["lab"]["cards"]["minimax_h3_desc"],
                "addons": workbench["minimax_h3_addons"],
                "options": workbench["minimax_h3_addon_options"],
            },
            ensure_ascii=False,
        )
        assert "minimax_h3_base_stack" not in workbench

    for private_term in (
        "10Eros",
        "LightX2V",
        "LoRA",
        "NaughtyTimes",
        "HMNSFW",
        "Motion Booster",
        "REF2VA",
        "Mystic XXX",
        "Breast Play & Jiggle",
        "HMInnie",
        "Daring",
        "H3 POV Missionary Insertion",
        "H3 Footjobs",
        "HMBreasts",
        "VagAssist",
        "HMPussy",
        "HMPenis",
        "HMPussy V1 Stills",
        "Better Titfuck",
    ):
        assert private_term not in public_copy


def test_minimax_h3_image_bounds_aimdo_cast_reservation():
    root = Path(__file__).resolve().parents[2]
    dockerfile = (root / "workers/runpod_profiles/minimax_h3/Dockerfile").read_text()

    assert "DEFAULT_AIMDO_CAST_BUFFER_RESERVATION_SIZE = 8 * 1024 ** 3" in dockerfile


def test_minimax_h3_image_pins_parallel_nvidia_vfx_build_dependency():
    root = Path(__file__).resolve().parents[2]
    dockerfile = (root / "workers/runpod_profiles/minimax_h3/Dockerfile").read_text()

    assert "NVIDIA_VFX_WHEEL_SIZE=597321055" in dockerfile
    assert (
        "NVIDIA_VFX_WHEEL_SHA256="
        "e51d9e6faa68466e45b83be7928321af4b0c561c7c5536a8cb2b7e6aba25f905"
    ) in dockerfile
    assert "download_pinned_file.py" in dockerfile
    assert "ARG NVIDIA_VFX_DOWNLOAD_PARALLELISM=1" in dockerfile
    assert '--parallelism "${NVIDIA_VFX_DOWNLOAD_PARALLELISM}"' in dockerfile


def test_minimax_h3_exposes_only_the_four_approved_action_addons():
    assert tuple(MINIMAX_H3_ADDON_MODELS) == (
        "deepthroat",
        "pov_missionary",
        "footjob",
        "cumshot",
    )
    assert build_minimax_h3_spec(MINIMAX_H3_T2V, {}).addon_items == ()


@pytest.mark.parametrize("main_model", ["official", "official_ref2v_turbo"])
def test_minimax_h3_rejects_retired_official_main_models(main_model):
    with pytest.raises(MiniMaxH3ValidationError, match="不支持该 MiniMax H3 主模型"):
        build_minimax_h3_spec(
            MINIMAX_H3_REF2V,
            {
                "images": ["reference.png"],
                "aspect_ratio": "16:9",
                "main_model": main_model,
            },
        )


@pytest.mark.parametrize(
    ("main_model", "expected_model"),
    [
        (
            "10eros_bf16",
            "MiniMaxH3/10Eros_Max_h3_TURBO-hybrid_beta4.safetensors",
        ),
        (
            "10eros_int8",
            "MiniMaxH3/10Eros_Max_h3_TURBO-hybrid_beta4_int8_convrot.safetensors",
        ),
    ],
)
def test_minimax_h3_exposes_bf16_and_int8_10eros_profiles_for_every_mode(
    main_model, expected_model
):
    cases = (
        (MINIMAX_H3_T2V, [], "16:9"),
        (MINIMAX_H3_I2V, ["first.png"], "source"),
        (MINIMAX_H3_FLF2V, ["first.png", "last.png"], "source"),
        (MINIMAX_H3_REF2V, ["reference.png"], "16:9"),
    )
    for task_type, images, aspect_ratio in cases:
        spec = build_minimax_h3_spec(
            task_type,
            {
                "images": images,
                "aspect_ratio": aspect_ratio,
                "main_model": main_model,
            },
        )
        assert spec.main_model == main_model
        assert spec.model_name == expected_model


def test_minimax_h3_pins_the_four_approved_addon_contracts():
    expected = {
        "deepthroat": ("MiniMaxH3/deepthroat_v02.safetensors", 0.75, ""),
        "pov_missionary": ("MiniMaxH3/H3_Mis_Insrt_v07.safetensors", 0.7, ""),
        "footjob": ("MiniMaxH3/H3_Footjob_TypeB_v1.safetensors", 0.5, "fj."),
        "cumshot": ("MiniMaxH3/HMCumshot_V2.safetensors", 0.9, "hmcumshot3"),
    }
    assert {
        name: (model.model_path, model.default_strength, model.prompt_prefix)
        for name, model in MINIMAX_H3_ADDON_MODELS.items()
    } == expected


def test_minimax_h3_normalizes_four_addons_with_catalog_defaults():
    spec = build_minimax_h3_spec(
        MINIMAX_H3_T2V,
        {
            "lora_items": [
                {"name": "deepthroat"},
                {"name": "pov_missionary"},
                {"name": "footjob"},
                {"name": "cumshot"},
            ]
        },
    )
    assert [(item.name, item.strength) for item in spec.addon_items] == [
        ("deepthroat", 0.75),
        ("pov_missionary", 0.7),
        ("footjob", 0.5),
        ("cumshot", 0.9),
    ]


@pytest.mark.parametrize(
    "inputs,match",
    [
        ({"lora_strength": 1.0}, "选择附加模型"),
        ({"lora_name": "missing"}, "不支持"),
        ({"lora_items": [{"name": "deepthroat"}, {"name": "deepthroat"}]}, "不得重复"),
        ({"lora_items": [{"name": "deepthroat", "strength": 0.0}]}, "0.1 至 2.0"),
        (
            {"lora_items": [{"name": "deepthroat"}] * 5},
            "最多 4 项",
        ),
    ],
)
def test_minimax_h3_rejects_invalid_addon_configuration(inputs, match):
    with pytest.raises(MiniMaxH3ValidationError, match=match):
        build_minimax_h3_spec(MINIMAX_H3_T2V, inputs)


@pytest.mark.parametrize(
    "inputs",
    [
        {"lora_name": ""},
        {"lora_strength": None},
        {"lora_items": []},
        {"addon_models": []},
    ],
)
def test_minimax_h3_accepts_empty_legacy_addon_placeholders(inputs):
    assert build_minimax_h3_spec(MINIMAX_H3_T2V, inputs).mode == "t2v"


def test_minimax_h3_ref2v_accepts_one_optional_reference_audio():
    spec = build_minimax_h3_spec(
        MINIMAX_H3_REF2V,
        {
            "images": ["subject.png"],
            "reference_audio": "voice.m4a",
        },
    )

    assert spec.reference_audio == "voice.m4a"


def test_minimax_h3_ref2v_accepts_reference_video_without_images():
    spec = build_minimax_h3_spec(
        MINIMAX_H3_REF2V,
        {
            "reference_video": "task-inputs/extension/previous-tail.mp4",
            "aspect_ratio": "16:9",
        },
    )

    assert spec.images == ()
    assert spec.reference_video == "task-inputs/extension/previous-tail.mp4"


def test_minimax_h3_ref2v_requires_an_image_or_reference_video():
    with pytest.raises(MiniMaxH3ValidationError, match="参考图片或参考视频"):
        build_minimax_h3_spec(MINIMAX_H3_REF2V, {})


def test_minimax_h3_non_reference_modes_reject_reference_video():
    with pytest.raises(MiniMaxH3ValidationError, match="参考视频仅支持"):
        build_minimax_h3_spec(
            MINIMAX_H3_I2V,
            {
                "images": ["first.png"],
                "reference_video": "previous.mp4",
            },
        )


@pytest.mark.parametrize(
    ("task_type", "images"),
    [
        (MINIMAX_H3_T2V, []),
        (MINIMAX_H3_I2V, ["first.png"]),
        (MINIMAX_H3_FLF2V, ["first.png", "last.png"]),
    ],
)
def test_minimax_h3_non_reference_modes_reject_reference_audio(task_type, images):
    with pytest.raises(MiniMaxH3ValidationError, match="参考图生视频"):
        build_minimax_h3_spec(
            task_type,
            {"images": images, "reference_audio": "voice.wav"},
        )


def test_minimax_h3_uses_fixed_10eros_beta4_hybrid_model_for_all_public_modes():
    for task_type, images in (
        (MINIMAX_H3_T2V, []),
        (MINIMAX_H3_I2V, ["first.png"]),
        (MINIMAX_H3_FLF2V, ["first.png", "last.png"]),
        (MINIMAX_H3_REF2V, ["reference.png"]),
    ):
        spec = build_minimax_h3_spec(
            task_type,
            {
                "images": images,
                "aspect_ratio": (
                    "source"
                    if task_type in {MINIMAX_H3_I2V, MINIMAX_H3_FLF2V}
                    else "16:9"
                ),
            },
        )
        assert spec.model_name == (
            "MiniMaxH3/10Eros_Max_h3_TURBO-hybrid_beta4.safetensors"
        )


@pytest.mark.parametrize(
    "preset,duration,cost,frames",
    [
        ("preview", 5, 10, 124),
        ("small", 5, 11, 124),
        ("standard", 10, 36, 243),
        ("hd", 15, 89, 362),
    ],
)
def test_minimax_h3_t2v_resolution_duration_cost_and_frame_grid(
    preset, duration, cost, frames
):
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


@pytest.mark.parametrize(
    "count",
    [1, 4, 5],
)
def test_minimax_h3_ref2v_accepts_ordered_reference_images(count):
    images = [f"ref-{index}.png" for index in range(count)]
    spec = build_minimax_h3_spec(
        MINIMAX_H3_REF2V,
        {
            "images": images,
            "aspect_ratio": "16:9",
            "resolution_preset": "preview",
        },
    )

    assert spec.mode == "ref2v"
    assert spec.images == tuple(images)
    assert spec.model_name == "MiniMaxH3/10Eros_Max_h3_TURBO-hybrid_beta4.safetensors"
    assert (spec.width, spec.height) != (0, 0)


def test_minimax_h3_ref2v_rejects_more_than_five_worker_images():
    count = 6
    with pytest.raises(MiniMaxH3ValidationError, match="0 至 5"):
        build_minimax_h3_spec(
            MINIMAX_H3_REF2V,
            {"images": [f"ref-{index}.png" for index in range(count)]},
        )


@pytest.mark.parametrize(
    "duration,preset,normal",
    [
        (5, "preview", 10),
        (5, "small", 11),
        (5, "standard", 15),
        (5, "hd", 17),
        (10, "preview", 14),
        (10, "small", 21),
        (10, "standard", 36),
        (10, "hd", 47),
        (15, "preview", 23),
        (15, "small", 36),
        (15, "standard", 63),
        (15, "hd", 89),
    ],
)
def test_minimax_h3_resolution_price_matrix_uses_default_normal_prices(
    duration, preset, normal
):
    assert (
        build_minimax_h3_spec(
            MINIMAX_H3_T2V,
            {"duration": duration, "resolution_preset": preset},
        ).cost
        == normal
    )


@pytest.mark.parametrize(
    "preset,duration,cost",
    [
        ("preview", 5, 11),
        ("small", 5, 13),
        ("standard", 5, 17),
        ("hd", 5, 22),
        ("preview", 10, 17),
        ("small", 10, 24),
        ("standard", 10, 37),
        ("hd", 10, 50),
        ("preview", 15, 26),
        ("small", 15, 38),
        ("standard", 15, 64),
        ("hd", 15, 91),
    ],
)
def test_minimax_h3_ref2v_price_matrix_applies_public_1_1_multiplier(
    preset, duration, cost
):
    spec = build_minimax_h3_spec(
        MINIMAX_H3_REF2V,
        {
            "images": ["ref.png"],
            "resolution_preset": preset,
            "duration": duration,
        },
    )
    assert spec.cost == cost


@pytest.mark.parametrize(
    "reference_audio,reference_video,expected",
    [
        (False, False, 91),
        (True, False, 101),
        (False, True, 146),
        (True, True, 161),
    ],
)
def test_minimax_h3_reference_media_multipliers_compose_and_round_up(
    reference_audio, reference_video, expected
):
    assert get_minimax_h3_cost(
        MINIMAX_H3_REF2V,
        duration=15,
        resolution_preset="hd",
        reference_audio=reference_audio,
        reference_video=reference_video,
    ) == expected


def test_minimax_h3_spec_includes_reference_media_multipliers():
    spec = build_minimax_h3_spec(
        MINIMAX_H3_REF2V,
        {
            "images": ["ref.png"],
            "reference_audio": "voice.m4a",
            "reference_video": "motion.mp4",
            "resolution_preset": "hd",
            "duration": 15,
        },
    )

    assert spec.cost == 161


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


@pytest.mark.parametrize(
    "field,value",
    [
        ("timeline_data", "{}"),
        ("model_name", "other"),
        ("sampler_name", "dpmpp_2m"),
        ("scheduler", "karras"),
        ("steps", 25),
    ],
)
def test_minimax_h3_rejects_execution_overrides(field, value):
    with pytest.raises(MiniMaxH3ValidationError, match="不允许覆盖"):
        build_minimax_h3_spec(MINIMAX_H3_T2V, {field: value})


def test_minimax_h3_public_modes_reject_reference_descriptions():
    with pytest.raises(MiniMaxH3ValidationError, match="不支持"):
        build_minimax_h3_spec(
            MINIMAX_H3_T2V,
            {"reference_descriptions": ["historical ref2v field"]},
        )
