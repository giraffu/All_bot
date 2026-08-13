from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


MINIMAX_H3_T2V = "minimax_h3_t2v"
MINIMAX_H3_I2V = "minimax_h3_i2v"
MINIMAX_H3_FLF2V = "minimax_h3_flf2v"
MINIMAX_H3_REF2V = "minimax_h3_ref2v"
MINIMAX_H3_TASK_TYPES = (
    MINIMAX_H3_T2V,
    MINIMAX_H3_I2V,
    MINIMAX_H3_FLF2V,
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
MINIMAX_H3_NORMAL_PRICE_BY_PRESET = {
    "preview": 10,
    "small": 15,
    "standard": 20,
    "hd": 30,
}
MINIMAX_H3_REFERENCE_PRICE_BY_PRESET = {
    "preview": 12,
    "small": 18,
    "standard": 24,
    "hd": 36,
}
MINIMAX_H3_ASPECT_RATIOS = {
    "16:9": 16 / 9,
    "9:16": 9 / 16,
    "1:1": 1.0,
    "4:3": 4 / 3,
    "3:4": 3 / 4,
}
MINIMAX_H3_MAX_PIXELS = 768 * 1344
MINIMAX_H3_MODEL_FL = "MiniMaxH3/minimax_h3_fl2va_pruned_bf16.safetensors"
MINIMAX_H3_MODEL_REF = "MiniMaxH3/minimax_h3_ref2va_pruned_int8_convrot.safetensors"
MINIMAX_H3_ADDON_MIN_STRENGTH = 0.1
MINIMAX_H3_ADDON_MAX_STRENGTH = 2.0


@dataclass(frozen=True, slots=True)
class MiniMaxH3AddonModel:
    id: str
    label_zh: str
    label_en: str
    model_paths: tuple[str, ...]
    relative_strengths: tuple[float, ...]
    default_strength: float
    prompt_prefix: str
    strength_hint_zh: str
    strength_hint_en: str
    prompt_guide_zh: str
    prompt_guide_en: str


@dataclass(frozen=True, slots=True)
class MiniMaxH3AddonSelection:
    name: str
    strength: float


MINIMAX_H3_ADDON_MODELS = {
    "breasts": MiniMaxH3AddonModel(
        "breasts", "乳房", "Breasts",
        ("MiniMaxH3/HMBreasts_085e0750_e40.safetensors",), (1.0,), 1.0, "HMBreasts",
        "默认 1.0；可按画面效果在允许范围内调整。", "Default 1.0; adjust within the allowed range to suit the result.",
        "写明乳房尺寸与形状、乳晕尺寸与颜色、乳头状态；使用 areoles 拼写。",
        "Describe breast size and shape, areole size and color, and nipple state; use the spelling “areoles”.",
    ),
    "anus": MiniMaxH3AddonModel(
        "anus", "肛门", "Anus",
        ("MiniMaxH3/vagassist_e40.safetensors", "MiniMaxH3/hmpussy_v6_epoch30.safetensors"),
        (1.0, 0.35), 1.0, "Vagina, hmpussy, anus",
        "推荐 1.0。",
        "Recommended 1.0.",
        "描述肛门在画面中的方向、结构细节与运动；两份 LoRA 及触发词会自动组合。",
        "Describe the anus direction in frame, structural detail, and motion; both LoRAs and their triggers are combined automatically.",
    ),
    "vagina": MiniMaxH3AddonModel(
        "vagina", "阴道", "Vagina",
        ("MiniMaxH3/vagassist_e40.safetensors", "MiniMaxH3/hmpussy_v6_epoch30.safetensors"),
        (1.0, 0.35), 1.0, "Vagina, hmpussy",
        "推荐 1.0。",
        "Recommended 1.0.",
        "描述阴道在画面中的方向、结构细节与运动；两份 LoRA 及触发词会自动组合。",
        "Describe the vagina direction in frame, structural detail, and motion; both LoRAs and their triggers are combined automatically.",
    ),
    "sex_pose": MiniMaxH3AddonModel(
        "sex_pose", "性爱姿势", "Sex pose",
        ("MiniMaxH3/HMNSFW_AIO_V2.safetensors",), (1.0,), 0.5, "hmmotion",
        "建议 0.5 或更低；默认 0.5。", "Recommended 0.5 or lower; default 0.5.",
        "优先使用图生视频；建议约 200–270 个英文单词，依次描述动作、视角、速度、景别、人物、画面位置、运动、表面状态和环境音。",
        "Prefer image-to-video; use about 200–270 English words covering action, viewpoint, pace, shot type, people, frame position, motion, surface state, and ambience.",
    ),
    "penis": MiniMaxH3AddonModel(
        "penis", "阴茎", "Penis",
        ("MiniMaxH3/HMPenis_v2_e35.safetensors",), (1.0,), 1.0, "HMPenis",
        "默认 1.0；可按画面效果在允许范围内调整。", "Default 1.0; adjust within the allowed range to suit the result.",
        "写明正面、背面或侧面方向，并描述尺寸、是否包皮环切及龟头颜色。",
        "Specify front, back, or side direction, plus size, circumcision, and glans color.",
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
    model_name: str
    addon_items: tuple[MiniMaxH3AddonSelection, ...]

    @property
    def addon_model(self) -> str | None:
        return self.addon_items[0].name if len(self.addon_items) == 1 else None

    @property
    def addon_strength(self) -> float | None:
        return self.addon_items[0].strength if len(self.addon_items) == 1 else None


def _addon_items(inputs: dict[str, Any]) -> tuple[MiniMaxH3AddonSelection, ...]:
    raw_items = inputs.get("lora_items")
    legacy_name = str(inputs.get("lora_name") or "").strip()
    legacy_strength = inputs.get("lora_strength")
    if raw_items is not None and (legacy_name or legacy_strength not in (None, "")):
        raise MiniMaxH3ValidationError("lora_items 不能与旧版单模型参数同时使用。")
    if raw_items is None:
        if not legacy_name:
            if legacy_strength not in (None, ""):
                raise MiniMaxH3ValidationError("选择附加模型后才能设置强度。")
            return ()
        raw_items = [{"name": legacy_name, "strength": legacy_strength}]
    if not isinstance(raw_items, (list, tuple)) or len(raw_items) > len(MINIMAX_H3_ADDON_MODELS):
        raise MiniMaxH3ValidationError("附加模型必须为最多 5 项的数组。")
    result: list[MiniMaxH3AddonSelection] = []
    seen: set[str] = set()
    for raw in raw_items:
        if not isinstance(raw, dict):
            raise MiniMaxH3ValidationError("附加模型配置格式错误。")
        name = str(raw.get("name") or "").strip()
        model = MINIMAX_H3_ADDON_MODELS.get(name)
        if model is None:
            raise MiniMaxH3ValidationError("不支持该附加模型。")
        if name in seen:
            raise MiniMaxH3ValidationError("附加模型不得重复选择。")
        seen.add(name)
        raw_strength = raw.get("strength")
        try:
            strength = model.default_strength if raw_strength in (None, "") else float(raw_strength)
        except (TypeError, ValueError) as exc:
            raise MiniMaxH3ValidationError("附加模型强度必须为数字。") from exc
        if not math.isfinite(strength) or not MINIMAX_H3_ADDON_MIN_STRENGTH <= strength <= MINIMAX_H3_ADDON_MAX_STRENGTH:
            raise MiniMaxH3ValidationError("附加模型强度必须在 0.1 至 2.0 之间。")
        result.append(MiniMaxH3AddonSelection(name, strength))
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
        raise MiniMaxH3ValidationError(f"{PRODUCT_NAME}时长必须为 5、10 或 15 秒。") from exc
    if duration not in MINIMAX_H3_ALLOWED_DURATIONS:
        raise MiniMaxH3ValidationError(f"{PRODUCT_NAME}时长必须为 5、10 或 15 秒。")
    return duration


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
    if task_type not in MINIMAX_H3_TASK_TYPES:
        raise MiniMaxH3ValidationError(f"未知{PRODUCT_NAME}任务类型。")
    forbidden = (
        "model_name", "checkpoint", "timeline_data",
        "local_path", "ref_videos", "ref_audios", "sampler_name", "steps",
    )
    if any(inputs.get(key) not in (None, "", [], ()) for key in forbidden):
        raise MiniMaxH3ValidationError(f"{PRODUCT_NAME}不允许覆盖底层执行参数。")

    addon_items = _addon_items(inputs)
    if task_type == MINIMAX_H3_REF2V and addon_items:
        raise MiniMaxH3ValidationError("ref2v 不支持附加模型。")

    duration = normalize_minimax_h3_duration_seconds(
        inputs.get("duration", inputs.get("length", 5))
    )
    preset = str(inputs.get("resolution_preset") or "preview").strip().lower()
    if preset not in MINIMAX_H3_PIXEL_PRESETS:
        raise MiniMaxH3ValidationError(
            "分辨率档位必须为 preview、small、standard 或 hd。"
        )

    images = _images(inputs)
    descriptions = _string_tuple(
        inputs.get("reference_descriptions"), field="reference_descriptions"
    )
    expected = {
        MINIMAX_H3_T2V: (0, 0, "t2v"),
        MINIMAX_H3_I2V: (1, 1, "i2v"),
        MINIMAX_H3_FLF2V: (2, 2, "flf2v"),
        MINIMAX_H3_REF2V: (1, 4, "ref2v"),
    }[task_type]
    minimum, maximum, mode = expected
    if not minimum <= len(images) <= maximum:
        if minimum == maximum:
            raise MiniMaxH3ValidationError(f"{mode} 必须提供恰好 {minimum} 张图片。")
        raise MiniMaxH3ValidationError("ref2v 必须提供 1 至 4 张有序角色参考图。")
    if any(not item for item in images):
        raise MiniMaxH3ValidationError(f"{PRODUCT_NAME}图片不得为空。")
    if task_type != MINIMAX_H3_REF2V and descriptions:
        raise MiniMaxH3ValidationError("仅 ref2v 支持角色参考说明。")
    if descriptions and len(descriptions) != len(images):
        raise MiniMaxH3ValidationError("角色参考说明数量必须与参考图数量一致。")
    if any(not item for item in descriptions):
        raise MiniMaxH3ValidationError("角色参考说明不得为空。")

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
    multiplier = duration // 5
    base_cost = (
        MINIMAX_H3_REFERENCE_PRICE_BY_PRESET[preset]
        if task_type == MINIMAX_H3_REF2V
        else MINIMAX_H3_NORMAL_PRICE_BY_PRESET[preset]
    )
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
        cost=base_cost * multiplier,
        images=images,
        reference_descriptions=descriptions,
        model_name=(MINIMAX_H3_MODEL_REF if task_type == MINIMAX_H3_REF2V else MINIMAX_H3_MODEL_FL),
        addon_items=addon_items,
    )
