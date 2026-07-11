from __future__ import annotations

from typing import Any

QQCC_REGENERATE_CALLBACK_PREFIX = "qqcc_regenerate"
QQCC_REGENERATE_CONTEXT_KEY = "_qqcc_regenerate"
QQCC_REGENERATE_KIND_QUICK_IMAGE = "quick_image"
QQCC_REGENERATE_KIND_QUICK_VIDEO = "quick_video"

_ALLOWED_CONTEXT_KEYS = {
    "kind",
    "mode",
    "scene_id",
    "scene_kind",
    "display_mode_name",
}


def normalize_qqcc_regenerate_context(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    context: dict[str, Any] = {}
    for key in _ALLOWED_CONTEXT_KEYS:
        raw_value = value.get(key)
        if raw_value is None:
            continue
        normalized = str(raw_value).strip()
        if normalized:
            context[key] = normalized
    if not context.get("kind") or not context.get("mode"):
        return {}
    return context


def build_qqcc_regenerate_result_meta(
    *,
    kind: str,
    mode: str,
    display_mode_name: str,
    scene_id: str | None = None,
    scene_kind: str | None = None,
) -> dict[str, Any]:
    context: dict[str, Any] = {
        "kind": kind,
        "mode": mode,
        "display_mode_name": display_mode_name,
    }
    if scene_id:
        context["scene_id"] = scene_id
    if scene_kind:
        context["scene_kind"] = scene_kind
    return {QQCC_REGENERATE_CONTEXT_KEY: normalize_qqcc_regenerate_context(context)}


def extract_qqcc_regenerate_context(meta: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(meta, dict):
        return {}
    return normalize_qqcc_regenerate_context(meta.get(QQCC_REGENERATE_CONTEXT_KEY))


def has_qqcc_regenerate_context(meta: dict[str, Any] | None) -> bool:
    return bool(extract_qqcc_regenerate_context(meta))


def merge_qqcc_regenerate_context_into_extra_outputs(
    *,
    extra_outputs: dict[str, Any] | None,
    metadata: dict[str, Any] | None,
) -> dict[str, Any] | None:
    context = extract_qqcc_regenerate_context(metadata)
    if not context:
        return extra_outputs
    merged = dict(extra_outputs or {})
    merged[QQCC_REGENERATE_CONTEXT_KEY] = context
    return merged
