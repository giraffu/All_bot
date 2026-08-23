from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


FEATURE_ENTRY_VISIBILITY_CONFIG_KEY = "feature_entry_visibility_config:v1"

DEFAULT_FEATURE_ENTRY_VISIBILITY_CONFIG: dict[str, dict[str, bool]] = {
    "web": {
        "ltx_video": True,
        "minimax_h3": False,
        "character_assets": False,
    },
    "gallery": {
        "minimax_h3": False,
    },
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
        "enable_ltx_video_entry": config["web"]["ltx_video"],
        "enable_minimax_h3_entry": config["web"]["minimax_h3"],
        "enable_character_assets_entry": config["web"]["character_assets"],
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
