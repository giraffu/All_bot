from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

from src.handlers.fsm.quick_video_callback_data import (
    QUICK_VIDEO_MODE_KEYS,
    build_quick_video_mode_callback_data,
)
from src.i18n.translator import get_text
from src.services.qqcc_config_service import (
    has_enabled_qqcc_values,
    has_enabled_qqcc_video_settings,
    is_qqcc_global_enabled,
    is_qqcc_main_bot_link_enabled,
    is_qqcc_main_button_enabled,
    is_qqcc_photo_button_enabled,
    is_qqcc_video_button_enabled,
    normalize_qqcc_config,
)

VIDEO_ROUTE_TO_CONFIG_KEY = {
    "menu.video_edit_missionary": "missionary",
    "menu.video_edit_doggy": "doggy",
    "menu.video_edit_blowjob": "blowjob",
    "menu.video_edit_undress_tongue": "undress_tongue",
    "menu.video_edit_closeup_blowjob": "closeup_blowjob",
}


def _can_show_quick_undress(config: dict) -> bool:
    return (
        is_qqcc_main_button_enabled(config, "quick_undress")
        and has_enabled_qqcc_values(config, "undress_methods")
    )


def _can_show_photo_edit(config: dict) -> bool:
    return (
        is_qqcc_main_button_enabled(config, "photo_edit")
        and has_enabled_qqcc_values(config, "photo_buttons")
    )


def _can_show_video_edit(config: dict) -> bool:
    return (
        is_qqcc_main_button_enabled(config, "video_edit")
        and has_enabled_qqcc_values(config, "video_buttons")
        and has_enabled_qqcc_video_settings(config)
    )


def _can_show_market(config: dict) -> bool:
    return is_qqcc_main_button_enabled(config, "market")


def get_qqcc_main_menu_keyboard(
    lang: str,
    config: dict | None = None,
) -> ReplyKeyboardMarkup:
    config = normalize_qqcc_config(config)
    keyboard = []
    if is_qqcc_global_enabled(config) and _can_show_quick_undress(config):
        keyboard.append([get_text("menu.photo_edit_undress", lang)])

    feature_row = []
    if is_qqcc_global_enabled(config) and _can_show_photo_edit(config):
        feature_row.append(get_text("menu.photo_edit", lang))
    if is_qqcc_global_enabled(config) and _can_show_video_edit(config):
        feature_row.append(get_text("qqcc.menu.video_edit", lang))
    if feature_row:
        keyboard.append(feature_row)

    if is_qqcc_global_enabled(config) and _can_show_market(config):
        keyboard.append([get_text("qqcc.menu.market", lang)])

    if is_qqcc_main_bot_link_enabled(config):
        keyboard.append([get_text("menu.open_main_bot", lang)])
    if not keyboard:
        keyboard.append([get_text("menu.main_menu", lang)])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_qqcc_main_bot_link_keyboard(
    lang: str, main_bot_url: str
) -> InlineKeyboardMarkup:
    button = InlineKeyboardButton(
        get_text("menu.open_main_bot", lang),
        url=main_bot_url,
    )
    return InlineKeyboardMarkup([[button]])


def get_qqcc_photo_edit_keyboard(
    lang: str,
    config: dict | None = None,
) -> ReplyKeyboardMarkup:
    config = normalize_qqcc_config(config)
    keyboard = []
    if is_qqcc_photo_button_enabled(config, "masturbation"):
        keyboard.append([get_text("menu.photo_edit_masturbation", lang)])
    if is_qqcc_photo_button_enabled(config, "random_faceswap"):
        keyboard.append([get_text("menu.photo_edit_random_faceswap", lang)])
    keyboard.append([get_text("menu.back_main", lang)])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_qqcc_video_edit_keyboard(
    lang: str,
    config: dict | None = None,
) -> ReplyKeyboardMarkup:
    config = normalize_qqcc_config(config)
    route_texts = [
        get_text(route_key, lang)
        for route_key in QUICK_VIDEO_MODE_KEYS
        if is_qqcc_video_button_enabled(config, VIDEO_ROUTE_TO_CONFIG_KEY[route_key])
    ]
    keyboard = [
        route_texts[index : index + 2] for index in range(0, len(route_texts), 2)
    ]
    keyboard.append([get_text("menu.back_main", lang)])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_qqcc_video_edit_inline_keyboard(
    lang: str,
    config: dict | None = None,
) -> InlineKeyboardMarkup:
    config = normalize_qqcc_config(config)
    buttons = [
        InlineKeyboardButton(
            get_text(route_key, lang),
            callback_data=build_quick_video_mode_callback_data(route_key),
        )
        for route_key in QUICK_VIDEO_MODE_KEYS
        if is_qqcc_video_button_enabled(config, VIDEO_ROUTE_TO_CONFIG_KEY[route_key])
    ]
    keyboard = [buttons[index : index + 3] for index in range(0, len(buttons), 3)]
    return InlineKeyboardMarkup(keyboard)
