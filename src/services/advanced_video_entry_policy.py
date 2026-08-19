from __future__ import annotations

import os


_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


def minimax_h3_advanced_video_entry_enabled() -> bool:
    """Match the Bot entry to the environment's H3 backend capability."""

    configured = os.getenv("MINIMAX_H3_BACKEND_ENABLED")
    if configured is not None:
        return configured.strip().lower() in _TRUE_VALUES
    return os.getenv("ALLBOT_ENV", "").strip().lower() == "test"


def active_advanced_video_menu_key() -> str:
    return (
        "menu.advanced_video_pro"
        if minimax_h3_advanced_video_entry_enabled()
        else "menu.ltx_video"
    )
