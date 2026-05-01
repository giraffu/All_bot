from functools import lru_cache
from telegram import ReplyKeyboardMarkup
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
