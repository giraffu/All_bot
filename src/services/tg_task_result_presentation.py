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
from src.domain_config.scail2_video import (
    SCAIL2_ACTION_TRANSFER_TASK_TYPE,
    SCAIL2_FACE_SWAP_V2_TASK_TYPE,
    SCAIL2_VIDEO_REPLACEMENT_TASK_TYPE,
)
from src.domain_config.wan22_aio_video import is_wan22_chain_history_task_type
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

WAN22_EXTEND_CALLBACK_PREFIX = "wan22v2_extend"
WAN22_REGENERATE_CALLBACK_PREFIX = "wan22v2_regenerate"
WAN22_STITCH_CALLBACK_PREFIX = "wan22v2_stitch_chain"
GALLERY_SUBMIT_CALLBACK_PREFIX = "submit_gallery_"


def build_task_bound_callback_data(prefix: str, task_id: str) -> str:
    normalized_task_id = str(task_id or "").strip()
    if not normalized_task_id:
        return prefix
    return f"{prefix}:{normalized_task_id}"


def resolve_task_id_from_callback_data(callback_data: str | None, prefix: str) -> str:
    normalized_data = str(callback_data or "").strip()
    token = f"{prefix}:"
    if not normalized_data.startswith(token):
        return ""
    return normalized_data.removeprefix(token).strip()


def resolve_task_id_from_reply_markup(reply_markup: InlineKeyboardMarkup | None) -> str:
    if reply_markup is None:
        return ""
    for row in getattr(reply_markup, "inline_keyboard", []) or []:
        for button in row:
            callback_data = str(getattr(button, "callback_data", "") or "").strip()
            if callback_data.startswith(GALLERY_SUBMIT_CALLBACK_PREFIX):
                return callback_data.removeprefix(GALLERY_SUBMIT_CALLBACK_PREFIX).strip()
    return ""


def _supports_gallery_submission(task_type: str, allow_contribute: bool) -> bool:
    allowed_gallery_types = {
        MODE_I2I_PRO,
        MODE_EDIT,
        MODE_CUSTOM_VIDEO,
        MODE_IMAGE_TO_VIDEO,
        MODE_LTX_VIDEO,
        MODE_WAN22_VIDEO_V2,
        MODE_IMG2IMG_LORA,
        SCAIL2_ACTION_TRANSFER_TASK_TYPE,
        SCAIL2_VIDEO_REPLACEMENT_TASK_TYPE,
        SCAIL2_FACE_SWAP_V2_TASK_TYPE,
    }
    return allow_contribute and task_type in allowed_gallery_types


def _build_gallery_button_row(task_id: str) -> list[InlineKeyboardButton]:
    return [
        InlineKeyboardButton(
            "🚀 一键投稿至广场",
            callback_data=f"{GALLERY_SUBMIT_CALLBACK_PREFIX}{task_id}",
        )
    ]


def _supports_wan22_extension(task_type: str, result_meta: dict | None) -> bool:
    return is_wan22_chain_history_task_type(task_type) and isinstance(result_meta, dict)


def _supports_wan22_regenerate(task_type: str, result_meta: dict | None) -> bool:
    return is_wan22_chain_history_task_type(task_type) and bool(
        isinstance(result_meta, dict) and result_meta.get("wan22_prev_task_id")
    )


def _supports_wan22_stitch(task_type: str, result_meta: dict | None) -> bool:
    return _supports_wan22_regenerate(task_type, result_meta)


def _build_wan22_extension_button(
    task_id: str,
    result_meta: dict | None,
) -> InlineKeyboardButton | None:
    if not isinstance(result_meta, dict):
        return None
    resolution_preset = str(result_meta.get("wan22_resolution_preset") or "").strip()
    if not resolution_preset:
        return None
    return InlineKeyboardButton(
        "✨ 扩展生成",
        callback_data=build_task_bound_callback_data(
            WAN22_EXTEND_CALLBACK_PREFIX,
            task_id,
        ),
    )


def _build_wan22_regenerate_button(task_id: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        "🔁 重新生成",
        callback_data=build_task_bound_callback_data(
            WAN22_REGENERATE_CALLBACK_PREFIX,
            task_id,
        ),
    )


def _build_wan22_stitch_button(task_id: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        "🔗 完成拼接",
        callback_data=build_task_bound_callback_data(
            WAN22_STITCH_CALLBACK_PREFIX,
            task_id,
        ),
    )


def _build_result_action_rows(
    *,
    task_type: str,
    task_id: str,
    allow_contribute: bool,
    result_meta: dict | None,
) -> list[list[InlineKeyboardButton]]:
    rows: list[list[InlineKeyboardButton]] = []
    primary_row: list[InlineKeyboardButton] = []
    if _supports_gallery_submission(task_type, allow_contribute):
        primary_row.extend(_build_gallery_button_row(task_id))
    if _supports_wan22_regenerate(task_type, result_meta):
        primary_row.append(_build_wan22_regenerate_button(task_id))
    if _supports_wan22_extension(task_type, result_meta):
        extension_button = _build_wan22_extension_button(
            task_id=task_id,
            result_meta=result_meta,
        )
        if extension_button is not None:
            primary_row.append(extension_button)
    if primary_row:
        rows.append(primary_row)
    if _supports_wan22_stitch(task_type, result_meta):
        rows.append([_build_wan22_stitch_button(task_id)])
    return rows


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
    task_type: str,
    task_id: str,
    allow_contribute: bool,
    result_meta: dict | None,
) -> InlineKeyboardMarkup:
    expected_rows = _build_result_action_rows(
        task_type=task_type,
        task_id=task_id,
        allow_contribute=allow_contribute,
        result_meta=result_meta,
    )
    expected_buttons = [btn for row in expected_rows for btn in row]
    if not expected_buttons:
        return reply_markup

    existing_callbacks = {
        btn.callback_data
        for row in reply_markup.inline_keyboard
        for btn in row
        if btn.callback_data
    }
    missing_buttons = [
        btn for btn in expected_buttons if btn.callback_data not in existing_callbacks
    ]
    if not missing_buttons:
        return reply_markup

    new_keyboard = [list(row) for row in reply_markup.inline_keyboard]
    new_keyboard.insert(0, missing_buttons)
    return InlineKeyboardMarkup(new_keyboard)


def build_result_reply_markup(
    task_type,
    task_id,
    allow_contribute,
    reply_markup,
    result_meta: dict | None = None,
):
    if reply_markup:
        return _ensure_gallery_button(
            reply_markup,
            task_type=task_type,
            task_id=task_id,
            allow_contribute=allow_contribute,
            result_meta=result_meta,
        )

    keyboard = _build_default_result_keyboard()
    action_rows = _build_result_action_rows(
        task_type=task_type,
        task_id=task_id,
        allow_contribute=allow_contribute,
        result_meta=result_meta,
    )
    if action_rows:
        keyboard = action_rows + keyboard
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


def record_result_message_meta(
    context,
    sent_msg,
    task_type,
    prompt,
    task_id,
    *,
    result_meta: dict | None = None,
):
    if not sent_msg:
        return
    meta = {
        "mode_name": resolve_result_mode_name(task_type),
        "task_type": task_type,
        "prompt": prompt,
        "task_id": task_id,
    }
    if isinstance(result_meta, dict):
        meta.update(result_meta)
    context.bot_data[f"msg_meta_{sent_msg.message_id}"] = meta
