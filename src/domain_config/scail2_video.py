from __future__ import annotations

from typing import Any


SCAIL2_ACTION_TRANSFER_TASK_TYPE = "scail2_action_transfer"
SCAIL2_VIDEO_REPLACEMENT_TASK_TYPE = "scail2_video_replacement"
SCAIL2_TASK_TYPES = frozenset(
    {
        SCAIL2_ACTION_TRANSFER_TASK_TYPE,
        SCAIL2_VIDEO_REPLACEMENT_TASK_TYPE,
    }
)

SCAIL2_DEFAULT_DURATION_SECONDS = 5
SCAIL2_ALLOWED_DURATION_SECONDS = (5, 8)
SCAIL2_FRAME_COUNT_BY_DURATION_SECONDS = {
    5: 81,
    8: 129,
}
SCAIL2_COST_BY_DURATION_SECONDS = {
    5: 40,
    8: 80,
}
SCAIL2_FIXED_WIDTH = 512
SCAIL2_FIXED_HEIGHT = 896
SCAIL2_FORCE_RATE = 16
SCAIL2_SKIP_FIRST_FRAMES = 0

SCAIL2_DEFAULT_NEGATIVE_PROMPT = (
    "色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，"
    "静止，整体发灰，最差质量，低质量，JPEG压缩残留，丑陋的，残缺的，"
    "多余的手指，画得不好的手部，画得不好的脸部，畸形的，毁容的，"
    "形态畸形的肢体，手指融合，静止不动的画面，杂乱的背景，三条腿，"
    "背景人很多，倒着走"
)


class Scail2DurationError(ValueError):
    pass


def is_scail2_task_type(task_type: str | None) -> bool:
    return str(task_type or "").strip() in SCAIL2_TASK_TYPES


def normalize_scail2_duration_seconds(
    value: Any,
    *,
    strict: bool = False,
) -> int:
    if value in (None, ""):
        return SCAIL2_DEFAULT_DURATION_SECONDS

    text = str(value).strip().lower()
    if text.endswith("s"):
        text = text[:-1]

    try:
        duration_seconds = int(text)
    except (TypeError, ValueError) as exc:
        if strict:
            raise Scail2DurationError("SCAIL-2 only supports 5s or 8s duration.") from exc
        return SCAIL2_DEFAULT_DURATION_SECONDS

    if duration_seconds in SCAIL2_ALLOWED_DURATION_SECONDS:
        return duration_seconds

    if strict:
        raise Scail2DurationError("SCAIL-2 only supports 5s or 8s duration.")
    return SCAIL2_DEFAULT_DURATION_SECONDS


def get_scail2_frame_count(duration_seconds: Any, *, strict: bool = False) -> int:
    normalized = normalize_scail2_duration_seconds(duration_seconds, strict=strict)
    return SCAIL2_FRAME_COUNT_BY_DURATION_SECONDS[normalized]


def get_scail2_cost(duration_seconds: Any, *, strict: bool = False) -> int:
    normalized = normalize_scail2_duration_seconds(duration_seconds, strict=strict)
    return SCAIL2_COST_BY_DURATION_SECONDS[normalized]


def normalize_scail2_negative_prompt(value: Any) -> str:
    text = str(value or "").strip()
    return text or SCAIL2_DEFAULT_NEGATIVE_PROMPT
