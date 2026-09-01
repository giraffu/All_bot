import math

from .models import TaskType


CATALOG = {
    "image_upscale": {
        "media_kind": "image",
        "multipliers": {"2": 2, "4": 4},
        "billing_unit": "item",
    },
    "video_upscale": {
        "media_kind": "video",
        "multipliers": {"2": 5},
        "billing_unit": "started_10_seconds",
    },
    "frame_interpolation": {
        "media_kind": "video",
        "multipliers": {"2": 3, "4": 5},
        "billing_unit": "started_10_seconds",
    },
}

PUBLIC_SERVICE_TYPES = ("video_upscale",)

PACKAGES = [
    {"points": 100, "price_cny": 9.9},
    {"points": 600, "price_cny": 49},
    {"points": 1500, "price_cny": 99},
]


def quote_points(
    task_type: TaskType | str,
    multiplier: int,
    duration_seconds: float | None = None,
) -> int:
    task_key = task_type.value if isinstance(task_type, TaskType) else task_type
    try:
        item = CATALOG[task_key]
        rate = item["multipliers"][str(multiplier)]
    except KeyError as exc:
        raise ValueError("unsupported processing preset") from exc
    if item["billing_unit"] == "item":
        return int(rate)
    if duration_seconds is None or duration_seconds <= 0:
        raise ValueError("video duration is required")
    return math.ceil(duration_seconds / 10) * int(rate)


def public_catalog() -> dict:
    return {
        "services": {key: CATALOG[key] for key in PUBLIC_SERVICE_TYPES},
        "packages": PACKAGES,
        "purchases_enabled": False,
    }
