"""QQCC lazy-bot Wan 2.2 LoRA catalog and normalization.

This module deliberately stays separate from the public catalog.  The main Bot
continues to expose its existing single-LoRA settings while QQCC scenes can
store an ordered list with per-model strengths.
"""

from __future__ import annotations

import math
from typing import Any

from src.lora_catalog import VIDEO_LORA_MODELS


QQCC_VIDEO_LORA_MODELS = {
    name: label for name, label in VIDEO_LORA_MODELS.items() if name
}

# Existing Wan 2.2 assets historically ran at 1.0.  Making that value explicit
# gives QQCC Config a recommendation source while still allowing per-scene edits.
QQCC_VIDEO_LORA_DEFAULT_STRENGTHS = {
    name: 1.0 for name in QQCC_VIDEO_LORA_MODELS
}


def normalize_qqcc_video_lora_strength(name: str, value: Any) -> float:
    default = QQCC_VIDEO_LORA_DEFAULT_STRENGTHS.get(name, 1.0)
    try:
        strength = default if value is None else float(value)
    except (TypeError, ValueError):
        strength = default
    if not math.isfinite(strength):
        strength = default
    return float(round(round(min(2.0, max(0.1, strength)) * 20) / 20, 2))


def normalize_qqcc_video_lora_items(
    raw_items: Any,
    *,
    legacy_name: Any = None,
    legacy_strength: Any = None,
    max_items: int = 5,
) -> list[dict[str, str | float]]:
    candidates = raw_items if isinstance(raw_items, list) else []
    if not candidates and isinstance(legacy_name, str) and legacy_name.strip():
        candidates = [{"name": legacy_name, "strength": legacy_strength}]

    normalized: list[dict[str, str | float]] = []
    seen: set[str] = set()
    for raw_item in candidates:
        if not isinstance(raw_item, dict):
            continue
        raw_name = raw_item.get("name", raw_item.get("path"))
        name = raw_name.strip() if isinstance(raw_name, str) else ""
        if name not in QQCC_VIDEO_LORA_MODELS or name in seen:
            continue
        seen.add(name)
        normalized.append(
            {
                "name": name,
                "strength": normalize_qqcc_video_lora_strength(
                    name, raw_item.get("strength")
                ),
            }
        )
        if len(normalized) >= max_items:
            break
    return normalized
