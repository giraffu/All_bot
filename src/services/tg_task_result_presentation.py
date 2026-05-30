from config import ENABLE_PUBLIC_SHARE
from src.constants import (
    MODE_CUSTOM_VIDEO,
    MODE_EDIT,
    MODE_FACESWAP_STEP1,
    MODE_I2I_PRO,
    MODE_IMAGE_TO_VIDEO,
    MODE_IMG2IMG_LORA,
    MODE_LTX_VIDEO,
    MODE_MASTURBATION,
    MODE_NAME_MAP,
    MODE_PENETRATION_STEP1,
    MODE_UNDRESS,
    MODE_WAN22_VIDEO_V2,
)
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def _supports_gallery_submission(task_type: str, allow_contribute: bool) -> bool:
    allowed_gallery_types = {
        MODE_I2I_PRO,
        MODE_EDIT,
        MODE_CUSTOM_VIDEO,
        MODE_IMAGE_TO_VIDEO,
        MODE_LTX_VIDEO,
        MODE_WAN22_VIDEO_V2,
        MODE_IMG2IMG_LORA,
    }
    return allow_contribute and task_type in allowed_gallery_types


def _build_gallery_button_row(task_id: str) -> list[InlineKeyboardButton]:
    return [
        InlineKeyboardButton(
            "🚀 一键投稿至广场",
            callback_data=f"submit_gallery_{task_id}",
        )
    ]


def _build_default_result_keyboard() -> list[list[InlineKeyboardButton]]:
    keyboard = [
        [
            InlineKeyboardButton("👍", callback_data="rate_like"),
            InlineKeyboardButton("👎", callback_data="rate_dislike"),
        ]
    ]
    if ENABLE_PUBLIC_SHARE:
        keyboard.insert(
            0,
            [InlineKeyboardButton("公开", callback_data="public_share_request")],
        )
    return keyboard


def _ensure_gallery_button(
    reply_markup: InlineKeyboardMarkup,
    *,
    task_id: str,
) -> InlineKeyboardMarkup:
    has_gallery = any(
        btn.callback_data and btn.callback_data.startswith("submit_gallery_")
        for row in reply_markup.inline_keyboard
        for btn in row
    )
    if has_gallery:
        return reply_markup

    new_keyboard = [list(row) for row in reply_markup.inline_keyboard]
    new_keyboard.insert(0, _build_gallery_button_row(task_id))
    return InlineKeyboardMarkup(new_keyboard)


def build_result_reply_markup(
    task_type,
    task_id,
    allow_contribute,
    reply_markup,
):
    show_gallery_btn = _supports_gallery_submission(task_type, allow_contribute)
    if reply_markup:
        if show_gallery_btn:
            return _ensure_gallery_button(reply_markup, task_id=task_id)
        return reply_markup

    keyboard = _build_default_result_keyboard()
    if show_gallery_btn:
        keyboard.insert(0, _build_gallery_button_row(task_id))
    return InlineKeyboardMarkup(keyboard)


def resolve_result_mode_name(task_type):
    mode_name = MODE_NAME_MAP.get(task_type, task_type)
    if task_type == "face_swap":
        return MODE_NAME_MAP.get(MODE_FACESWAP_STEP1)
    if task_type == "penetration":
        return MODE_NAME_MAP.get(MODE_PENETRATION_STEP1)
    if task_type == "undress":
        return MODE_NAME_MAP.get(MODE_UNDRESS)
    if task_type == "masturbation":
        return MODE_NAME_MAP.get(MODE_MASTURBATION)
    return mode_name


def record_result_message_meta(context, sent_msg, task_type, prompt, task_id):
    if not sent_msg:
        return
    context.bot_data[f"msg_meta_{sent_msg.message_id}"] = {
        "mode_name": resolve_result_mode_name(task_type),
        "prompt": prompt,
        "task_id": task_id,
    }
