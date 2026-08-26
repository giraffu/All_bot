from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import math
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain_config.minimax_h3 import (
    MINIMAX_H3_ADDON_MODELS,
    MINIMAX_H3_ADDON_MAX_STRENGTH,
    MINIMAX_H3_ADDON_MIN_STRENGTH,
    MINIMAX_H3_DEFAULT_MAIN_MODEL,
    MINIMAX_H3_MAIN_MODEL_OFFICIAL_REF2V_TURBO,
    MINIMAX_H3_MAIN_MODELS,
    MINIMAX_H3_MAX_ADDON_ITEMS,
    MINIMAX_H3_MODES,
)


FEATURE_ENTRY_VISIBILITY_CONFIG_KEY = "feature_entry_visibility_config:v1"
ADVANCED_VIDEO_PRO_MODES = MINIMAX_H3_MODES

DEFAULT_ADVANCED_VIDEO_PRO_CONFIG: dict[str, dict[str, Any]] = {
    mode: {
        "main_model": MINIMAX_H3_DEFAULT_MAIN_MODEL,
        "addon_items": [],
    }
    for mode in ADVANCED_VIDEO_PRO_MODES
}

GALLERY_ENTRY_FLAG_NAMES: dict[str, str] = {
    "txt2img": "enable_gallery_txt2img_entry",
    "i2i_pro": "enable_gallery_i2i_pro_entry",
    "edit": "enable_gallery_edit_entry",
    "free_edit_v2_5": "enable_gallery_free_edit_v2_5_entry",
    "free_edit_v3": "enable_gallery_free_edit_v3_entry",
    "custom_video": "enable_gallery_custom_video_entry",
    "ltx_video": "enable_gallery_ltx_video_entry",
    "minimax_h3": "enable_gallery_minimax_h3_entry",
    "wan22_video_v2": "enable_gallery_wan22_video_v2_entry",
    "scail2_action_transfer": "enable_gallery_scail2_action_transfer_entry",
    "scail2_video_replacement": "enable_gallery_scail2_video_replacement_entry",
    "scail2_face_swap_v2": "enable_gallery_scail2_face_swap_v2_entry",
}

DEFAULT_FEATURE_ENTRY_VISIBILITY_CONFIG: dict[str, Any] = {
    "web": {
        "edit": True,
        "edit_v2_5": True,
        "edit_v3": True,
        "txt2img": True,
        "i2i_pro": True,
        "custom_video": True,
        "face_swap": True,
        "random_faceswap": True,
        "ltx_video": True,
        "ltx_video_v2": True,
        "ltx_t2v": True,
        "minimax_h3": False,
        "wan22_video_v2": True,
        "scail2_action_transfer": True,
        "scail2_video_replacement": True,
        "scail2_face_swap_v2": True,
        "character_assets": False,
    },
    "gallery": {
        "txt2img": True,
        "i2i_pro": True,
        "edit": True,
        "free_edit_v2_5": True,
        "free_edit_v3": True,
        "custom_video": True,
        "ltx_video": True,
        "minimax_h3": False,
        "wan22_video_v2": True,
        "scail2_action_transfer": True,
        "scail2_video_replacement": True,
        "scail2_face_swap_v2": True,
    },
    "advanced_video_pro": deepcopy(DEFAULT_ADVANCED_VIDEO_PRO_CONFIG),
}

WEB_ENTRY_FLAG_NAMES: dict[str, str] = {
    "edit": "enable_edit_entry",
    "edit_v2_5": "enable_edit_v2_5_entry",
    "edit_v3": "enable_edit_v3_entry",
    "txt2img": "enable_txt2img_entry",
    "i2i_pro": "enable_i2i_pro_entry",
    "custom_video": "enable_custom_video_entry",
    "face_swap": "enable_face_swap_entry",
    "random_faceswap": "enable_random_faceswap_entry",
    "ltx_video": "enable_ltx_video_entry",
    "ltx_video_v2": "enable_ltx_video_v2_entry",
    "ltx_t2v": "enable_ltx_t2v_entry",
    "minimax_h3": "enable_minimax_h3_entry",
    "wan22_video_v2": "enable_wan22_video_v2_entry",
    "scail2_action_transfer": "enable_scail2_action_transfer_entry",
    "scail2_video_replacement": "enable_scail2_video_replacement_entry",
    "scail2_face_swap_v2": "enable_scail2_face_swap_v2_entry",
    "character_assets": "enable_character_assets_entry",
}


def _normalize_scope(raw: Any, defaults: dict[str, bool]) -> dict[str, bool]:
    values = raw if isinstance(raw, dict) else {}
    return {
        key: values[key] if isinstance(values.get(key), bool) else default
        for key, default in defaults.items()
    }


def _normalize_advanced_video_pro_config(raw: Any) -> dict[str, dict[str, Any]]:
    values = raw if isinstance(raw, dict) else {}
    normalized: dict[str, dict[str, Any]] = {}
    for mode in ADVANCED_VIDEO_PRO_MODES:
        profile = values.get(mode)
        profile = profile if isinstance(profile, dict) else {}
        main_model = str(
            profile.get("main_model") or MINIMAX_H3_DEFAULT_MAIN_MODEL
        ).strip().lower()
        if main_model not in MINIMAX_H3_MAIN_MODELS or (
            main_model == MINIMAX_H3_MAIN_MODEL_OFFICIAL_REF2V_TURBO
            and mode != "ref2v"
        ):
            main_model = MINIMAX_H3_DEFAULT_MAIN_MODEL

        raw_items = profile.get("addon_items")
        if isinstance(raw_items, (list, tuple)):
            candidates = list(raw_items)
        else:
            legacy_addons = profile.get("addon_models")
            legacy_addons = (
                legacy_addons
                if isinstance(legacy_addons, (list, tuple))
                else []
            )
            candidates = [{"name": value} for value in legacy_addons]

        addon_items: list[dict[str, Any]] = []
        seen: set[str] = set()
        for raw_item in candidates:
            if not isinstance(raw_item, dict):
                continue
            model_id = str(raw_item.get("name") or "").strip()
            model = MINIMAX_H3_ADDON_MODELS.get(model_id)
            if (
                model is None
                or mode not in model.supported_modes
                or model_id in seen
            ):
                continue
            try:
                raw_strength = raw_item.get("strength")
                strength = (
                    model.default_strength
                    if raw_strength in (None, "")
                    else float(raw_strength)
                )
            except (TypeError, ValueError):
                continue
            if not (
                math.isfinite(strength)
                and MINIMAX_H3_ADDON_MIN_STRENGTH
                <= strength
                <= MINIMAX_H3_ADDON_MAX_STRENGTH
            ):
                continue
            seen.add(model_id)
            addon_items.append({"name": model_id, "strength": strength})
            if len(addon_items) >= MINIMAX_H3_MAX_ADDON_ITEMS:
                break
        normalized[mode] = {
            "main_model": main_model,
            "addon_items": addon_items,
        }
    return normalized


def normalize_feature_entry_visibility_config(
    raw: Any,
) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return deepcopy(DEFAULT_FEATURE_ENTRY_VISIBILITY_CONFIG)
    return {
        "web": _normalize_scope(
            raw.get("web"), DEFAULT_FEATURE_ENTRY_VISIBILITY_CONFIG["web"]
        ),
        "gallery": _normalize_scope(
            raw.get("gallery"), DEFAULT_FEATURE_ENTRY_VISIBILITY_CONFIG["gallery"]
        ),
        "advanced_video_pro": _normalize_advanced_video_pro_config(
            raw.get("advanced_video_pro")
        ),
    }


def get_advanced_video_pro_profile(raw: Any, mode: str) -> dict[str, Any]:
    normalized_mode = str(mode or "").strip().lower()
    if normalized_mode not in ADVANCED_VIDEO_PRO_MODES:
        raise ValueError("未知高级图生视频 Pro 模式。")
    profile = normalize_feature_entry_visibility_config(raw)[
        "advanced_video_pro"
    ][normalized_mode]
    return {
        "main_model": profile["main_model"],
        "addon_items": [dict(item) for item in profile["addon_items"]],
    }


def build_advanced_video_pro_admin_options() -> dict[str, Any]:
    main_model_labels = {
        "10eros": "10Eros TURBO",
        "official": "官方高保真",
        "official_ref2v_turbo": "官方 REF2V 极速",
    }
    return {
        "modes": [
            {"value": mode, "label": label}
            for mode, label in (
                ("t2v", "文生视频"),
                ("i2v", "首帧图生视频"),
                ("flf2v", "首尾帧视频"),
                ("ref2v", "参考图生视频"),
            )
        ],
        "main_models": {
            mode: [
                {"value": model_id, "label": main_model_labels[model_id]}
                for model_id in MINIMAX_H3_MAIN_MODELS
                if not (
                    model_id == MINIMAX_H3_MAIN_MODEL_OFFICIAL_REF2V_TURBO
                    and mode != "ref2v"
                )
            ]
            for mode in ADVANCED_VIDEO_PRO_MODES
        },
        "addon_models": [
            {
                "value": model.id,
                "label": model.label_zh,
                "supported_modes": list(model.supported_modes),
                "default_strength": model.default_strength,
            }
            for model in MINIMAX_H3_ADDON_MODELS.values()
        ],
        "max_addon_items": MINIMAX_H3_MAX_ADDON_ITEMS,
        "strength_min": MINIMAX_H3_ADDON_MIN_STRENGTH,
        "strength_max": MINIMAX_H3_ADDON_MAX_STRENGTH,
    }


def build_public_entry_visibility_flags(raw: Any) -> dict[str, bool]:
    config = normalize_feature_entry_visibility_config(raw)
    return {
        **{
            flag_name: config["web"][config_key]
            for config_key, flag_name in WEB_ENTRY_FLAG_NAMES.items()
        },
        **{
            flag_name: config["gallery"][config_key]
            for config_key, flag_name in GALLERY_ENTRY_FLAG_NAMES.items()
        },
    }


def _build_config_response(
    config: Any,
    *,
    updated_at: datetime | None,
) -> dict[str, Any]:
    return {
        "key": FEATURE_ENTRY_VISIBILITY_CONFIG_KEY,
        "config": normalize_feature_entry_visibility_config(config),
        "options": build_advanced_video_pro_admin_options(),
        "updated_at": updated_at,
    }


async def load_advanced_video_pro_profiles() -> dict[str, dict[str, Any]]:
    from src.database.core import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        payload = await load_feature_entry_visibility_config_payload(db)
    return {
        mode: get_advanced_video_pro_profile(payload["config"], mode)
        for mode in ADVANCED_VIDEO_PRO_MODES
    }


async def load_advanced_video_pro_profile(mode: str) -> dict[str, Any]:
    profiles = await load_advanced_video_pro_profiles()
    normalized_mode = str(mode or "").strip().lower()
    if normalized_mode not in profiles:
        raise ValueError("未知高级图生视频 Pro 模式。")
    return profiles[normalized_mode]


async def load_feature_entry_visibility_config_payload(
    db: AsyncSession,
) -> dict[str, Any]:
    from src.database.models import RuntimeCheckpoint

    result = await db.execute(
        select(RuntimeCheckpoint).where(
            RuntimeCheckpoint.key == FEATURE_ENTRY_VISIBILITY_CONFIG_KEY
        )
    )
    checkpoint = result.scalar_one_or_none()
    if checkpoint is None:
        return _build_config_response({}, updated_at=None)
    return _build_config_response(
        checkpoint.value or {},
        updated_at=checkpoint.updated_at,
    )


async def save_feature_entry_visibility_config_payload(
    db: AsyncSession,
    payload: dict[str, Any],
) -> dict[str, Any]:
    from src.database.models import RuntimeCheckpoint

    config = normalize_feature_entry_visibility_config(payload)
    result = await db.execute(
        select(RuntimeCheckpoint)
        .where(RuntimeCheckpoint.key == FEATURE_ENTRY_VISIBILITY_CONFIG_KEY)
        .with_for_update()
    )
    checkpoint = result.scalar_one_or_none()
    if checkpoint is None:
        checkpoint = RuntimeCheckpoint(
            key=FEATURE_ENTRY_VISIBILITY_CONFIG_KEY,
            value=config,
        )
        db.add(checkpoint)
    else:
        checkpoint.value = config
    await db.commit()
    await db.refresh(checkpoint)
    return _build_config_response(
        checkpoint.value or {},
        updated_at=checkpoint.updated_at,
    )
