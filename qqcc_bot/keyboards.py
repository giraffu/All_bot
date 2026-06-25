from functools import lru_cache

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

from src.i18n.translator import get_text


@lru_cache(maxsize=10)
def get_qqcc_main_menu_keyboard(lang: str) -> ReplyKeyboardMarkup:
    keyboard = [
        [get_text("menu.photo_edit_undress", lang)],
        [
            get_text("menu.photo_edit", lang),
            get_text("menu.video_edit", lang),
        ],
        [get_text("menu.open_main_bot", lang)],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_qqcc_main_bot_link_keyboard(
    lang: str, main_bot_url: str
) -> InlineKeyboardMarkup:
    button = InlineKeyboardButton(
        get_text("menu.open_main_bot", lang),
        url=main_bot_url,
    )
    return InlineKeyboardMarkup([[button]])


@lru_cache(maxsize=10)
def get_qqcc_photo_edit_keyboard(lang: str) -> ReplyKeyboardMarkup:
    keyboard = [
        [get_text("menu.photo_edit_masturbation", lang)],
        [get_text("menu.photo_edit_random_faceswap", lang)],
        [get_text("menu.back_main", lang)],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


@lru_cache(maxsize=10)
def get_qqcc_video_edit_keyboard(lang: str) -> ReplyKeyboardMarkup:
    keyboard = [
        [
            get_text("menu.video_edit_missionary", lang),
            get_text("menu.video_edit_doggy", lang),
        ],
        [
            get_text("menu.video_edit_blowjob", lang),
            get_text("menu.video_edit_undress_tongue", lang),
            get_text("menu.video_edit_closeup_blowjob", lang),
        ],
        [get_text("menu.back_main", lang)],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
