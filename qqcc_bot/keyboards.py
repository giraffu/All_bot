from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

from src.handlers.fsm.quick_draw_callback_data import (
    build_quick_draw_scene_callback_data,
)
from src.handlers.fsm.quick_video_callback_data import (
    build_quick_video_scene_callback_data,
)
from src.i18n.translator import get_text
from src.services.qqcc_config_service import (
    get_enabled_qqcc_draw_scenes,
    get_enabled_qqcc_video_scenes,
    has_enabled_qqcc_values,
    has_enabled_qqcc_draw_scenes,
    has_enabled_qqcc_video_scenes,
    is_qqcc_global_enabled,
    is_qqcc_main_bot_link_enabled,
    is_qqcc_main_button_enabled,
    is_qqcc_photo_button_enabled,
    normalize_qqcc_config,
)


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


def _can_show_ai_draw(config: dict) -> bool:
    return (
        is_qqcc_main_button_enabled(config, "ai_draw")
        and has_enabled_qqcc_draw_scenes(config)
    )


def _can_show_video_edit(config: dict) -> bool:
    return (
        is_qqcc_main_button_enabled(config, "video_edit")
        and has_enabled_qqcc_video_scenes(config)
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
    if is_qqcc_global_enabled(config) and _can_show_ai_draw(config):
        feature_row.append(get_text("qqcc.menu.ai_draw", lang))
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
    route_texts = [scene["name"] for scene in get_enabled_qqcc_video_scenes(config)]
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
            scene["name"],
            callback_data=build_quick_video_scene_callback_data(scene["id"]),
        )
        for scene in get_enabled_qqcc_video_scenes(config)
    ]
    keyboard = [buttons[index : index + 3] for index in range(0, len(buttons), 3)]
    return InlineKeyboardMarkup(keyboard)


def get_qqcc_draw_edit_inline_keyboard(
    lang: str,
    config: dict | None = None,
) -> InlineKeyboardMarkup:
    config = normalize_qqcc_config(config)
    buttons = [
        InlineKeyboardButton(
            scene["name"],
            callback_data=build_quick_draw_scene_callback_data(scene["id"]),
        )
        for scene in get_enabled_qqcc_draw_scenes(config)
    ]
    keyboard = [buttons[index : index + 3] for index in range(0, len(buttons), 3)]
    return InlineKeyboardMarkup(keyboard)
