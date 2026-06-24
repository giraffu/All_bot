from functools import lru_cache

from telegram import ReplyKeyboardMarkup

from src.i18n.translator import get_text


@lru_cache(maxsize=10)
def get_qqcc_main_menu_keyboard(lang: str) -> ReplyKeyboardMarkup:
    keyboard = [
        [get_text("menu.photo_edit_undress", lang)],
        [
            get_text("menu.photo_edit", lang),
            get_text("menu.video_edit", lang),
        ],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


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
