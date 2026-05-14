from typing import Any

from src.constants import VIDEO_TASK_TYPES


VIDEO_BILLING_TASK_TYPES = frozenset(VIDEO_TASK_TYPES)


def _normalize_tier_from_longest_side(longest_side: int | None) -> str | None:
    if longest_side is None or longest_side <= 0:
        return None
    if longest_side >= 960:
        return "1024"
    if longest_side >= 700:
        return "720"
    return "512"


def is_video_billing_task_type(task_type: str | None) -> bool:
    return bool(task_type and task_type in VIDEO_BILLING_TASK_TYPES)


def normalize_requested_billing_resolution(
    resolution: Any, task_type: str | None = None
) -> str | None:
    if resolution is None:
        return None

    text = str(resolution).strip().lower()
    if not text:
        return None

    if text.endswith("p"):
        text = text[:-1]

    if "x" in text:
        try:
            width_text, height_text = text.split("x", 1)
            width = int(width_text)
            height = int(height_text)
        except ValueError:
            return None

        if task_type == "ltx_video":
            return f"{width}x{height}"
        return _normalize_tier_from_longest_side(max(width, height))

    try:
        numeric = int(text)
    except ValueError:
        return None

    if numeric in (512, 720, 1024):
        return str(numeric)
    return _normalize_tier_from_longest_side(numeric)


def infer_billing_resolution_from_dimensions(
    width: int | None,
    height: int | None,
    task_type: str | None = None,
) -> str | None:
    if not is_video_billing_task_type(task_type):
        return None

    if task_type == "ltx_video" and width and height:
        return f"{width}x{height}"

    longest_side = max(width or 0, height or 0) or None
    return _normalize_tier_from_longest_side(longest_side)
