"""QQCC lazy-bot Wan 2.2 LoRA catalog and normalization.

This module deliberately stays separate from the public catalog.  The main Bot
continues to expose its existing single-LoRA settings while QQCC scenes can
store an ordered list with per-model strengths.
"""

from __future__ import annotations

import math
from typing import Any

from src.wan22_explicit_lora_catalog import WAN22_EXPLICIT_LORA_MODELS


QQCC_VIDEO_LORA_MODELS = {
    name: str(item["label"]) for name, item in WAN22_EXPLICIT_LORA_MODELS.items()
}

QQCC_VIDEO_LORA_DEFAULT_STRENGTHS = {
    name: float(item["default_strength"])
    for name, item in WAN22_EXPLICIT_LORA_MODELS.items()
}

# Upgrade existing QQCC scenes from the old seven-prefix menu to the closest
# downloaded pair.  These aliases are accepted on input but never returned in
# the new 49-item options catalog.
QQCC_VIDEO_LORA_LEGACY_ALIASES = {
    "BreastGrow": "wan22_explicit_077",
    "BreastInsertion": "wan22_explicit_088",
    "Cum": "wan22_explicit_008",
    "Cunilingus": "wan22_explicit_069",
    "Flatchested": "wan22_explicit_164",
    "Footjob": "wan22_explicit_040",
    "Insertion": "wan22_explicit_010",
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
        name = QQCC_VIDEO_LORA_LEGACY_ALIASES.get(name, name)
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
