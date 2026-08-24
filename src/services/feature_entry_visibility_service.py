from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


FEATURE_ENTRY_VISIBILITY_CONFIG_KEY = "feature_entry_visibility_config:v1"

DEFAULT_FEATURE_ENTRY_VISIBILITY_CONFIG: dict[str, dict[str, bool]] = {
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
        "minimax_h3": False,
    },
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


def normalize_feature_entry_visibility_config(
    raw: Any,
) -> dict[str, dict[str, bool]]:
    if not isinstance(raw, dict):
        return deepcopy(DEFAULT_FEATURE_ENTRY_VISIBILITY_CONFIG)
    return {
        scope: _normalize_scope(raw.get(scope), defaults)
        for scope, defaults in DEFAULT_FEATURE_ENTRY_VISIBILITY_CONFIG.items()
    }


def build_public_entry_visibility_flags(raw: Any) -> dict[str, bool]:
    config = normalize_feature_entry_visibility_config(raw)
    return {
        **{
            flag_name: config["web"][config_key]
            for config_key, flag_name in WEB_ENTRY_FLAG_NAMES.items()
        },
        "enable_gallery_minimax_h3_entry": config["gallery"]["minimax_h3"],
    }


def _build_config_response(
    config: Any,
    *,
    updated_at: datetime | None,
) -> dict[str, Any]:
    return {
        "key": FEATURE_ENTRY_VISIBILITY_CONFIG_KEY,
        "config": normalize_feature_entry_visibility_config(config),
        "updated_at": updated_at,
    }


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
