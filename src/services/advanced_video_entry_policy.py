from __future__ import annotations

import os


_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


def _flag(name: str, *, test_default: bool = False) -> bool:
    configured = os.getenv(name)
    if configured is not None:
        return configured.strip().lower() in _TRUE_VALUES
    return test_default and os.getenv("ALLBOT_ENV", "").strip().lower() == "test"


def minimax_h3_backend_enabled() -> bool:
    """Whether direct H3 commands may use the backend in this environment."""

    return _flag("MINIMAX_H3_BACKEND_ENABLED", test_default=True)


def minimax_h3_ref2v_enabled() -> bool:
    return _flag("MINIMAX_H3_REF2V_ENABLED", test_default=True)


def minimax_h3_advanced_video_entry_enabled() -> bool:
    """Whether the H3 label is exposed in the ordinary Main Bot menu."""

    return minimax_h3_backend_enabled() and _flag(
        "MINIMAX_H3_ENTRY_ENABLED", test_default=False
    )


def active_advanced_video_menu_key() -> str:
    return (
        "menu.advanced_video_pro"
        if minimax_h3_advanced_video_entry_enabled()
        else "menu.ltx_video"
    )
