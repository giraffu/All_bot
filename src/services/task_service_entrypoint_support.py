from collections.abc import Iterable
from typing import Any, Callable

from src.core.video_billing import normalize_requested_billing_resolution


def build_task_inputs(
    *,
    prompt: str,
    images: list[str],
    resolution: Any,
    duration: Any,
    **extra_fields: Any,
) -> dict[str, Any]:
    return {
        "prompt": prompt,
        "images": images,
        "resolution": resolution,
        "duration": duration,
        **extra_fields,
    }


def resolve_video_billing_args(
    *,
    is_video: bool,
    resolution: Any,
    task_type: str,
    duration: Any = None,
    include_requested_duration: bool = True,
    allowed_task_types: set[str] | tuple[str, ...] | None = None,
    duration_transform: Callable[[Any], Any] | None = None,
) -> dict[str, Any]:
    if not is_video:
        return {"billing_resolution": None, "requested_duration": None}

    requested_duration = None
    allow_duration = include_requested_duration and (
        allowed_task_types is None or task_type in allowed_task_types
    )
    if allow_duration:
        requested_duration = duration_transform(duration) if duration_transform else duration

    return {
        "billing_resolution": normalize_requested_billing_resolution(resolution, task_type),
        "requested_duration": requested_duration,
    }


def build_log_prompt(
    prompt: str,
    *,
    resolution: Any = None,
    duration: Any = None,
    lora_name: str | None = None,
    task_type: str | None = None,
    lora_task_types: set[str] | tuple[str, ...] | None = None,
) -> str:
    result = prompt
    if lora_name and lora_task_types and task_type in lora_task_types:
        result = f"[模型: {lora_name}] {result}"
    if resolution is not None and duration is not None:
        result = f"[{resolution}|{duration}] {result}"
    return result


def build_cleanup_paths(paths: Iterable[str | None]) -> list[str] | None:
    cleaned = [path for path in paths if path]
    return cleaned or None


def build_unexpected_error_log_message(task_label: str, *, verb: str = "in") -> str:
    if verb == "processing":
        return f"Error processing {task_label} for {{internal_user_id}}: {{error}}"
    return f"Error in {task_label} for user {{internal_user_id}}: {{error}}"
