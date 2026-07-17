from functools import lru_cache
from typing import Any

from telegram import ReplyKeyboardMarkup

from src.i18n.translator import get_text
from src.services.lazy_bot_entry_service import is_lazy_bot_entry_enabled
from src.services.main_bot_menu_config_service import (
    DEFAULT_MAIN_BOT_MENU_CONFIG,
    normalize_main_bot_menu_config,
)


def _chunk(items: list[str], size: int) -> list[list[str]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def _build_main_menu_keyboard(lang: str, config: Any) -> ReplyKeyboardMarkup:
    normalized = normalize_main_bot_menu_config(config)
    visible_keys = [
        item["key"]
        for item in normalized["main_menu"]["items"]
        if item["visible"]
        and (item["key"] != "menu.lazy_bot" or is_lazy_bot_entry_enabled())
    ]
    if not visible_keys:
        visible_keys = ["menu.main_menu"]
    labels = [get_text(key, lang) for key in visible_keys]
    keyboard = _chunk(labels, normalized["main_menu"]["buttons_per_row"])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


@lru_cache(maxsize=10)
def _get_default_main_menu_keyboard(lang: str) -> ReplyKeyboardMarkup:
    return _build_main_menu_keyboard(lang, DEFAULT_MAIN_BOT_MENU_CONFIG)


def get_main_menu_keyboard(
    lang: str,
    config: dict[str, Any] | None = None,
) -> ReplyKeyboardMarkup:
    if config is None:
        return _get_default_main_menu_keyboard(lang)
    return _build_main_menu_keyboard(lang, config)


def _build_submenu_keyboard(
    lang: str,
    config: Any,
    *,
    parent_key: str,
) -> ReplyKeyboardMarkup:
    normalized = normalize_main_bot_menu_config(config)
    labels = [
        get_text(item["key"], lang)
        for item in normalized["submenus"][parent_key]
        if item["visible"]
    ]
    keyboard = _chunk(labels, 2)
    keyboard.append([get_text("menu.back_main", lang)])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


@lru_cache(maxsize=10)
def _get_default_photo_edit_keyboard(lang: str) -> ReplyKeyboardMarkup:
    return _build_submenu_keyboard(
        lang,
        DEFAULT_MAIN_BOT_MENU_CONFIG,
        parent_key="menu.photo_edit",
    )


def get_photo_edit_keyboard(
    lang: str,
    config: dict[str, Any] | None = None,
) -> ReplyKeyboardMarkup:
    if config is None:
        return _get_default_photo_edit_keyboard(lang)
    return _build_submenu_keyboard(lang, config, parent_key="menu.photo_edit")


@lru_cache(maxsize=10)
def _get_default_video_to_video_keyboard(lang: str) -> ReplyKeyboardMarkup:
    return _build_submenu_keyboard(
        lang,
        DEFAULT_MAIN_BOT_MENU_CONFIG,
        parent_key="menu.video_to_video",
    )


def get_video_to_video_keyboard(
    lang: str,
    config: dict[str, Any] | None = None,
) -> ReplyKeyboardMarkup:
    if config is None:
        return _get_default_video_to_video_keyboard(lang)
    return _build_submenu_keyboard(
        lang,
        config,
        parent_key="menu.video_to_video",
    )


# Keep the historical cache-control hook used by focused tests and local tooling.
get_main_menu_keyboard.cache_clear = _get_default_main_menu_keyboard.cache_clear  # type: ignore[attr-defined]
get_photo_edit_keyboard.cache_clear = _get_default_photo_edit_keyboard.cache_clear  # type: ignore[attr-defined]
get_video_to_video_keyboard.cache_clear = (
    _get_default_video_to_video_keyboard.cache_clear
)  # type: ignore[attr-defined]
