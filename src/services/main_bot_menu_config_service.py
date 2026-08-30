from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


MAIN_BOT_MENU_CONFIG_KEY = "main_bot_menu_config:v1"

MAIN_MENU_KEYS = (
    "menu.lazy_bot",
    "menu.recharge",
    "menu.checkin",
    "menu.profile",
    "menu.share",
    "menu.queue",
    "menu.switch_lang",
    "menu.photo_edit",
    "menu.video_to_video",
    "menu.txt2img",
    "menu.i2i_pro",
    "menu.free_edit",
    "menu.video_lora",
    "menu.ltx_video",
    "menu.advanced_video_pro",
    "menu.wan22_video_v2",
)

SUBMENU_KEYS = {
    "menu.photo_edit": (
        "menu.photo_edit_faceswap",
        "menu.photo_edit_random_faceswap",
    ),
    "menu.video_to_video": (
        "menu.video_to_video_replacement",
        "menu.video_to_video_action_transfer",
        "menu.video_upscale",
        "menu.face_video",
    ),
}

DEFAULT_MAIN_BOT_MENU_CONFIG: dict[str, Any] = {
    "main_menu": {
        "buttons_per_row": 3,
        "items": [
            {
                "key": key,
                "visible": key != "menu.advanced_video_pro",
            }
            for key in MAIN_MENU_KEYS
        ],
    },
    "submenus": {
        parent_key: [
            {"key": key, "visible": key != "menu.video_upscale"}
            for key in item_keys
        ]
        for parent_key, item_keys in SUBMENU_KEYS.items()
    },
}


class MainBotMenuConfigValidationError(ValueError):
    pass


def _normalize_items(raw: Any, allowed_keys: tuple[str, ...]) -> list[dict[str, Any]]:
    raw_items = raw if isinstance(raw, list) else []
    allowed = frozenset(allowed_keys)
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()

    for item in raw_items:
        if not isinstance(item, dict):
            continue
        key = item.get("key")
        if key not in allowed or key in seen:
            continue
        seen.add(key)
        normalized.append(
            {
                "key": key,
                "visible": item.get("visible")
                if isinstance(item.get("visible"), bool)
                else key != "menu.video_upscale",
            }
        )

    normalized.extend(
        {
            "key": key,
            "visible": key not in {"menu.advanced_video_pro", "menu.video_upscale"},
        }
        for key in allowed_keys
        if key not in seen
    )
    return normalized


def normalize_main_bot_menu_config(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return deepcopy(DEFAULT_MAIN_BOT_MENU_CONFIG)

    raw_main = raw.get("main_menu")
    raw_main = raw_main if isinstance(raw_main, dict) else {}
    buttons_per_row = raw_main.get("buttons_per_row")
    if (
        not isinstance(buttons_per_row, int)
        or isinstance(buttons_per_row, bool)
        or not 1 <= buttons_per_row <= 4
    ):
        buttons_per_row = 3

    raw_submenus = raw.get("submenus")
    raw_submenus = raw_submenus if isinstance(raw_submenus, dict) else {}
    return {
        "main_menu": {
            "buttons_per_row": buttons_per_row,
            "items": _normalize_items(raw_main.get("items"), MAIN_MENU_KEYS),
        },
        "submenus": {
            parent_key: _normalize_items(raw_submenus.get(parent_key), item_keys)
            for parent_key, item_keys in SUBMENU_KEYS.items()
        },
    }


def validate_main_bot_menu_config(raw: Any) -> dict[str, Any]:
    raw_main = raw.get("main_menu") if isinstance(raw, dict) else None
    buttons_per_row = (
        raw_main.get("buttons_per_row") if isinstance(raw_main, dict) else None
    )
    if (
        not isinstance(buttons_per_row, int)
        or isinstance(buttons_per_row, bool)
        or not 1 <= buttons_per_row <= 4
    ):
        raise MainBotMenuConfigValidationError(
            "buttons_per_row must be an integer between 1 and 4"
        )

    config = normalize_main_bot_menu_config(raw)
    if not any(item["visible"] for item in config["main_menu"]["items"]):
        raise MainBotMenuConfigValidationError(
            "at least one main menu item must remain visible"
        )
    return config


def _build_config_response(
    config: Any,
    *,
    updated_at: datetime | None,
) -> dict[str, Any]:
    return {
        "key": MAIN_BOT_MENU_CONFIG_KEY,
        "config": normalize_main_bot_menu_config(config),
        "updated_at": updated_at,
    }


async def load_main_bot_menu_config_payload(db: AsyncSession) -> dict[str, Any]:
    from src.database.models import RuntimeCheckpoint

    result = await db.execute(
        select(RuntimeCheckpoint).where(
            RuntimeCheckpoint.key == MAIN_BOT_MENU_CONFIG_KEY
        )
    )
    checkpoint = result.scalar_one_or_none()
    if checkpoint is None:
        return _build_config_response({}, updated_at=None)
    return _build_config_response(
        checkpoint.value or {},
        updated_at=checkpoint.updated_at,
    )


async def save_main_bot_menu_config_payload(
    db: AsyncSession,
    payload: dict[str, Any],
) -> dict[str, Any]:
    from src.database.models import RuntimeCheckpoint

    config = validate_main_bot_menu_config(payload)
    result = await db.execute(
        select(RuntimeCheckpoint)
        .where(RuntimeCheckpoint.key == MAIN_BOT_MENU_CONFIG_KEY)
        .with_for_update()
    )
    checkpoint = result.scalar_one_or_none()
    if checkpoint is None:
        checkpoint = RuntimeCheckpoint(
            key=MAIN_BOT_MENU_CONFIG_KEY,
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


async def load_runtime_main_bot_menu_config() -> dict[str, Any]:
    from src.database.core import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        payload = await load_main_bot_menu_config_payload(db)
        return payload["config"]
