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
    normalize_minimax_h3_duration_seconds,
)


def test_web_locales_hide_model_names():
    public_copy = ""
    root = Path(__file__).resolve().parents[2]
    for language in ("zh", "en"):
        locale = json.loads((root / "shared/locales" / f"{language}.json").read_text())
        workbench = locale["lab"]["workbench"]
        expected_addon_labels = (
            ("成人动作测试一", "成人动作测试二")
            if language == "zh"
            else ("Adult action test 1", "Adult action test 2")
        )
        assert (
            workbench["minimax_h3_addon_options"]["naughty_times"]
            == (expected_addon_labels[0])
        )
        assert (
            workbench["minimax_h3_addon_options"]["sex_pose"]
            == (expected_addon_labels[1])
        )
        assert workbench["minimax_h3_addon_options"]["motion_booster"] == (
            "成人动作强化" if language == "zh" else "Adult motion boost"
        )
        assert workbench["minimax_h3_addon_options"]["mystic_xxx"] == (
            "人体结构增强" if language == "zh" else "Anatomy enhancement"
        )
        expected_new_labels = (
            {
                "breast_play": "乳房动态",
                "innie": "阴道形态",
                "deepthroat": "深喉动作",
                "pov_missionary": "POV 传教士动作",
                "footjob": "足交动作",
                "motion_booster_ref2va": "参考人物动作强化实验",
                "pussy_stills_v1": "私密部位静帧实验",
                "titjob": "乳房夹持动作实验",
            }
            if language == "zh"
            else {
                "breast_play": "Breast motion",
                "innie": "Vaginal shape",
                "deepthroat": "Deep-throat motion",
                "pov_missionary": "POV missionary motion",
                "footjob": "Footjob motion",
                "motion_booster_ref2va": "Reference-character motion experiment",
                "pussy_stills_v1": "Intimate anatomy still-frame experiment",
                "titjob": "Breast-intercourse motion experiment",
            }
        )
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


def test_minimax_h3_exposes_eighteen_local_addons_and_defaults_to_none():
    assert tuple(MINIMAX_H3_ADDON_MODELS) == (
        "naughty_times",
        "sex_pose",
        "motion_booster",
        "motion_booster_ref2va",
        "video_reasoning",
        "mystic_xxx",
        "breast_play",
        "innie",
        "deepthroat",
        "pov_missionary",
        "footjob",
        "breasts",
        "vagassist",
        "pussy",
        "penis",
        "cumshot",
        "pussy_stills_v1",
        "titjob",
    )
    assert build_minimax_h3_spec(MINIMAX_H3_T2V, {}).addon_items == ()


def test_minimax_h3_pins_new_and_updated_addon_contracts():
    reasoning = MINIMAX_H3_ADDON_MODELS["video_reasoning"]
    assert reasoning.model_path == "MiniMaxH3/VBVR_H3_attn_only.safetensors"
    assert reasoning.default_strength == 1.0
    assert reasoning.prompt_prefix == ""
    assert reasoning.supported_modes == ("t2v", "i2v")
    assert MINIMAX_H3_ADDON_MODELS["sex_pose"].model_path == (
        "MiniMaxH3/HMNSFW-AIO-V2.5.safetensors"
    )
    assert MINIMAX_H3_ADDON_MODELS["sex_pose"].default_strength == 0.5
    assert MINIMAX_H3_ADDON_MODELS["sex_pose"].prompt_prefix == ""
    assert MINIMAX_H3_ADDON_MODELS["motion_booster"].model_path == (
        "MiniMaxH3/H3_Motion_BoosterV2.safetensors"
    )
    assert MINIMAX_H3_ADDON_MODELS["motion_booster"].prompt_prefix == "dynv2"
    ref2va_booster = MINIMAX_H3_ADDON_MODELS["motion_booster_ref2va"]
    assert ref2va_booster.model_path == "MiniMaxH3/ref2VA_Motion_v2.safetensors"
    assert ref2va_booster.default_strength == 0.7
    assert ref2va_booster.prompt_prefix == "dynv2"
    assert ref2va_booster.supported_modes == ("ref2v",)
    assert MINIMAX_H3_ADDON_MODELS["penis"].model_path == (
        "MiniMaxH3/PenisV2_minimax-h3_epoch60.safetensors"
    )
    assert MINIMAX_H3_ADDON_MODELS["penis"].prompt_prefix == "HMPenis"
    assert MINIMAX_H3_ADDON_MODELS["cumshot"].model_path == (
        "MiniMaxH3/HMCumshot_V2.safetensors"
    )
    assert MINIMAX_H3_ADDON_MODELS["cumshot"].default_strength == 0.9
    assert MINIMAX_H3_ADDON_MODELS["cumshot"].prompt_prefix == "hmcumshot3"
    assert MINIMAX_H3_ADDON_MODELS["pussy_stills_v1"].model_path == (
        "MiniMaxH3/Vagina_minimax-h3_epoch20.safetensors"
    )
    assert MINIMAX_H3_ADDON_MODELS["pussy_stills_v1"].default_strength == 0.35
    assert MINIMAX_H3_ADDON_MODELS["pussy_stills_v1"].prompt_prefix == "pussy"
    assert MINIMAX_H3_ADDON_MODELS["titjob"].model_path == (
        "MiniMaxH3/Titjob_Titfuck_V1-MiniMaxh3_ComfyTinker.safetensors"
    )
    assert MINIMAX_H3_ADDON_MODELS["titjob"].default_strength == 0.75
    assert MINIMAX_H3_ADDON_MODELS["titjob"].prompt_prefix == "titjob"


def test_minimax_h3_uses_neutral_public_labels_for_adult_motion_addons():
    assert MINIMAX_H3_ADDON_MODELS["naughty_times"].label_zh.endswith(
        "（成人动作测试一）"
    )
    assert MINIMAX_H3_ADDON_MODELS["sex_pose"].label_zh.endswith("（成人动作测试二）")
    assert MINIMAX_H3_ADDON_MODELS["motion_booster"].label_zh.endswith(
        "（成人动作强化）"
    )
    assert MINIMAX_H3_ADDON_MODELS["mystic_xxx"].label_zh.endswith("（人体结构增强）")
    assert MINIMAX_H3_ADDON_MODELS["mystic_xxx"].label_zh.startswith("Mystic XXX v4")
    assert MINIMAX_H3_ADDON_MODELS["mystic_xxx"].model_path == (
        "MiniMaxH3/MysticXXX_MMH3-V4.safetensors"
    )
    assert MINIMAX_H3_ADDON_MODELS["mystic_xxx"].default_strength == 1.0


def test_minimax_h3_normalizes_multiple_addons_with_catalog_defaults():
    spec = build_minimax_h3_spec(
        MINIMAX_H3_T2V,
        {
            "lora_items": [
                {"name": "naughty_times", "strength": 0.8},
                {"name": "sex_pose"},
                {"name": "motion_booster"},
                {"name": "mystic_xxx"},
                {"name": "breast_play"},
                {"name": "innie"},
                {"name": "deepthroat"},
                {"name": "pov_missionary"},
                {"name": "footjob"},
                {"name": "pussy"},
            ]
        },
    )
    assert [(item.name, item.strength) for item in spec.addon_items] == [
        ("naughty_times", 0.8),
        ("sex_pose", 0.5),
        ("motion_booster", 0.7),
        ("mystic_xxx", 1.0),
        ("breast_play", 0.75),
        ("innie", 0.8),
        ("deepthroat", 0.75),
        ("pov_missionary", 0.7),
        ("footjob", 0.5),
        ("pussy", 0.35),
    ]


def test_minimax_h3_ref2va_motion_booster_is_restricted_to_ref2v():
    ref_spec = build_minimax_h3_spec(
        MINIMAX_H3_REF2V,
        {
            "images": ["subject.png", "reference.png"],
            "lora_items": [{"name": "motion_booster_ref2va"}],
        },
    )

    assert [(item.name, item.strength) for item in ref_spec.addon_items] == [
        ("motion_booster_ref2va", 0.7),
    ]
    with pytest.raises(MiniMaxH3ValidationError, match="仅支持参考图生视频"):
        build_minimax_h3_spec(
            MINIMAX_H3_T2V,
            {"lora_items": [{"name": "motion_booster_ref2va"}]},
        )


def test_minimax_h3_video_reasoning_is_restricted_to_trained_modes():
    for task_type in (MINIMAX_H3_T2V, MINIMAX_H3_I2V):
        inputs = {"lora_items": [{"name": "video_reasoning"}]}
        if task_type == MINIMAX_H3_I2V:
            inputs["images"] = ["first.png"]
        spec = build_minimax_h3_spec(task_type, inputs)
        assert [(item.name, item.strength) for item in spec.addon_items] == [
            ("video_reasoning", 1.0)
        ]

    for task_type, images in (
        (MINIMAX_H3_FLF2V, ["first.png", "last.png"]),
        (MINIMAX_H3_REF2V, ["subject.png", "reference.png"]),
    ):
        with pytest.raises(MiniMaxH3ValidationError, match="不支持当前生成模式"):
            build_minimax_h3_spec(
                task_type,
                {
                    "images": images,
                    "lora_items": [{"name": "video_reasoning"}],
                },
            )


@pytest.mark.parametrize(
    "inputs,match",
    [
        ({"lora_strength": 1.0}, "选择附加模型"),
        ({"lora_name": "missing"}, "不支持"),
        ({"lora_items": [{"name": "penis"}, {"name": "penis"}]}, "不得重复"),
        ({"lora_items": [{"name": "penis", "strength": 0.0}]}, "0.1 至 2.0"),
        (
            {"lora_items": [{"name": name} for name in MINIMAX_H3_ADDON_MODELS]},
            "最多 13 项",
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


def test_minimax_h3_ref2v_accepts_dedicated_official_turbo_profile():
    spec = build_minimax_h3_spec(
        MINIMAX_H3_REF2V,
        {
            "images": ["reference.png"],
            "aspect_ratio": "16:9",
            "main_model": "official_ref2v_turbo",
        },
    )

    assert spec.main_model == "official_ref2v_turbo"
    assert spec.model_name == (
        "MiniMaxH3/minimax_h3_ref2va_pruned_int8_convrot.safetensors"
    )


@pytest.mark.parametrize(
    ("task_type", "images", "aspect_ratio"),
    [
        (MINIMAX_H3_T2V, [], "16:9"),
        (MINIMAX_H3_I2V, ["first.png"], "source"),
        (MINIMAX_H3_FLF2V, ["first.png", "last.png"], "source"),
    ],
)
def test_minimax_h3_rejects_ref2v_turbo_profile_outside_ref2v(
    task_type, images, aspect_ratio
):
    with pytest.raises(MiniMaxH3ValidationError, match="仅支持参考图生视频"):
        build_minimax_h3_spec(
            task_type,
            {
                "images": images,
                "aspect_ratio": aspect_ratio,
                "main_model": "official_ref2v_turbo",
            },
        )


@pytest.mark.parametrize(
    "preset,duration,cost,frames",
    [
        ("preview", 5, 10, 124),
        ("small", 5, 11, 124),
        ("standard", 10, 27, 243),
        ("hd", 15, 59, 362),
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
        (10, "small", 17),
        (10, "standard", 27),
        (10, "hd", 33),
        (15, "preview", 19),
        (15, "small", 27),
        (15, "standard", 42),
        (15, "hd", 59),
    ],
)
def test_minimax_h3_resolution_price_matrix_applies_public_1_1_multiplier(
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
