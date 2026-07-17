from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from src.i18n.keyboards import (
    get_main_menu_keyboard,
    get_photo_edit_keyboard,
    get_video_to_video_keyboard,
)
from src.services.main_bot_menu_config_service import (
    DEFAULT_MAIN_BOT_MENU_CONFIG,
    load_runtime_main_bot_menu_config,
)


LoadMainBotMenuConfigFunc = Callable[[], Awaitable[dict[str, Any]]]
logger = logging.getLogger("bot.main_menu")


async def _load_config_safely(
    load_config_func: LoadMainBotMenuConfigFunc,
) -> dict[str, Any]:
    try:
        return await load_config_func()
    except Exception:
        logger.exception("Failed to load main Bot menu config; using defaults.")
        return DEFAULT_MAIN_BOT_MENU_CONFIG


async def get_runtime_main_menu_keyboard(
    lang: str,
    *,
    load_config_func: LoadMainBotMenuConfigFunc = load_runtime_main_bot_menu_config,
):
    config = await _load_config_safely(load_config_func)
    return get_main_menu_keyboard(lang, config)


async def get_runtime_photo_edit_keyboard(
    lang: str,
    *,
    load_config_func: LoadMainBotMenuConfigFunc = load_runtime_main_bot_menu_config,
):
    config = await _load_config_safely(load_config_func)
    return get_photo_edit_keyboard(lang, config)


async def get_runtime_video_to_video_keyboard(
    lang: str,
    *,
    load_config_func: LoadMainBotMenuConfigFunc = load_runtime_main_bot_menu_config,
):
    config = await _load_config_safely(load_config_func)
    return get_video_to_video_keyboard(lang, config)
