from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any

from src.domain_config.minimax_h3 import (
    MINIMAX_H3_ALLOWED_DURATIONS,
    MINIMAX_H3_ASPECT_RATIOS,
    MINIMAX_H3_FLF2V,
    MINIMAX_H3_I2V,
    MINIMAX_H3_REF2V,
    MINIMAX_H3_PIXEL_PRESETS,
    MiniMaxH3ValidationError,
    normalize_minimax_h3_addon_items,
    normalize_minimax_h3_main_model,
)


MINIMAX_H3_HISTORY_CONTEXT_KEY = "_minimax_h3_context"
MINIMAX_H3_HISTORY_CONTEXT_VERSION = 3
MINIMAX_H3_PREVIOUS_HISTORY_CONTEXT_VERSION = 2
MINIMAX_H3_LEGACY_HISTORY_CONTEXT_VERSION = 1
MINIMAX_H3_GALLERY_TASK_TYPES = frozenset(
    {MINIMAX_H3_I2V, MINIMAX_H3_FLF2V, MINIMAX_H3_REF2V}
)
_MODE_BY_TASK_TYPE = {
    MINIMAX_H3_I2V: "i2v",
    MINIMAX_H3_FLF2V: "flf2v",
    MINIMAX_H3_REF2V: "ref2v",
}
_REFERENCE_AUDIO_EXTENSIONS = frozenset(
    {"mp3", "wav", "m4a", "mp4", "ogg", "oga", "opus"}
)


def _normalize_durable_reference_audio(value: object) -> str | None:
    reference = str(value or "").strip()
    if not reference:
        return None
    path = PurePosixPath(reference)
    if (
        path.is_absolute()
        or ".." in path.parts
        or "://" in reference
        or path.suffix.lower().removeprefix(".") not in _REFERENCE_AUDIO_EXTENSIONS
    ):
        raise ValueError("reference audio must be a durable storage object key")
    return reference


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
    resolution_preset = str(metadata.get("minimax_h3_resolution_preset") or "").strip()
    aspect_ratio = str(metadata.get("minimax_h3_aspect_ratio") or "").strip()
    try:
        requested_duration = int(metadata.get("requested_duration"))
    except (TypeError, ValueError):
        return {}
    if (
        mode != expected_mode
        or requested_duration not in MINIMAX_H3_ALLOWED_DURATIONS
        or resolution_preset not in MINIMAX_H3_PIXEL_PRESETS
        or (
            aspect_ratio != "source"
            if expected_mode in {"i2v", "flf2v"}
            else aspect_ratio not in MINIMAX_H3_ASPECT_RATIOS
        )
    ):
        return {}
    try:
        addon_items = normalize_minimax_h3_addon_items(
            {"lora_items": metadata.get("lora_items") or []},
            mode=expected_mode,
        )
    except MiniMaxH3ValidationError:
        return {}
    try:
        main_model = normalize_minimax_h3_main_model(
            metadata.get("minimax_h3_main_model")
        )
    except MiniMaxH3ValidationError:
        return {}
    try:
        reference_audio = _normalize_durable_reference_audio(
            metadata.get("reference_audio")
        )
    except ValueError:
        return {}
    if reference_audio is not None and expected_mode != "ref2v":
        return {}
    context = {
        "version": MINIMAX_H3_HISTORY_CONTEXT_VERSION,
        "mode": mode,
        "main_model": main_model,
        "requested_duration": requested_duration,
        "resolution_preset": resolution_preset,
        "aspect_ratio": aspect_ratio,
        "lora_items": [
            {"name": item.name, "strength": item.strength} for item in addon_items
        ],
    }
    if reference_audio is not None:
        context["reference_audio"] = reference_audio
    prev_task_id = str(metadata.get("minimax_h3_prev_task_id") or "").strip()
    chain_task_ids = normalize_minimax_h3_chain_task_ids(
        metadata.get("minimax_h3_chain_task_ids")
    )
    if prev_task_id:
        if not chain_task_ids or chain_task_ids[-1] != prev_task_id:
            return {}
        context["prev_task_id"] = prev_task_id
    if chain_task_ids:
        context["chain_task_ids"] = chain_task_ids
    return context


def normalize_minimax_h3_chain_task_ids(value: object) -> list[str]:
    if isinstance(value, str):
        raw_items = value.split(",")
    elif isinstance(value, (list, tuple, set)):
        raw_items = list(value)
    else:
        raw_items = []
    ordered: list[str] = []
    for item in raw_items:
        normalized = str(item or "").strip()
        if normalized and normalized not in ordered:
            ordered.append(normalized)
    return ordered


def extract_minimax_h3_history_context(
    extra_outputs: dict[str, object] | None,
) -> dict[str, object]:
    if not isinstance(extra_outputs, dict):
        return {}
    context = extra_outputs.get(MINIMAX_H3_HISTORY_CONTEXT_KEY)
    if not isinstance(context, dict):
        return {}
    if context.get("version") not in {
        MINIMAX_H3_LEGACY_HISTORY_CONTEXT_VERSION,
        MINIMAX_H3_PREVIOUS_HISTORY_CONTEXT_VERSION,
        MINIMAX_H3_HISTORY_CONTEXT_VERSION,
    }:
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
            "minimax_h3_main_model": context.get("main_model"),
            "reference_audio": context.get("reference_audio"),
            "lora_items": context.get("lora_items"),
            "minimax_h3_prev_task_id": context.get("prev_task_id"),
            "minimax_h3_chain_task_ids": context.get("chain_task_ids"),
        },
    )
    if not rebuilt:
        return {}
    if context.get("version") in {
        MINIMAX_H3_LEGACY_HISTORY_CONTEXT_VERSION,
        MINIMAX_H3_PREVIOUS_HISTORY_CONTEXT_VERSION,
    }:
        legacy_rebuilt = dict(rebuilt)
        legacy_rebuilt["version"] = context["version"]
        legacy_rebuilt.pop("main_model", None)
        return rebuilt if legacy_rebuilt == context else {}
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


def merge_minimax_h3_input_assets_into_metadata(
    *,
    task_type: str | None,
    metadata: dict[str, Any] | None,
    inputs: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if task_type != MINIMAX_H3_REF2V:
        return metadata
    reference_audio = str((inputs or {}).get("reference_audio") or "").strip()
    if not reference_audio:
        return metadata
    merged = dict(metadata or {})
    merged["reference_audio"] = reference_audio
    return merged
