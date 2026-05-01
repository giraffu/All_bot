from functools import lru_cache
from telegram import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from src.i18n.translator import get_text

@lru_cache(maxsize=10)
def get_main_menu_keyboard(lang: str) -> ReplyKeyboardMarkup:
    """
    动态生成并缓存多语言主菜单键盘。
    """
    keyboard = [
        [get_text("menu.gallery", lang), get_text("menu.recharge", lang), get_text("menu.checkin", lang), get_text("menu.profile", lang)],
        [get_text("menu.share", lang), get_text("menu.queue", lang)],
        [get_text("menu.photo_edit", lang), get_text("menu.video_edit", lang), get_text("menu.face_video", lang)],
        [get_text("menu.i2i_pro", lang), get_text("menu.free_edit", lang)],
        [get_text("menu.video_lora", lang), get_text("menu.custom_video", lang), get_text("menu.ltx_video", lang)]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

@lru_cache(maxsize=10)
def get_photo_edit_keyboard(lang: str) -> ReplyKeyboardMarkup:
    keyboard = [
        [get_text("menu.photo_edit_undress", lang), get_text("menu.photo_edit_faceswap", lang), get_text("menu.photo_edit_masturbation", lang)],
        [get_text("menu.photo_edit_random_faceswap", lang)],
        [get_text("menu.back_main", lang)]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

@lru_cache(maxsize=10)
def get_video_edit_keyboard(lang: str) -> ReplyKeyboardMarkup:
    keyboard = [
        [get_text("menu.video_edit_missionary", lang), get_text("menu.video_edit_doggy", lang)],
        [get_text("menu.video_edit_blowjob", lang), get_text("menu.video_edit_undress_tongue", lang), get_text("menu.video_edit_closeup_blowjob", lang)],
        [get_text("menu.back_main", lang)]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

@lru_cache(maxsize=10)
def get_gallery_keyboard(lang: str) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(get_text("menu.gallery_latest", lang), callback_data="gallery_catmenu_latest")],
        [InlineKeyboardButton(get_text("menu.gallery_likes", lang), callback_data="gallery_catmenu_likes")],
        [InlineKeyboardButton(get_text("menu.gallery_applied", lang), callback_data="gallery_catmenu_applied")],
        [InlineKeyboardButton(get_text("menu.gallery_mine", lang), callback_data="gallery_catmenu_mine")]
    ]
    return InlineKeyboardMarkup(keyboard)

