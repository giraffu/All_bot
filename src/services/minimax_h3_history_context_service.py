from __future__ import annotations

from typing import Any

from src.domain_config.minimax_h3 import (
    MINIMAX_H3_ALLOWED_DURATIONS,
    MINIMAX_H3_FLF2V,
    MINIMAX_H3_I2V,
    MINIMAX_H3_PIXEL_PRESETS,
    MiniMaxH3ValidationError,
    normalize_minimax_h3_addon_items,
)


MINIMAX_H3_HISTORY_CONTEXT_KEY = "_minimax_h3_context"
MINIMAX_H3_HISTORY_CONTEXT_VERSION = 1
MINIMAX_H3_GALLERY_TASK_TYPES = frozenset({MINIMAX_H3_I2V, MINIMAX_H3_FLF2V})
_MODE_BY_TASK_TYPE = {
    MINIMAX_H3_I2V: "i2v",
    MINIMAX_H3_FLF2V: "flf2v",
}


def is_minimax_h3_gallery_task_type(task_type: str | None) -> bool:
    return str(task_type or "").strip() in MINIMAX_H3_GALLERY_TASK_TYPES


def build_minimax_h3_history_context(
    *,
    task_type: str | None,
    metadata: dict[str, Any] | None,
) -> dict[str, object]:
    normalized_task_type = str(task_type or "").strip()
    expected_mode = _MODE_BY_TASK_TYPE.get(normalized_task_type)
    if expected_mode is None:
        return {}
    metadata = metadata or {}
    mode = str(metadata.get("minimax_h3_mode") or "").strip()
    resolution_preset = str(
        metadata.get("minimax_h3_resolution_preset") or ""
    ).strip()
    aspect_ratio = str(metadata.get("minimax_h3_aspect_ratio") or "").strip()
    try:
        requested_duration = int(metadata.get("requested_duration"))
    except (TypeError, ValueError):
        return {}
    if (
        mode != expected_mode
        or requested_duration not in MINIMAX_H3_ALLOWED_DURATIONS
        or resolution_preset not in MINIMAX_H3_PIXEL_PRESETS
        or aspect_ratio != "source"
    ):
        return {}
    try:
        addon_items = normalize_minimax_h3_addon_items(
            {"lora_items": metadata.get("lora_items") or []},
            mode=expected_mode,
        )
    except MiniMaxH3ValidationError:
        return {}
    return {
        "version": MINIMAX_H3_HISTORY_CONTEXT_VERSION,
        "mode": mode,
        "requested_duration": requested_duration,
        "resolution_preset": resolution_preset,
        "aspect_ratio": aspect_ratio,
        "lora_items": [
            {"name": item.name, "strength": item.strength} for item in addon_items
        ],
    }


def extract_minimax_h3_history_context(
    extra_outputs: dict[str, object] | None,
) -> dict[str, object]:
    if not isinstance(extra_outputs, dict):
        return {}
    context = extra_outputs.get(MINIMAX_H3_HISTORY_CONTEXT_KEY)
    if not isinstance(context, dict):
        return {}
    if context.get("version") != MINIMAX_H3_HISTORY_CONTEXT_VERSION:
        return {}
    return dict(context)


def resolve_valid_minimax_h3_history_context(
    *, task_type: str | None, extra_outputs: dict[str, object] | None
) -> dict[str, object]:
    context = extract_minimax_h3_history_context(extra_outputs)
    if not context:
        return {}
    rebuilt = build_minimax_h3_history_context(
        task_type=task_type,
        metadata={
            "minimax_h3_mode": context.get("mode"),
            "requested_duration": context.get("requested_duration"),
            "minimax_h3_resolution_preset": context.get("resolution_preset"),
            "minimax_h3_aspect_ratio": context.get("aspect_ratio"),
            "lora_items": context.get("lora_items"),
        },
    )
    return rebuilt if rebuilt == context else {}


def merge_minimax_h3_history_context_into_extra_outputs(
    *,
    task_type: str | None,
    extra_outputs: dict[str, object] | None,
    metadata: dict[str, Any] | None,
) -> dict[str, object] | None:
    if not is_minimax_h3_gallery_task_type(task_type):
        return extra_outputs
    context = build_minimax_h3_history_context(
        task_type=task_type,
        metadata=metadata,
    )
    if not context:
        return extra_outputs
    merged = dict(extra_outputs or {})
    merged[MINIMAX_H3_HISTORY_CONTEXT_KEY] = context
    return merged
