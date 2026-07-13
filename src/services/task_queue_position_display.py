from collections.abc import Mapping
from typing import Any


def select_display_queue_position(info: Mapping[str, Any]) -> Any:
    """Return the user-facing 0-based queue position from a status payload."""
    for key in ("queue_type_pos", "queue_pos"):
        value = info.get(key)
        if value is not None:
            return value
    return None
