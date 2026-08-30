from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

MINIMAX_H3_T2V = "minimax_h3_t2v"
MINIMAX_H3_I2V = "minimax_h3_i2v"
MINIMAX_H3_FLF2V = "minimax_h3_flf2v"
MINIMAX_H3_REF2V = "minimax_h3_ref2v"
MINIMAX_H3_PUBLIC_TASK_TYPES = (
    MINIMAX_H3_T2V,
    MINIMAX_H3_I2V,
    MINIMAX_H3_FLF2V,
    MINIMAX_H3_REF2V,
)
MINIMAX_H3_TASK_TYPES = (
    *MINIMAX_H3_PUBLIC_TASK_TYPES,
    MINIMAX_H3_REF2V,
)

MINIMAX_H3_FPS = 24
MINIMAX_H3_MAX_SEED = 1 << 50
MINIMAX_H3_ALLOWED_DURATIONS = (5, 10, 15)
MINIMAX_H3_FRAME_COUNTS = {5: 124, 10: 243, 15: 362}
MINIMAX_H3_PIXEL_PRESETS = {
    "preview": 260_000,
    "small": 360_000,
    "standard": 520_000,
    "hd": 650_000,
}
MINIMAX_H3_PUBLIC_PRICE_MULTIPLIER_NUMERATOR = 11
MINIMAX_H3_PUBLIC_PRICE_MULTIPLIER_DENOMINATOR = 10


def _apply_public_price_multiplier(price: int) -> int:
    numerator = price * MINIMAX_H3_PUBLIC_PRICE_MULTIPLIER_NUMERATOR
    denominator = MINIMAX_H3_PUBLIC_PRICE_MULTIPLIER_DENOMINATOR
    return (numerator + denominator - 1) // denominator


_MINIMAX_H3_NORMAL_BASE_PRICE_BY_DURATION = {
    5: {"preview": 9, "small": 10, "standard": 13, "hd": 15},
    10: {"preview": 12, "small": 15, "standard": 24, "hd": 30},
    15: {"preview": 17, "small": 24, "standard": 38, "hd": 53},
}
_MINIMAX_H3_REF2V_BASE_PRICE_BY_DURATION = {
    5: {"preview": 10, "small": 11, "standard": 15, "hd": 20},
    10: {"preview": 15, "small": 21, "standard": 33, "hd": 45},
    15: {"preview": 23, "small": 34, "standard": 58, "hd": 82},
}


def _build_public_price_matrix(
    base_matrix: dict[int, dict[str, int]],
) -> dict[int, dict[str, int]]:
    return {
        duration: {
            preset: _apply_public_price_multiplier(price)
            for preset, price in prices.items()
        }
        for duration, prices in base_matrix.items()
    }


MINIMAX_H3_NORMAL_PRICE_BY_DURATION = _build_public_price_matrix(
    _MINIMAX_H3_NORMAL_BASE_PRICE_BY_DURATION
)
MINIMAX_H3_REF2V_PRICE_BY_DURATION = _build_public_price_matrix(
    _MINIMAX_H3_REF2V_BASE_PRICE_BY_DURATION
)
MINIMAX_H3_ASPECT_RATIOS = {
    "16:9": 16 / 9,
    "9:16": 9 / 16,
    "1:1": 1.0,
    "4:3": 4 / 3,
    "3:4": 3 / 4,
}
MINIMAX_H3_MAX_PIXELS = 768 * 1344
MINIMAX_H3_MODEL_FL = "MiniMaxH3/10Eros_Max_h3_TURBO-hybrid_beta4.safetensors"
MINIMAX_H3_MODEL_REF = MINIMAX_H3_MODEL_FL
MINIMAX_H3_MAIN_MODEL_10EROS = "10eros"
MINIMAX_H3_MAIN_MODEL_OFFICIAL = "official"
MINIMAX_H3_MAIN_MODEL_OFFICIAL_REF2V_TURBO = "official_ref2v_turbo"
MINIMAX_H3_DEFAULT_MAIN_MODEL = MINIMAX_H3_MAIN_MODEL_10EROS
MINIMAX_H3_MAIN_MODELS = (
    MINIMAX_H3_MAIN_MODEL_10EROS,
    MINIMAX_H3_MAIN_MODEL_OFFICIAL,
    MINIMAX_H3_MAIN_MODEL_OFFICIAL_REF2V_TURBO,
)
MINIMAX_H3_OFFICIAL_MODEL_FL = (
    "MiniMaxH3/minimax_h3_fl2va_pruned_int8_convrot.safetensors"
)
MINIMAX_H3_OFFICIAL_MODEL_REF = (
    "MiniMaxH3/minimax_h3_ref2va_pruned_int8_convrot.safetensors"
)
MINIMAX_H3_ADDON_MIN_STRENGTH = 0.1
MINIMAX_H3_ADDON_MAX_STRENGTH = 2.0
MINIMAX_H3_MODES = ("t2v", "i2v", "flf2v", "ref2v")
# The catalog may grow without forcing an API/control-plane rollout. Requests
# remain capped at the already deployed transport contract.
MINIMAX_H3_MAX_ADDON_ITEMS = 13


@dataclass(frozen=True, slots=True)
class MiniMaxH3AddonModel:
    id: str
    label_zh: str
    label_en: str
    model_path: str
    default_strength: float
    prompt_prefix: str = ""
    supported_modes: tuple[str, ...] = MINIMAX_H3_MODES


@dataclass(frozen=True, slots=True)
class MiniMaxH3AddonSelection:
    name: str
    strength: float


# Public catalog intentionally maps one option to one locally pinned file. This
# avoids loading the same physical LoRA twice when users combine options and
# makes each Web strength control unambiguous.
MINIMAX_H3_ADDON_MODELS = {
    "naughty_times": MiniMaxH3AddonModel(
        "naughty_times",
        "NaughtyTimes v2（成人动作测试一）",
        "NaughtyTimes v2 (adult action test 1)",
        "MiniMaxH3/NaughtyTimes_pruned_r256_v2.safetensors",
        1.0,
    ),
    "sex_pose": MiniMaxH3AddonModel(
        "sex_pose",
        "HMNSFW AIO v2.5（成人动作测试二）",
        "HMNSFW AIO v2.5 (adult action test 2)",
        "MiniMaxH3/HMNSFW-AIO-V2.5.safetensors",
        0.5,
    ),
    "motion_booster": MiniMaxH3AddonModel(
        "motion_booster",
        "H3 Motion Booster v2（成人动作强化）",
        "H3 Motion Booster v2 (adult motion boost)",
        "MiniMaxH3/H3_Motion_BoosterV2.safetensors",
        0.7,
        "dynv2",
    ),
    "motion_booster_ref2va": MiniMaxH3AddonModel(
        "motion_booster_ref2va",
        "H3 Motion Booster V0.2 REF2VA（参考人物动作强化实验）",
        "H3 Motion Booster V0.2 REF2VA (reference-character motion experiment)",
        "MiniMaxH3/ref2VA_Motion_v2.safetensors",
        0.7,
        "dynv2",
        ("ref2v",),
    ),
    "video_reasoning": MiniMaxH3AddonModel(
        "video_reasoning",
        "VBVR H3 v1（提示词遵循与时序辅助）",
        "VBVR H3 v1 (prompt-following and temporal aid)",
        "MiniMaxH3/VBVR_H3_attn_only.safetensors",
        1.0,
        supported_modes=("t2v", "i2v"),
    ),
    "mystic_xxx": MiniMaxH3AddonModel(
        "mystic_xxx",
        "Mystic XXX v4（人体结构增强）",
        "Mystic XXX v4 (anatomy enhancement)",
        "MiniMaxH3/MysticXXX_MMH3-V4.safetensors",
        1.0,
    ),
    "breast_play": MiniMaxH3AddonModel(
        "breast_play",
        "Breast Play & Jiggle v1（乳房动态）",
        "Breast Play & Jiggle v1 (breast motion)",
        "MiniMaxH3/breastplayjiggle_h3_v1.safetensors",
        0.75,
    ),
    "innie": MiniMaxH3AddonModel(
        "innie",
        "HMInnie v1（阴道形态）",
        "HMInnie v1 (vaginal shape)",
        "MiniMaxH3/HMInnie_v1_e50.safetensors",
        0.8,
        "inniepussy",
    ),
    "deepthroat": MiniMaxH3AddonModel(
        "deepthroat",
        "Daring Deepthroat v0.2（深喉动作）",
        "Daring Deepthroat v0.2 (deep-throat motion)",
        "MiniMaxH3/deepthroat_v02.safetensors",
        0.75,
    ),
    "pov_missionary": MiniMaxH3AddonModel(
        "pov_missionary",
        "H3 POV Missionary v0.7（POV 传教士动作）",
        "H3 POV Missionary v0.7 (POV missionary motion)",
        "MiniMaxH3/H3_Mis_Insrt_v07.safetensors",
        0.7,
    ),
    "footjob": MiniMaxH3AddonModel(
        "footjob",
        "H3 Footjobs Type B v1（足交动作）",
        "H3 Footjobs Type B v1 (footjob motion)",
        "MiniMaxH3/H3_Footjob_TypeB_v1.safetensors",
        0.5,
        "fj.",
    ),
    "breasts": MiniMaxH3AddonModel(
        "breasts",
        "HMBreasts（乳房）",
        "HMBreasts",
        "MiniMaxH3/HMBreasts_085e0750_e40.safetensors",
        1.0,
        "HMBreasts",
    ),
    "vagassist": MiniMaxH3AddonModel(
        "vagassist",
        "VagAssist（阴道/肛门辅助）",
        "VagAssist (vagina/anus assist)",
        "MiniMaxH3/vagassist_e40.safetensors",
        1.0,
        "Vagina, anus",
    ),
    "pussy": MiniMaxH3AddonModel(
        "pussy",
        "HMPussy v6（阴道）",
        "HMPussy v6",
        "MiniMaxH3/hmpussy_v6_epoch30.safetensors",
        0.35,
        "Vagina",
    ),
    "penis": MiniMaxH3AddonModel(
        "penis",
        "HMPenis v2（阴茎）",
        "HMPenis v2",
        "MiniMaxH3/PenisV2_minimax-h3_epoch60.safetensors",
        1.0,
        "HMPenis",
    ),
    "cumshot": MiniMaxH3AddonModel(
        "cumshot",
        "HMCumshot v0.5（射精动作）",
        "HMCumshot v0.5 (ejaculation motion)",
        "MiniMaxH3/HMCumshot_V2.safetensors",
        0.9,
        "hmcumshot3",
    ),
    "pussy_stills_v1": MiniMaxH3AddonModel(
        "pussy_stills_v1",
        "HMPussy V1 Stills（私密部位静帧实验）",
        "HMPussy V1 Stills (intimate anatomy still-frame experiment)",
        "MiniMaxH3/Vagina_minimax-h3_epoch20.safetensors",
        0.35,
        "pussy",
    ),
    "titjob": MiniMaxH3AddonModel(
        "titjob",
        "Better Titfuck v0.5（乳房夹持动作实验）",
        "Better Titfuck v0.5 (breast-intercourse motion experiment)",
        "MiniMaxH3/Titjob_Titfuck_V1-MiniMaxh3_ComfyTinker.safetensors",
        0.75,
        "titjob",
    ),
}


class MiniMaxH3ValidationError(ValueError):
    pass


PRODUCT_NAME = "高级图生视频pro"


@dataclass(frozen=True, slots=True)
class MiniMaxH3Spec:
    task_type: str
    mode: str
    duration_seconds: int
    resolution_preset: str
    aspect_ratio: str
    width: int
    height: int
    frame_count: int
    fps: int
    cost: int
    images: tuple[str, ...]
    reference_descriptions: tuple[str, ...]
    reference_video: str | None
    reference_audio: str | None
    main_model: str
    model_name: str
    addon_items: tuple[MiniMaxH3AddonSelection, ...]


def normalize_minimax_h3_addon_items(
    inputs: dict[str, Any],
    *,
    mode: str | None = None,
) -> tuple[MiniMaxH3AddonSelection, ...]:
    raw_items = inputs.get("lora_items")
    legacy_names = inputs.get("addon_models")
    legacy_name = str(inputs.get("lora_name") or "").strip()
    legacy_strength = inputs.get("lora_strength")
    configured_formats = sum(
        value not in (None, "", [], ())
        for value in (raw_items, legacy_names, legacy_name)
    )
    if configured_formats > 1:
        raise MiniMaxH3ValidationError("附加模型参数格式不能混用。")
    if raw_items is None and legacy_names not in (None, [], ()):
        if not isinstance(legacy_names, (list, tuple)):
            raise MiniMaxH3ValidationError("addon_models 必须为有序数组。")
        raw_items = [{"name": name} for name in legacy_names]
    if raw_items is None:
        if not legacy_name:
            if legacy_strength not in (None, ""):
                raise MiniMaxH3ValidationError("选择附加模型后才能设置强度。")
            return ()
        raw_items = [{"name": legacy_name, "strength": legacy_strength}]
    if not isinstance(raw_items, (list, tuple)):
        raise MiniMaxH3ValidationError("附加模型必须为有序数组。")
    if len(raw_items) > MINIMAX_H3_MAX_ADDON_ITEMS:
        raise MiniMaxH3ValidationError(
            f"附加模型必须为最多 {MINIMAX_H3_MAX_ADDON_ITEMS} 项的数组。"
        )
    result: list[MiniMaxH3AddonSelection] = []
    seen: set[str] = set()
    for raw in raw_items:
        if not isinstance(raw, dict):
            raise MiniMaxH3ValidationError("附加模型配置格式错误。")
        name = str(raw.get("name") or "").strip()
        model = MINIMAX_H3_ADDON_MODELS.get(name)
        if model is None:
            raise MiniMaxH3ValidationError("不支持该附加模型。")
        if mode is not None and mode not in model.supported_modes:
            if model.supported_modes == ("ref2v",):
                raise MiniMaxH3ValidationError("该附加模型仅支持参考图生视频。")
            raise MiniMaxH3ValidationError("该附加模型不支持当前生成模式。")
        if name in seen:
            raise MiniMaxH3ValidationError("附加模型不得重复选择。")
        seen.add(name)
        raw_strength = raw.get("strength")
        try:
            strength = (
                model.default_strength
                if raw_strength in (None, "")
                else float(raw_strength)
            )
        except (TypeError, ValueError) as exc:
            raise MiniMaxH3ValidationError("附加模型强度必须为数字。") from exc
        if not (
            math.isfinite(strength)
            and MINIMAX_H3_ADDON_MIN_STRENGTH
            <= strength
            <= MINIMAX_H3_ADDON_MAX_STRENGTH
        ):
            raise MiniMaxH3ValidationError("附加模型强度必须在 0.1 至 2.0 之间。")
        result.append(MiniMaxH3AddonSelection(name=name, strength=strength))
    return tuple(result)


def _string_tuple(value: Any, *, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise MiniMaxH3ValidationError(f"{field} 必须使用有序数组。")
    return tuple(str(item or "").strip() for item in value)


def normalize_minimax_h3_duration_seconds(value: Any) -> int:
    try:
        duration = int(str(value if value is not None else 5).removesuffix("s"))
    except (TypeError, ValueError) as exc:
        raise MiniMaxH3ValidationError(
            f"{PRODUCT_NAME}时长必须为 5、10 或 15 秒。"
        ) from exc
    if duration not in MINIMAX_H3_ALLOWED_DURATIONS:
        raise MiniMaxH3ValidationError(f"{PRODUCT_NAME}时长必须为 5、10 或 15 秒。")
    return duration


def get_minimax_h3_cost(
    task_type: str,
    *,
    duration: Any = 5,
    resolution_preset: Any = "preview",
) -> int:
    if task_type not in MINIMAX_H3_PUBLIC_TASK_TYPES:
        raise MiniMaxH3ValidationError(f"未知{PRODUCT_NAME}任务类型。")
    normalized_duration = normalize_minimax_h3_duration_seconds(duration)
    preset = str(resolution_preset or "preview").strip().lower()
    if preset not in MINIMAX_H3_PIXEL_PRESETS:
        raise MiniMaxH3ValidationError(
            "分辨率档位必须为 preview、small、standard 或 hd。"
        )
    matrix = (
        MINIMAX_H3_REF2V_PRICE_BY_DURATION
        if task_type == MINIMAX_H3_REF2V
        else MINIMAX_H3_NORMAL_PRICE_BY_DURATION
    )
    return matrix[normalized_duration][preset]


def _dimensions(preset: str, aspect_ratio: str) -> tuple[int, int]:
    target = min(MINIMAX_H3_PIXEL_PRESETS[preset], MINIMAX_H3_MAX_PIXELS)
    ratio = MINIMAX_H3_ASPECT_RATIOS[aspect_ratio]
    width = max(32, round(math.sqrt(target * ratio) / 32) * 32)
    height = max(32, round(math.sqrt(target / ratio) / 32) * 32)
    while width * height > MINIMAX_H3_MAX_PIXELS:
        if width >= height:
            width -= 32
        else:
            height -= 32
    return width, height


def _images(inputs: dict[str, Any]) -> tuple[str, ...]:
    value = inputs.get("saved_input_images")
    if value is None:
        value = inputs.get("images")
    if value is not None:
        return _string_tuple(value, field="images")
    return tuple(
        str(inputs.get(key) or "").strip()
        for key in ("image", "end_image")
        if str(inputs.get(key) or "").strip()
    )


def build_minimax_h3_spec(task_type: str, inputs: dict[str, Any]) -> MiniMaxH3Spec:
    if task_type not in MINIMAX_H3_PUBLIC_TASK_TYPES:
        raise MiniMaxH3ValidationError(f"未知{PRODUCT_NAME}任务类型。")
    forbidden = (
        "model_name",
        "checkpoint",
        "timeline_data",
        "local_path",
        "ref_videos",
        "ref_video_audios",
        "ref_audios",
        "sampler_name",
        "scheduler",
        "steps",
        "sigmas",
        "ref_image_size",
    )
    if any(inputs.get(key) not in (None, "", [], ()) for key in forbidden):
        raise MiniMaxH3ValidationError(f"{PRODUCT_NAME}不允许覆盖底层执行参数。")

    addon_items = normalize_minimax_h3_addon_items(
        inputs,
        mode=task_type.removeprefix("minimax_h3_"),
    )
    main_model = (
        str(inputs.get("main_model") or MINIMAX_H3_DEFAULT_MAIN_MODEL).strip().lower()
    )
    if main_model not in MINIMAX_H3_MAIN_MODELS:
        raise MiniMaxH3ValidationError("不支持该 MiniMax H3 主模型。")
    if (
        main_model == MINIMAX_H3_MAIN_MODEL_OFFICIAL_REF2V_TURBO
        and task_type != MINIMAX_H3_REF2V
    ):
        raise MiniMaxH3ValidationError("官方 REF2V 极速主模型仅支持参考图生视频。")

    duration = normalize_minimax_h3_duration_seconds(
        inputs.get("duration", inputs.get("length", 5))
    )
    preset = str(inputs.get("resolution_preset") or "preview").strip().lower()
    if preset not in MINIMAX_H3_PIXEL_PRESETS:
        raise MiniMaxH3ValidationError(
            "分辨率档位必须为 preview、small、standard 或 hd。"
        )

    images = _images(inputs)
    reference_video = str(inputs.get("reference_video") or "").strip() or None
    reference_audio = str(inputs.get("reference_audio") or "").strip() or None
    descriptions = _string_tuple(
        inputs.get("reference_descriptions"), field="reference_descriptions"
    )
    expected = {
        MINIMAX_H3_T2V: (0, 0, "t2v"),
        MINIMAX_H3_I2V: (1, 1, "i2v"),
        MINIMAX_H3_FLF2V: (2, 2, "flf2v"),
        MINIMAX_H3_REF2V: (0, 5, "ref2v"),
    }[task_type]
    minimum, maximum, mode = expected
    if not minimum <= len(images) <= maximum:
        if minimum == maximum:
            raise MiniMaxH3ValidationError(f"{mode} 必须提供恰好 {minimum} 张图片。")
        raise MiniMaxH3ValidationError(
            f"{mode} 必须提供 {minimum} 至 {maximum} 张有序图片。"
        )
    if any(not item for item in images):
        raise MiniMaxH3ValidationError(f"{PRODUCT_NAME}图片不得为空。")
    if task_type == MINIMAX_H3_REF2V:
        if not images and reference_video is None:
            raise MiniMaxH3ValidationError("ref2v 必须提供参考图片或参考视频。")
        if descriptions and (
            len(descriptions) != len(images) or any(not item for item in descriptions)
        ):
            raise MiniMaxH3ValidationError("参考说明必须与参考图片一一对应。")
    elif descriptions:
        raise MiniMaxH3ValidationError("当前模式不支持角色参考说明。")
    if reference_video is not None and task_type != MINIMAX_H3_REF2V:
        raise MiniMaxH3ValidationError("参考视频仅支持参考生视频。")
    if reference_audio is not None and task_type != MINIMAX_H3_REF2V:
        raise MiniMaxH3ValidationError("主角参考语音仅支持参考图生视频。")

    raw_aspect = str(inputs.get("aspect_ratio") or "").strip()
    if task_type in {MINIMAX_H3_I2V, MINIMAX_H3_FLF2V}:
        if raw_aspect and raw_aspect != "source":
            raise MiniMaxH3ValidationError("首帧模式必须跟随首帧原始比例。")
        aspect = "source"
        width, height = 0, 0
    else:
        aspect = raw_aspect or "16:9"
        if aspect == "source":
            raise MiniMaxH3ValidationError("该模式必须选择固定画面比例。")
        if aspect not in MINIMAX_H3_ASPECT_RATIOS:
            raise MiniMaxH3ValidationError("不支持该画面比例。")
        width, height = _dimensions(preset, aspect)
    return MiniMaxH3Spec(
        task_type=task_type,
        mode=mode,
        duration_seconds=duration,
        resolution_preset=preset,
        aspect_ratio=aspect,
        width=width,
        height=height,
        frame_count=MINIMAX_H3_FRAME_COUNTS[duration],
        fps=MINIMAX_H3_FPS,
        cost=get_minimax_h3_cost(
            task_type,
            duration=duration,
            resolution_preset=preset,
        ),
        images=images,
        reference_descriptions=descriptions,
        reference_video=reference_video,
        reference_audio=reference_audio,
        main_model=main_model,
        model_name=(
            MINIMAX_H3_OFFICIAL_MODEL_REF
            if main_model
            in {
                MINIMAX_H3_MAIN_MODEL_OFFICIAL,
                MINIMAX_H3_MAIN_MODEL_OFFICIAL_REF2V_TURBO,
            }
            and task_type == MINIMAX_H3_REF2V
            else MINIMAX_H3_OFFICIAL_MODEL_FL
            if main_model == MINIMAX_H3_MAIN_MODEL_OFFICIAL
            else MINIMAX_H3_MODEL_REF
            if task_type == MINIMAX_H3_REF2V
            else MINIMAX_H3_MODEL_FL
        ),
        addon_items=addon_items,
    )
