"""Deprecated compatibility layer for the legacy `video_lora_fsm` module.

New code should import and patch `src.handlers.fsm.image_to_video_fsm` directly.
This module is intentionally kept as a thin re-export surface during migration.
"""

from src.handlers.fsm.image_to_video_fsm import (
    VideoLoraState,
    get_image_to_video_fsm_handler,
    get_video_lora_fsm_handler,
    start_video_lora,
)

# Deprecated compatibility exports. Keep this file free of new logic and
# restrict it to the minimal legacy entry points still worth preserving.
__all__ = [
    "VideoLoraState",
    "get_image_to_video_fsm_handler",
    "get_video_lora_fsm_handler",
    "start_video_lora",
]
