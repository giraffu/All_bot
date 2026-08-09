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
    "preview": 300_000,
    "standard": 520_000,
    "hd": 830_000,
}
MINIMAX_H3_ASPECT_RATIOS = {
    "16:9": 16 / 9,
    "9:16": 9 / 16,
    "1:1": 1.0,
    "4:3": 4 / 3,
    "3:4": 3 / 4,
}
MINIMAX_H3_MAX_PIXELS = 768 * 1344
MINIMAX_H3_MODEL_FL = "MiniMaxH3/minimax_h3_fl2va_pruned_int8_convrot.safetensors"
MINIMAX_H3_MODEL_REF = "MiniMaxH3/minimax_h3_ref2va_pruned_int8_convrot.safetensors"


class MiniMaxH3ValidationError(ValueError):
    pass


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


def _string_tuple(value: Any, *, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise MiniMaxH3ValidationError(f"{field} 必须使用有序数组。")
    return tuple(str(item or "").strip() for item in value)


def _duration(value: Any) -> int:
    try:
        duration = int(str(value if value is not None else 5).removesuffix("s"))
    except (TypeError, ValueError) as exc:
        raise MiniMaxH3ValidationError("MiniMax H3 时长必须为 5、10 或 15 秒。") from exc
    if duration not in MINIMAX_H3_ALLOWED_DURATIONS:
        raise MiniMaxH3ValidationError("MiniMax H3 时长必须为 5、10 或 15 秒。")
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
        raise MiniMaxH3ValidationError(f"未知 MiniMax H3 任务类型: {task_type}")
    forbidden = (
        "lora_name", "lora_items", "model_name", "checkpoint", "timeline_data",
        "local_path", "ref_videos", "ref_audios", "sampler_name", "steps",
    )
    if any(inputs.get(key) not in (None, "", [], ()) for key in forbidden):
        raise MiniMaxH3ValidationError("MiniMax H3 不允许覆盖模型、LoRA、采样器或 timeline。")

    duration = _duration(inputs.get("duration", inputs.get("length", 5)))
    preset = str(inputs.get("resolution_preset") or "preview").strip().lower()
    if preset not in MINIMAX_H3_PIXEL_PRESETS:
        raise MiniMaxH3ValidationError("分辨率档位必须为 preview、standard 或 hd。")
    aspect = str(inputs.get("aspect_ratio") or "16:9").strip()
    if aspect not in MINIMAX_H3_ASPECT_RATIOS:
        raise MiniMaxH3ValidationError("不支持该画面比例。")

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
        raise MiniMaxH3ValidationError("MiniMax H3 图片对象键不得为空。")
    if task_type != MINIMAX_H3_REF2V and descriptions:
        raise MiniMaxH3ValidationError("仅 ref2v 支持角色参考说明。")
    if descriptions and len(descriptions) != len(images):
        raise MiniMaxH3ValidationError("角色参考说明数量必须与参考图数量一致。")
    if any(not item for item in descriptions):
        raise MiniMaxH3ValidationError("角色参考说明不得为空。")

    width, height = _dimensions(preset, aspect)
    multiplier = duration // 5
    base_cost = 12 if task_type == MINIMAX_H3_REF2V else 10
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
    )
