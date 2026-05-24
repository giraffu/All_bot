import re
from typing import Any

from src.constants import MODE_IMAGE_TO_VIDEO, VIDEO_TASK_TYPES


VIDEO_BILLING_TASK_TYPES = frozenset(VIDEO_TASK_TYPES)
LTX_ALLOWED_DURATIONS = (5, 10, 15, 20)
MAX_LEGACY_LTX_DURATION_DRIFT = 2
TIER_VIDEO_ALLOWED_DURATIONS = (5, 8, 10)
MAX_LEGACY_TIER_VIDEO_DURATION_DRIFT = 2
LEGACY_TIER_VIDEO_TASK_TYPES = frozenset({"custom_video", MODE_IMAGE_TO_VIDEO})


def _normalize_tier_from_video_side(side: int | None) -> str | None:
    if side is None or side <= 0:
        return None
    if side >= 960:
        return "1024"
    if side >= 700:
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
        return _normalize_tier_from_video_side(min(width, height))

    try:
        numeric = int(text)
    except ValueError:
        return None

    if numeric in (512, 720, 1024):
        return str(numeric)
    return _normalize_tier_from_video_side(numeric)


def normalize_requested_duration_seconds(duration: Any) -> int | None:
    if duration is None:
        return None

    text = str(duration).strip().lower()
    if not text:
        return None

    if text.endswith("s"):
        text = text[:-1]

    try:
        parsed = int(text)
    except ValueError:
        return None

    return parsed if parsed > 0 else None


def convert_ltx_seconds_to_length_frames(duration_seconds: Any) -> int:
    seconds = normalize_requested_duration_seconds(duration_seconds) or 5
    return seconds * 24 + 1


def infer_legacy_ltx_requested_duration(duration: Any) -> int | None:
    normalized = normalize_requested_duration_seconds(duration)
    if normalized is None:
        return None
    if normalized < LTX_ALLOWED_DURATIONS[0]:
        return None

    nearest = min(
        LTX_ALLOWED_DURATIONS,
        key=lambda candidate: abs(candidate - normalized),
    )
    if abs(nearest - normalized) > MAX_LEGACY_LTX_DURATION_DRIFT:
        return None
    return nearest


def infer_legacy_tier_video_requested_duration(duration: Any) -> int | None:
    normalized = normalize_requested_duration_seconds(duration)
    if normalized is None:
        return None
    if normalized < TIER_VIDEO_ALLOWED_DURATIONS[0]:
        return None

    nearest = min(
        TIER_VIDEO_ALLOWED_DURATIONS,
        key=lambda candidate: abs(candidate - normalized),
    )
    if abs(nearest - normalized) > MAX_LEGACY_TIER_VIDEO_DURATION_DRIFT:
        return None
    return nearest


def infer_legacy_video_requested_duration(
    task_type: str | None,
    duration: Any,
) -> int | None:
    if task_type == "ltx_video":
        return infer_legacy_ltx_requested_duration(duration)
    if task_type in LEGACY_TIER_VIDEO_TASK_TYPES:
        return infer_legacy_tier_video_requested_duration(duration)
    return None


def resolve_legacy_requested_duration(
    task_type: str | None,
    requested_duration: Any,
    duration: Any,
) -> int | None:
    if requested_duration is not None:
        return requested_duration
    return infer_legacy_video_requested_duration(task_type, duration)


def resolve_apply_prompt_and_requested_duration(
    task_type: str | None,
    prompt: str | None,
    requested_duration: Any,
) -> tuple[str, int | None]:
    resolved_prompt = prompt or ""
    if task_type == "ltx_video":
        _, _, resolved_prompt = extract_video_prompt_prefix(resolved_prompt)
    return resolved_prompt, requested_duration


def extract_video_prompt_prefix(
    prompt: str | None,
) -> tuple[str | None, int | None, str]:
    raw_prompt = (prompt or "").strip()
    match = re.match(r"^\[(?P<resolution>[^|\]]+)\|(?P<duration>[^\]]+)\]\s*(?P<body>.*)$", raw_prompt, re.DOTALL)
    if not match:
        return None, None, raw_prompt

    resolution = match.group("resolution").strip() or None
    duration = normalize_requested_duration_seconds(match.group("duration"))
    clean_prompt = match.group("body").strip()
    return resolution, duration, clean_prompt


def infer_billing_resolution_from_dimensions(
    width: int | None,
    height: int | None,
    task_type: str | None = None,
) -> str | None:
    if not is_video_billing_task_type(task_type):
        return None

    if task_type == "ltx_video" and width and height:
        return f"{width}x{height}"

    inferred_side = None
    if width and height:
        inferred_side = min(width, height)
    else:
        inferred_side = width or height or None
    return _normalize_tier_from_video_side(inferred_side)
