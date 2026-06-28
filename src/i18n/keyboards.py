from functools import lru_cache

from telegram import ReplyKeyboardMarkup

from config import ENABLE_FREE_EDIT_V2
from src.i18n.translator import get_text


@lru_cache(maxsize=10)
def get_main_menu_keyboard(lang: str) -> ReplyKeyboardMarkup:
    """
    动态生成并缓存多语言主菜单键盘。
    """
    keyboard = [
        [
            get_text("menu.gallery", lang),
            get_text("menu.recharge", lang),
            get_text("menu.checkin", lang),
            get_text("menu.profile", lang),
        ],
        [
            get_text("menu.share", lang),
            get_text("menu.queue", lang),
            get_text("menu.switch_lang", lang),
        ],
        [
            get_text("menu.photo_edit", lang),
            get_text("menu.video_edit", lang),
            get_text("menu.video_to_video", lang),
        ],
        [
            get_text("menu.txt2img", lang),
            get_text("menu.i2i_pro", lang),
            get_text("menu.free_edit", lang),
        ],
        *(
            [[get_text("menu.free_edit_v2", lang)]]
            if ENABLE_FREE_EDIT_V2
            else []
        ),
        [
            get_text("menu.video_lora", lang),
            get_text("menu.ltx_video", lang),
            get_text("menu.wan22_video_v2", lang),
        ],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


@lru_cache(maxsize=10)
def get_photo_edit_keyboard(lang: str) -> ReplyKeyboardMarkup:
    keyboard = [
        [
            get_text("menu.photo_edit_undress", lang),
            get_text("menu.photo_edit_faceswap", lang),
            get_text("menu.photo_edit_masturbation", lang),
        ],
        [get_text("menu.photo_edit_random_faceswap", lang)],
        [get_text("menu.back_main", lang)],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


@lru_cache(maxsize=10)
def get_video_edit_keyboard(lang: str) -> ReplyKeyboardMarkup:
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


@lru_cache(maxsize=10)
def get_video_to_video_keyboard(lang: str) -> ReplyKeyboardMarkup:
    keyboard = [
        [
            get_text("menu.video_to_video_replacement", lang),
            get_text("menu.video_to_video_action_transfer", lang),
        ],
        [get_text("menu.face_video", lang)],
        [get_text("menu.back_main", lang)],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
