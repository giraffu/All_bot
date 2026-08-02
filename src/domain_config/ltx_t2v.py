from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any


LTX_T2V_TASK_TYPE = "ltx_t2v"
LTX_T2V_IC_TASK_TYPE = "ltx_t2v_ic"
CHARACTER_REFERENCE_BUILD_TASK_TYPE = "character_reference_build"

LTX_T2V_WIDTH = 1280
LTX_T2V_HEIGHT = 704
LTX_T2V_IC_WIDTH = 768
LTX_T2V_IC_HEIGHT = 448
LTX_T2V_FPS = 24
LTX_T2V_ALLOWED_DURATIONS = (5, 10, 15, 20)
LTX_T2V_COST_BY_DURATION = {5: 10, 10: 20, 15: 30, 20: 40}
LTX_T2V_IC_COST_BY_DURATION = {5: 12, 10: 24, 15: 36, 20: 48}
CHARACTER_REFERENCE_BUILD_COST = 18

DISTILLED_LORA_NAME = "ltx-2.3-22b-distilled-lora-384-1.1.safetensors"
DISTILLED_LORA_STRENGTH = 0.5
SULPHUR_LORA_NAME = "sulphur_lora_rank_768.safetensors"
SULPHUR_LORA_STRENGTH = 1.0
INGREDIENTS_LORA_NAME = "ltx-2.3-22b-ic-lora-ingredients-0.9.safetensors"
INGREDIENTS_LORA_STRENGTH = 1.0
MSR_LORA_NAME = "LTX-2.3-Licon-MSR-V2.safetensors"
MSR_LORA_STRENGTH = 1.0
MSR_MIN_CHARACTERS = 2
MSR_MAX_CHARACTERS = 4
MSR_DEFAULT_SULPHUR_STRENGTH = 0.5


class LtxT2VValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class LtxT2VSpec:
    task_type: str
    duration_seconds: int
    width: int
    height: int
    frame_count: int
    fps: int
    cost: int
    character_sheet: str | None
    character_description: str | None
    character_sheets: tuple[str, ...] = ()
    character_descriptions: tuple[str, ...] = ()
    sulphur_strength: float | None = None

    @property
    def uses_msr(self) -> bool:
        return bool(self.character_sheets)


def _duration(value: Any) -> int:
    try:
        return int(str(value if value is not None else 5).removesuffix("s"))
    except (TypeError, ValueError) as exc:
        raise LtxT2VValidationError("文生视频时长必须为 5、10、15 或 20 秒。") from exc


def _string_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise LtxT2VValidationError("多人物输入必须使用有序数组。")
    return tuple(str(item or "").strip() for item in value)


def _sulphur_strength(value: Any) -> float:
    try:
        strength = float(value)
    except (TypeError, ValueError) as exc:
        raise LtxT2VValidationError("Sulphur 强度必须为 0 到 1。") from exc
    if not math.isfinite(strength) or not 0 <= strength <= 1:
        raise LtxT2VValidationError("Sulphur 强度必须为 0 到 1。")
    return strength


def build_ltx_t2v_spec(task_type: str, inputs: dict[str, Any]) -> LtxT2VSpec:
    if inputs.get("lora_name") or inputs.get("lora_items"):
        raise LtxT2VValidationError("当前文生视频固定模型栈不支持额外 LoRA。")

    duration = _duration(inputs.get("duration", inputs.get("length", 5)))
    character_sheet = str(inputs.get("character_sheet") or "").strip() or None
    character_description = (
        str(inputs.get("character_description") or "").strip() or None
    )
    character_sheets = _string_tuple(inputs.get("character_sheets"))
    character_descriptions = _string_tuple(inputs.get("character_descriptions"))
    has_multi_input = bool(character_sheets or character_descriptions)
    sulphur_strength: float | None = None
    if task_type == LTX_T2V_IC_TASK_TYPE:
        if duration not in LTX_T2V_ALLOWED_DURATIONS:
            raise LtxT2VValidationError(
                "人物一致性文生视频时长必须为 5、10、15 或 20 秒。"
            )
        if has_multi_input:
            if character_sheet or character_description:
                raise LtxT2VValidationError("单人物与多人物参考输入不能同时提交。")
            if not MSR_MIN_CHARACTERS <= len(character_sheets) <= MSR_MAX_CHARACTERS:
                raise LtxT2VValidationError(
                    "MSR 多人物模式需要 2 至 4 张角色四视图面板。"
                )
            if len(character_descriptions) != len(character_sheets):
                raise LtxT2VValidationError("人物参考表与人物描述必须一一对应。")
            if not all(character_sheets) or not all(character_descriptions):
                raise LtxT2VValidationError("人物参考表与人物描述不得为空。")
            sulphur_strength = _sulphur_strength(
                inputs.get("sulphur_strength", MSR_DEFAULT_SULPHUR_STRENGTH)
            )
        else:
            if not character_sheet:
                raise LtxT2VValidationError(
                    "人物一致性文生视频缺少已就绪的人物参考表。"
                )
            if not character_description:
                raise LtxT2VValidationError("人物一致性文生视频缺少人物描述。")
            if inputs.get("sulphur_strength") is not None:
                raise LtxT2VValidationError("Sulphur 强度仅用于 MSR 多人物模式。")
        width, height, cost = (
            LTX_T2V_IC_WIDTH,
            LTX_T2V_IC_HEIGHT,
            LTX_T2V_IC_COST_BY_DURATION[duration],
        )
    elif task_type == LTX_T2V_TASK_TYPE:
        if has_multi_input:
            raise LtxT2VValidationError("普通文生视频不得携带多人物参考输入。")
        if character_sheet:
            raise LtxT2VValidationError("普通文生视频不得携带人物参考表。")
        if character_description:
            raise LtxT2VValidationError("普通文生视频不得携带人物描述。")
        if duration not in LTX_T2V_ALLOWED_DURATIONS:
            raise LtxT2VValidationError("文生视频时长必须为 5、10、15 或 20 秒。")
        width, height, cost = (
            LTX_T2V_WIDTH,
            LTX_T2V_HEIGHT,
            LTX_T2V_COST_BY_DURATION[duration],
        )
    else:
        raise LtxT2VValidationError(f"未知 LTX 文生视频任务类型: {task_type}")

    resolution = str(inputs.get("resolution") or f"{width}x{height}")
    if resolution != f"{width}x{height}":
        raise LtxT2VValidationError(f"{task_type} 仅支持 {width}x{height}。")
    return LtxT2VSpec(
        task_type=task_type,
        duration_seconds=duration,
        width=width,
        height=height,
        frame_count=LTX_T2V_FPS * duration + 1,
        fps=LTX_T2V_FPS,
        cost=cost,
        character_sheet=character_sheet,
        character_description=character_description,
        character_sheets=character_sheets,
        character_descriptions=character_descriptions,
        sulphur_strength=sulphur_strength,
    )
