from __future__ import annotations

import math
from typing import Any, Callable

from src.domain_config.minimax_h3 import (
    MINIMAX_H3_ADDON_MODELS,
    MINIMAX_H3_ASPECT_RATIOS,
    MINIMAX_H3_DEFAULT_MAIN_MODEL,
    MINIMAX_H3_MAX_ADDON_ITEMS,
    MiniMaxH3ValidationError,
    normalize_minimax_h3_main_model,
)

AI_VIDEO_SCENE_ENGINE_MINIMAX_H3 = "minimax_h3"
AI_VIDEO_DURATION_KEYS = (5, 10, 15)
AI_VIDEO_RESOLUTION_KEYS = ("preview", "small", "standard", "hd")
DEFAULT_AI_VIDEO_SCENE_RESOLUTION = AI_VIDEO_RESOLUTION_KEYS[0]
AI_VIDEO_MAX_LORA_ITEMS = MINIMAX_H3_MAX_ADDON_ITEMS


def _normalize_duration(raw_duration: Any) -> int:
    try:
        duration = int(str(raw_duration).strip().removesuffix("s"))
    except (TypeError, ValueError):
        return AI_VIDEO_DURATION_KEYS[0]
    return duration if duration in AI_VIDEO_DURATION_KEYS else AI_VIDEO_DURATION_KEYS[0]


def _normalize_mode_and_model(raw_scene: dict[str, Any]) -> tuple[str, str]:
    mode = "ref2v" if str(raw_scene.get("mode") or "i2v").strip() == "ref2v" else "i2v"
    try:
        main_model = normalize_minimax_h3_main_model(
            raw_scene.get("main_model"), migrate_retired=True
        )
    except MiniMaxH3ValidationError:
        main_model = MINIMAX_H3_DEFAULT_MAIN_MODEL
    return mode, main_model


def _normalize_lora_items(raw_items: Any, *, mode: str) -> list[dict[str, Any]]:
    if not isinstance(raw_items, list):
        return []
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            continue
        raw_name = raw_item.get("name")
        name = raw_name.strip() if isinstance(raw_name, str) else ""
        model = MINIMAX_H3_ADDON_MODELS.get(name)
        if model is None or mode not in model.supported_modes or name in seen:
            continue
        seen.add(name)
        try:
            raw_strength = raw_item.get("strength")
            strength = (
                model.default_strength
                if raw_strength in (None, "")
                else float(raw_strength)
            )
        except (TypeError, ValueError):
            strength = model.default_strength
        if not math.isfinite(strength):
            strength = model.default_strength
        strength = float(round(round(min(2.0, max(0.1, strength)) * 20) / 20, 2))
        items.append({"name": name, "strength": strength})
        if len(items) >= AI_VIDEO_MAX_LORA_ITEMS:
            break
    return items


def _normalize_reference_images(
    raw_scene: dict[str, Any], *, mode: str
) -> list[str] | None:
    if mode != "ref2v":
        return []
    raw_images = raw_scene.get("reference_images")
    images = (
        [
            value.strip()
            for value in raw_images
            if isinstance(value, str)
            and value.strip().startswith("qqcc/config/ref2v/ai_video/")
        ]
        if isinstance(raw_images, list)
        else []
    )
    return images if 1 <= len(images) <= 4 else None


def _normalize_reference_names(raw_names: Any, *, count: int) -> list[str]:
    return [
        (
            str(raw_names[index]).strip()[:64]
            if isinstance(raw_names, list)
            and index < len(raw_names)
            and isinstance(raw_names[index], str)
            and str(raw_names[index]).strip()
            else f"模板 {index + 1}"
        )
        for index in range(count)
    ]


def _normalize_telegram_file_ids(raw_file_ids: Any, *, count: int) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for index in range(count):
        raw_mapping = (
            raw_file_ids[index]
            if isinstance(raw_file_ids, list) and index < len(raw_file_ids)
            else {}
        )
        mapping: dict[str, str] = {}
        if isinstance(raw_mapping, dict):
            for raw_bot_id, raw_file_id in raw_mapping.items():
                bot_id = str(raw_bot_id).strip()
                file_id = str(raw_file_id).strip() if isinstance(raw_file_id, str) else ""
                if bot_id.isdigit() and file_id:
                    mapping[bot_id] = file_id[:512]
                if len(mapping) >= 4:
                    break
        result.append(mapping)
    return result


def normalize_qqcc_ai_video_scene(
    raw_scene: Any,
    *,
    index: int,
    used_ids: set[str],
    allowed_end_frame_draw_scene_ids: frozenset[str],
    build_unique_scene_id: Callable[..., str],
    normalize_negative_prompt: Callable[[Any], str],
    normalize_credit_cost: Callable[[Any], int | None],
    normalize_draw_scene_id: Callable[..., str],
    attach_demo_media: Callable[..., None],
) -> dict[str, Any] | None:
    if not isinstance(raw_scene, dict):
        return None
    name = raw_scene.get("name")
    name = name.strip() if isinstance(name, str) else ""
    prompt = raw_scene.get("prompt")
    prompt = prompt.strip() if isinstance(prompt, str) else ""
    if not name or not prompt:
        return None

    mode, main_model = _normalize_mode_and_model(raw_scene)
    reference_images = _normalize_reference_images(raw_scene, mode=mode)
    if reference_images is None:
        return None
    aspect_ratio = str(raw_scene.get("aspect_ratio") or "16:9").strip()
    if aspect_ratio not in MINIMAX_H3_ASPECT_RATIOS:
        aspect_ratio = "16:9"
    raw_resolution = raw_scene.get("resolution")
    resolution = raw_resolution.strip() if isinstance(raw_resolution, str) else ""
    if resolution not in AI_VIDEO_RESOLUTION_KEYS:
        resolution = DEFAULT_AI_VIDEO_SCENE_RESOLUTION

    scene = {
        "id": build_unique_scene_id(raw_scene.get("id"), index=index, used_ids=used_ids),
        "name": name,
        "prompt": prompt,
        "negative_prompt": normalize_negative_prompt(raw_scene.get("negative_prompt")),
        "duration": _normalize_duration(raw_scene.get("duration")),
        "resolution": resolution,
        "engine": AI_VIDEO_SCENE_ENGINE_MINIMAX_H3,
        "main_model": main_model,
        "mode": mode,
        "reference_images": reference_images,
        "aspect_ratio": aspect_ratio,
        "lora_items": _normalize_lora_items(raw_scene.get("lora_items"), mode=mode),
        "credit_cost": normalize_credit_cost(raw_scene.get("credit_cost")),
        "end_frame_draw_scene_id": normalize_draw_scene_id(
            None if mode == "ref2v" else raw_scene.get("end_frame_draw_scene_id"),
            allowed_draw_scene_ids=allowed_end_frame_draw_scene_ids,
        ),
        "jump_draw_scene_id": normalize_draw_scene_id(
            raw_scene.get("jump_draw_scene_id"),
            allowed_draw_scene_ids=allowed_end_frame_draw_scene_ids,
        ),
        "next_scene_id": (
            str(raw_scene.get("next_scene_id")).strip()
            if mode != "ref2v"
            and isinstance(raw_scene.get("next_scene_id"), str)
            and str(raw_scene.get("next_scene_id")).strip()
            else None
        ),
    }
    attach_demo_media(
        scene, raw_scene, scene_kind="ai_video", output_media_type="video"
    )
    if mode == "ref2v":
        scene["reference_image_names"] = _normalize_reference_names(
            raw_scene.get("reference_image_names"), count=len(reference_images)
        )
        scene["reference_image_telegram_file_ids"] = _normalize_telegram_file_ids(
            raw_scene.get("reference_image_telegram_file_ids"),
            count=len(reference_images),
        )
    if not scene["jump_draw_scene_id"]:
        scene.pop("jump_draw_scene_id")
    return scene
