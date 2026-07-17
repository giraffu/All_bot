from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

from src.handlers.fsm.quick_draw_callback_data import (
    build_quick_filter_scene_callback_data,
    build_quick_draw_scene_callback_data,
)
from src.handlers.fsm.quick_video_callback_data import (
    build_quick_ai_video_scene_callback_data,
    build_quick_video_scene_callback_data,
)
from src.i18n.translator import get_text
from src.services.qqcc_config_service import (
    get_enabled_qqcc_draw_scenes,
    get_enabled_qqcc_filter_scenes,
    get_enabled_qqcc_video_scenes,
    get_enabled_qqcc_ai_video_scenes,
    has_enabled_qqcc_draw_scenes,
    has_enabled_qqcc_filter_scenes,
    has_enabled_qqcc_video_scenes,
    has_enabled_qqcc_ai_video_scenes,
    is_qqcc_global_enabled,
    is_qqcc_main_bot_link_enabled,
    is_qqcc_main_button_enabled,
    is_qqcc_private_bot_entry_enabled,
    normalize_qqcc_config,
)


def _can_show_quick_faceswap(config: dict) -> bool:
    return is_qqcc_main_button_enabled(config, "quick_faceswap")


def _can_show_ai_draw(config: dict) -> bool:
    return (
        is_qqcc_main_button_enabled(config, "ai_draw")
        and has_enabled_qqcc_draw_scenes(config)
    )


def _can_show_ai_filter(config: dict) -> bool:
    return (
        is_qqcc_main_button_enabled(config, "ai_filter")
        and has_enabled_qqcc_filter_scenes(config)
    )


def _can_show_video_edit(config: dict) -> bool:
    return (
        is_qqcc_main_button_enabled(config, "video_edit")
        and has_enabled_qqcc_video_scenes(config)
    )


def _can_show_ai_video(config: dict) -> bool:
    return (
        is_qqcc_main_button_enabled(config, "ai_video")
        and has_enabled_qqcc_ai_video_scenes(config)
    )


def _can_show_market(config: dict) -> bool:
    return is_qqcc_main_button_enabled(config, "market")


def _get_visible_qqcc_main_menu_buttons(
    lang: str,
    config: dict,
    *,
    include_private_bot_entry: bool,
) -> dict[str, str]:
    global_enabled = is_qqcc_global_enabled(config)
    candidates = (
        (
            "quick_faceswap",
            get_text("qqcc.menu.quick_faceswap", lang),
            global_enabled and _can_show_quick_faceswap(config),
        ),
        (
            "ai_draw",
            get_text("qqcc.menu.ai_draw", lang),
            global_enabled and _can_show_ai_draw(config),
        ),
        (
            "ai_filter",
            get_text("qqcc.menu.ai_filter", lang),
            global_enabled and _can_show_ai_filter(config),
        ),
        (
            "video_edit",
            get_text("qqcc.menu.video_edit", lang),
            global_enabled and _can_show_video_edit(config),
        ),
        (
            "ai_video",
            get_text("qqcc.menu.ai_video", lang),
            global_enabled and _can_show_ai_video(config),
        ),
        (
            "market",
            get_text("qqcc.menu.market", lang),
            global_enabled and _can_show_market(config),
        ),
        (
            "private_bot",
            get_text("qqcc.menu.private_bot", lang),
            include_private_bot_entry
            and is_qqcc_private_bot_entry_enabled(config),
        ),
        (
            "main_bot_link",
            get_text("menu.open_main_bot", lang),
            is_qqcc_main_bot_link_enabled(config),
        ),
    )
    return {key: label for key, label, is_visible in candidates if is_visible}


def _build_legacy_qqcc_main_menu_rows(
    visible_buttons: dict[str, str],
) -> list[list[str]]:
    keyboard: list[list[str]] = []
    quick_faceswap = visible_buttons.get("quick_faceswap")
    if quick_faceswap:
        keyboard.append([quick_faceswap])

    feature_row = [
        visible_buttons[key]
        for key in ("ai_draw", "ai_filter", "video_edit", "ai_video")
        if key in visible_buttons
    ]
    if feature_row:
        keyboard.append(feature_row)

    for key in ("market", "private_bot", "main_bot_link"):
        label = visible_buttons.get(key)
        if label:
            keyboard.append([label])
    return keyboard


def get_qqcc_main_menu_keyboard(
    lang: str,
    config: dict | None = None,
    *,
    include_private_bot_entry: bool = True,
) -> ReplyKeyboardMarkup:
    config = normalize_qqcc_config(config)
    visible_buttons = _get_visible_qqcc_main_menu_buttons(
        lang,
        config,
        include_private_bot_entry=include_private_bot_entry,
    )
    layout = config["main_menu_layout"]
    buttons_per_row = layout["buttons_per_row"]
    if buttons_per_row is None:
        keyboard = _build_legacy_qqcc_main_menu_rows(visible_buttons)
    else:
        ordered_buttons = [
            visible_buttons[key]
            for key in layout["button_order"]
            if key in visible_buttons
        ]
        keyboard = [
            ordered_buttons[index : index + buttons_per_row]
            for index in range(0, len(ordered_buttons), buttons_per_row)
        ]
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


def get_qqcc_ai_video_inline_keyboard(
    lang: str,
    config: dict | None = None,
) -> InlineKeyboardMarkup:
    config = normalize_qqcc_config(config)
    buttons = [
        InlineKeyboardButton(
            scene["name"],
            callback_data=build_quick_ai_video_scene_callback_data(scene["id"]),
        )
        for scene in get_enabled_qqcc_ai_video_scenes(config)
    ]
    return InlineKeyboardMarkup(
        [buttons[index : index + 3] for index in range(0, len(buttons), 3)]
    )


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


def get_qqcc_filter_edit_inline_keyboard(
    lang: str,
    config: dict | None = None,
) -> InlineKeyboardMarkup:
    config = normalize_qqcc_config(config)
    buttons = [
        InlineKeyboardButton(
            scene["name"],
            callback_data=build_quick_filter_scene_callback_data(scene["id"]),
        )
        for scene in get_enabled_qqcc_filter_scenes(config)
    ]
    keyboard = [buttons[index : index + 3] for index in range(0, len(buttons), 3)]
    return InlineKeyboardMarkup(keyboard)
