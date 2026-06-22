import logging
import os
from pathlib import Path
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from src.constants import (
    LTX_DURATION_MULTIPLIER,
    LTX_RESOLUTION_COST,
    get_ltx_video_settings_keyboard,
)
from src.handlers.fsm.fsm_shared import (
    handle_standard_fsm_cancel,
    handle_standard_fsm_timeout,
    handle_standard_fsm_unexpected_input,
    translate_fsm_text,
)
from src.handlers.conversation_states import LtxVideoState
from src.handlers.prompt_router import is_global_menu_command
from src.lora_catalog import (
    LTX_VIDEO_LORA_OPTIONS,
    build_ltx_video_lora_item,
    get_ltx_video_lora_display_name,
    normalize_ltx_video_lora_items,
    resolve_ltx_video_lora_name,
)
from src.services.task_service_entrypoints_specialized import process_ltx_video_task
from src.services.ltx_video_extension_service import (
    LtxVideoExtensionError,
    build_ltx_full_chain_task_ids,
    download_ltx_last_frame_to_fsm_temp,
    extract_ltx_history_context,
    load_owned_ltx_history,
    normalize_ltx_video_chain_task_ids,
)
from src.services.permission_service import permission_service
from src.services.fsm_temp_file_service import (
    cleanup_fsm_temp_files,
    download_telegram_file_to_fsm_temp,
)
from src.utils import (
    create_background_task,
    robust_edit_text,
    robust_reply_text,
)
import contextlib

from src.filters.i18n_filter import I18nFilter
from src.services.tg_task_result_presentation import (
    LTX_EXTEND_CALLBACK_PREFIX,
    resolve_task_id_from_callback_data,
    resolve_task_id_from_reply_markup,
)

logger = logging.getLogger("fsm.ltx_video")

MAX_LTX_VIDEO_LORAS = 3
LTX_VIDEO_DATA_KEY = "ltx_video_data"
LTX_VIDEO_CONVERSATION_TAG = "LTX_VIDEO"
LTX_MODE_I2V = "i2v"
LTX_MODE_FLF2V = "flf2v"
LTX_MODE_V2V_AUDIO = "v2v_audio"
LTX_SETUP_CONFIRM_CALLBACK = "ltx_setup_confirm"
LTX_V2V_AUDIO_DISABLED_MESSAGE = "视频配音暂未开放，请选择单首帧或首尾帧。"
LTX_MAX_INPUT_VIDEO_MB = 40
LTX_MAX_INPUT_VIDEO_BYTES = LTX_MAX_INPUT_VIDEO_MB * 1024 * 1024
_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
_VIDEO_SUFFIXES = {".mp4", ".mov", ".webm", ".avi", ".mkv"}


_t = translate_fsm_text


def _build_settings_message(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    resolution: str,
    duration: str,
    cost: int,
    lora_items: list[dict[str, Any]] | None = None,
    english_prompt_only: bool = False,
) -> str:
    key = (
        "fsm.ltx_video.settings_text_english_prompt"
        if english_prompt_only
        else "fsm.ltx_video.settings_text"
    )
    message = _t(
        context,
        key,
        resolution=resolution,
        duration=duration,
        cost=cost,
    )
    lora_text = _build_lora_summary_text(
        context,
        lora_items or [],
        empty_key="fsm.image_to_video.current_lora",
    )
    return f"{message}\n\n{lora_text}"


def _get_ltx_video_items(fsm_data: dict[str, Any]) -> list[dict[str, Any]]:
    return normalize_ltx_video_lora_items(
        fsm_data.get("lora_items"),
        max_items=MAX_LTX_VIDEO_LORAS,
    )


def _build_lora_summary_text(
    context: ContextTypes.DEFAULT_TYPE,
    lora_items: list[dict[str, Any]],
    *,
    empty_key: str | None = None,
) -> str:
    lang = getattr(context, "lang", "zh")
    if not lora_items:
        empty_name = get_ltx_video_lora_display_name("", lang)
        if empty_key:
            return _t(context, empty_key, model_name=empty_name)
        return f"当前附加模型: {empty_name}"

    display_items = ", ".join(
        f"{get_ltx_video_lora_display_name(str(item['name']), lang)}({float(item['strength']):.2f})"
        for item in lora_items
    )
    return f"当前附加模型: {display_items}"


def _build_ltx_lora_selection_keyboard(
    context_or_lang: ContextTypes.DEFAULT_TYPE | str,
    lora_items: list[dict[str, Any]] | None = None,
) -> InlineKeyboardMarkup:
    lang = (
        context_or_lang
        if isinstance(context_or_lang, str)
        else getattr(context_or_lang, "lang", "zh")
    )
    lora_items = lora_items or []
    selected_names = {str(item["name"]) for item in lora_items}
    buttons = []
    for option_id in LTX_VIDEO_LORA_OPTIONS.keys():
        lora_name = resolve_ltx_video_lora_name(option_id)
        if not lora_name:
            continue
        prefix = "✅ " if lora_name in selected_names else ""
        buttons.append(
            InlineKeyboardButton(
                f"{prefix}{get_ltx_video_lora_display_name(lora_name, lang)}",
                callback_data=f"toggle_ltx_lora_{option_id}",
            )
        )
    keyboard = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    keyboard.append(
        [
            InlineKeyboardButton("完成选择", callback_data="done_ltx_lora_select"),
            InlineKeyboardButton("清空", callback_data="clear_ltx_lora_select"),
        ]
    )
    keyboard.append(
        [InlineKeyboardButton("跳过附加模型", callback_data="skip_ltx_lora_select")]
    )
    return InlineKeyboardMarkup(keyboard)


def _ltx_mode_label(mode: str, lang: str = "zh") -> str:
    if lang == "en":
        return {
            LTX_MODE_FLF2V: "Start/end frames",
            LTX_MODE_V2V_AUDIO: "Video audio",
        }.get(mode, "Single start frame")
    return {
        LTX_MODE_FLF2V: "首尾帧",
        LTX_MODE_V2V_AUDIO: "视频配音",
    }.get(mode, "单首帧")


def _build_initial_setup_keyboard(
    context: ContextTypes.DEFAULT_TYPE,
    fsm_data: dict[str, Any],
) -> InlineKeyboardMarkup:
    lang = getattr(context, "lang", "zh")
    current_mode = str(fsm_data.get("ltx_mode") or LTX_MODE_I2V)
    mode_row = [
        InlineKeyboardButton(
            f"{'✅ ' if current_mode == LTX_MODE_I2V else ''}{_ltx_mode_label(LTX_MODE_I2V, lang)}",
            callback_data="ltx_mode_i2v",
        ),
        InlineKeyboardButton(
            f"{'✅ ' if current_mode == LTX_MODE_FLF2V else ''}{_ltx_mode_label(LTX_MODE_FLF2V, lang)}",
            callback_data="ltx_mode_flf2v",
        ),
    ]
    settings_markup = get_ltx_video_settings_keyboard(
        "default",
        "外门弟子",
        str(fsm_data.get("resolution") or "1280x704"),
        str(fsm_data.get("duration") or "5s"),
        lang,
    )
    confirm_text = "Confirm, upload media" if lang == "en" else "确定，上传素材"
    keyboard = [mode_row]
    keyboard.extend([list(row) for row in settings_markup.inline_keyboard])
    keyboard.append(
        [InlineKeyboardButton(confirm_text, callback_data=LTX_SETUP_CONFIRM_CALLBACK)]
    )
    return InlineKeyboardMarkup(keyboard)


def _build_initial_setup_message(
    context: ContextTypes.DEFAULT_TYPE,
    fsm_data: dict[str, Any],
) -> str:
    lang = getattr(context, "lang", "zh")
    res = str(fsm_data.get("resolution") or "1280x704")
    dur = str(fsm_data.get("duration") or "5s")
    multiplier = LTX_DURATION_MULTIPLIER.get(dur, 1.0)
    cost = int(LTX_RESOLUTION_COST.get(res, 10) * multiplier)
    mode_label = _ltx_mode_label(str(fsm_data.get("ltx_mode") or LTX_MODE_I2V), lang)
    lora_text = _build_lora_summary_text(
        context,
        _get_ltx_video_items(fsm_data),
        empty_key="fsm.image_to_video.current_lora",
    )
    if lang == "en":
        setup_text = (
            "Choose mode, quality and duration first.\n"
            f"Mode: {mode_label}\n"
            f"Quality: {res} | Duration: {dur} | Cost: {cost}\n\n"
            "Tap Confirm, then upload the required media."
        )
    else:
        setup_text = (
            "请先选择生成模式、清晰度和时长。\n"
            f"模式：{mode_label}\n"
            f"清晰度：{res} | 时长：{dur} | 消耗灵石：{cost}\n\n"
            "点“确定”后再上传素材。"
        )
    return f"{lora_text}\n\n{setup_text}"


def _build_image_request_text(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    lora_items: list[dict[str, Any]],
) -> str:
    return (
        f"{_build_lora_summary_text(context, lora_items, empty_key='fsm.image_to_video.current_lora')}\n\n"
        f"{_t(context, 'fsm.ltx_video.start')}"
    )


def _build_prompt_request_text(
    context: ContextTypes.DEFAULT_TYPE,
    fsm_data: dict[str, Any],
) -> str:
    res = str(fsm_data.get("resolution") or "1280x704")
    dur = str(fsm_data.get("duration") or "5s")
    base_cost = LTX_RESOLUTION_COST.get(res, 10)
    multiplier = LTX_DURATION_MULTIPLIER.get(dur, 1.0)
    cost = int(base_cost * multiplier)
    lang = getattr(context, "lang", "zh")
    key = "fsm.ltx_video.prompt_request_text"
    prompt_request_text = _t(
        context,
        key,
        resolution=res,
        duration=dur,
        cost=cost,
        mode=_ltx_mode_label(str(fsm_data.get("ltx_mode") or LTX_MODE_I2V), lang),
    )
    lora_text = _build_lora_summary_text(
        context,
        _get_ltx_video_items(fsm_data),
        empty_key="fsm.image_to_video.current_lora",
    )
    return f"{prompt_request_text}\n\n{lora_text}"


def _build_lora_selection_message(
    context: ContextTypes.DEFAULT_TYPE,
    lora_items: list[dict[str, Any]],
) -> str:
    suffix = (
        "可多选，最多 3 个。提交时将自动使用各模型默认强度。"
        if getattr(context, "lang", "zh") != "en"
        else "You can select up to 3 LoRAs. Each one uses its default strength automatically."
    )
    return f"{_t(context, 'fsm.ltx_video.select_lora')}\n\n{_build_lora_summary_text(context, lora_items)}\n{suffix}"


def _safe_suffix(file_name: str | None, *, default: str, allowed: set[str]) -> str:
    suffix = Path(file_name or "").suffix.lower()
    return suffix if suffix in allowed else default


def _extract_image_file(update: Update) -> tuple[str | None, str]:
    message = update.message
    if not message:
        return None, ".png"

    if message.document:
        mime_type = message.document.mime_type or ""
        if not mime_type.startswith("image/"):
            return None, ".png"
        return (
            message.document.file_id,
            _safe_suffix(
                message.document.file_name,
                default=".png",
                allowed=_IMAGE_SUFFIXES,
            ),
        )

    if message.photo:
        return message.photo[-1].file_id, ".jpg"

    return None, ".png"


def _extract_video_file(update: Update) -> tuple[str | None, str, int | None, bool]:
    message = update.message
    if not message:
        return None, ".mp4", None, False

    if message.document:
        mime_type = message.document.mime_type or ""
        if not mime_type.startswith("video/"):
            return None, ".mp4", None, True
        return (
            message.document.file_id,
            _safe_suffix(
                message.document.file_name,
                default=".mp4",
                allowed=_VIDEO_SUFFIXES,
            ),
            message.document.file_size,
            True,
        )

    if message.video:
        return message.video.file_id, ".mp4", message.video.file_size, False

    return None, ".mp4", None, False


def _is_video_too_large(size: int | None) -> bool:
    return bool(size and size > LTX_MAX_INPUT_VIDEO_BYTES)


def _cleanup_context(context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("in_conversation", None)
    pending_files = context.user_data.pop(LTX_VIDEO_DATA_KEY, {})
    cleanup_fsm_temp_files(
        [
            pending_files.get("image_path"),
            pending_files.get("end_image_path"),
            pending_files.get("video_path"),
        ]
    )


def _release_context_without_files(context: ContextTypes.DEFAULT_TYPE) -> dict[str, Any]:
    context.user_data.pop("in_conversation", None)
    return context.user_data.pop(LTX_VIDEO_DATA_KEY, {}) or {}


def _resolve_callback_task_id(
    *,
    meta: dict[str, Any],
    query,
    callback_prefix: str,
) -> str:
    task_id = resolve_task_id_from_callback_data(
        getattr(query, "data", None),
        callback_prefix,
    )
    if task_id:
        return task_id
    task_id = str(meta.get("task_id") or "").strip()
    if task_id:
        return task_id
    message = getattr(query, "message", None)
    return resolve_task_id_from_reply_markup(getattr(message, "reply_markup", None))


def _duration_label_from_history(history) -> str:
    try:
        duration = int(getattr(history, "requested_duration", None) or 5)
    except (TypeError, ValueError):
        duration = 5
    if duration not in {5, 10, 15, 20}:
        duration = 5
    return f"{duration}s"


def _resolution_from_history(history) -> str:
    resolution = str(getattr(history, "billing_resolution", None) or "").strip()
    return resolution if resolution == "1280x704" else "1280x704"


def _resolve_lora_items_from_meta(meta: dict[str, Any]) -> list[dict[str, Any]]:
    lora_items = normalize_ltx_video_lora_items(
        meta.get("lora_items"),
        max_items=MAX_LTX_VIDEO_LORAS,
    )
    if lora_items:
        return lora_items
    fallback_lora_name = str(meta.get("lora_name") or "").strip()
    if not fallback_lora_name:
        return []
    fallback_item = build_ltx_video_lora_item(
        fallback_lora_name,
        strength=meta.get("lora_strength"),
    )
    return [fallback_item] if fallback_item else []


def _merge_history_context_into_meta(history, meta: dict[str, Any]) -> dict[str, Any]:
    return {
        **extract_ltx_history_context(getattr(history, "extra_outputs", None)),
        **meta,
    }


async def _send_settings_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    message,
    english_prompt_only: bool = False,
) -> int:
    user_id = update.effective_user.id

    from src.core.user_core import get_or_create_user_by_telegram

    internal_user, _ = await get_or_create_user_by_telegram(user_id)
    internal_user_id = internal_user.id

    user_group = await permission_service.get_user_group(internal_user_id)
    user_identity = await permission_service.get_user_identity(internal_user_id)

    fsm_data = context.user_data[LTX_VIDEO_DATA_KEY]
    res = fsm_data["resolution"]
    dur = fsm_data["duration"]
    reply_markup = get_ltx_video_settings_keyboard(
        user_group, user_identity, res, dur, getattr(context, "lang", "zh")
    )

    base_cost = LTX_RESOLUTION_COST.get(res, 10)
    multiplier = LTX_DURATION_MULTIPLIER.get(dur, 1.0)
    cost = int(base_cost * multiplier)

    msg_text = _build_settings_message(
        context,
        resolution=res,
        duration=dur,
        cost=cost,
        lora_items=_get_ltx_video_items(fsm_data),
        english_prompt_only=english_prompt_only,
    )

    await robust_reply_text(
        message, msg_text, reply_markup=reply_markup, parse_mode="Markdown"
    )
    return LtxVideoState.WAIT_SETTINGS_AND_PROMPT


async def _send_prompt_request_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    message,
) -> int:
    fsm_data = context.user_data[LTX_VIDEO_DATA_KEY]
    await robust_reply_text(
        message,
        _build_prompt_request_text(context, fsm_data),
        parse_mode="Markdown",
    )
    return LtxVideoState.WAIT_SETTINGS_AND_PROMPT


async def start_ltx_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point for 高级图生视频"""
    query = update.callback_query
    if query:
        with contextlib.suppress(Exception):
            await query.answer(text=_t(context, "fsm.common.task_initializing"), cache_time=2)

    from src.utils import is_maintenance_mode

    if is_maintenance_mode():
        msg = _t(context, "fsm.common.maintenance")
        if update.callback_query:
            await robust_edit_text(
                update.callback_query.message, msg, parse_mode="Markdown"
            )
        else:
            await robust_reply_text(update.message, msg, parse_mode="Markdown")
        return ConversationHandler.END

    if context.user_data.get("in_conversation"):
        msg = _t(context, "fsm.common.conflict")
        await robust_reply_text(update.message, msg)
        return ConversationHandler.END

    context.user_data["in_conversation"] = LTX_VIDEO_CONVERSATION_TAG
    context.user_data[LTX_VIDEO_DATA_KEY] = {
        "resolution": "1280x704",
        "duration": "5s",
        "ltx_mode": LTX_MODE_I2V,
        "image_path": None,
        "end_image_path": None,
        "video_path": None,
        "lora_items": [],
    }

    msg = _build_lora_selection_message(context, [])
    await robust_reply_text(
        update.message,
        msg,
        reply_markup=_build_ltx_lora_selection_keyboard(getattr(context, "lang", "zh")),
        parse_mode="Markdown",
    )
    return LtxVideoState.WAIT_LORA_SELECTION


async def handle_lora_selection(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer(text=_t(context, "fsm.common.task_initializing"), cache_time=2)
    data = query.data or ""
    fsm_data = context.user_data.get(LTX_VIDEO_DATA_KEY)
    if not fsm_data:
        with contextlib.suppress(Exception):
            await query.answer(_t(context, "fsm.ltx_video.expired_alert"), show_alert=True)
        return ConversationHandler.END

    current_items = _get_ltx_video_items(fsm_data)

    if data.startswith("ltx_lora_select_"):
        selected_alias = data.replace("ltx_lora_select_", "", 1)
        lora_name = resolve_ltx_video_lora_name(selected_alias)
        if lora_name:
            item = build_ltx_video_lora_item(lora_name)
            fsm_data["lora_items"] = [item] if item else []
        await robust_edit_text(
            query.message,
            _build_initial_setup_message(context, fsm_data),
            reply_markup=_build_initial_setup_keyboard(context, fsm_data),
            parse_mode="Markdown",
        )
        return LtxVideoState.WAIT_MODE_SELECTION

    if data == "done_ltx_lora_select" or data == "skip_ltx_lora_select":
        if data == "skip_ltx_lora_select":
            fsm_data["lora_items"] = []
        await robust_edit_text(
            query.message,
            _build_initial_setup_message(context, fsm_data),
            reply_markup=_build_initial_setup_keyboard(context, fsm_data),
            parse_mode="Markdown",
        )
        return LtxVideoState.WAIT_MODE_SELECTION

    if data == "clear_ltx_lora_select":
        fsm_data["lora_items"] = []
        await robust_edit_text(
            query.message,
            _build_lora_selection_message(context, []),
            reply_markup=_build_ltx_lora_selection_keyboard(context, []),
            parse_mode="Markdown",
        )
        return LtxVideoState.WAIT_LORA_SELECTION

    if not data.startswith("toggle_ltx_lora_"):
        return LtxVideoState.WAIT_LORA_SELECTION

    selected_alias = data.replace("toggle_ltx_lora_", "", 1)
    lora_name = resolve_ltx_video_lora_name(selected_alias)
    if not lora_name:
        return LtxVideoState.WAIT_LORA_SELECTION

    existing_index = next(
        (index for index, item in enumerate(current_items) if str(item["name"]) == lora_name),
        None,
    )
    if existing_index is not None:
        current_items.pop(existing_index)
    else:
        if len(current_items) >= MAX_LTX_VIDEO_LORAS:
            await query.answer("最多只能选择 3 个附加模型", show_alert=True)
            return LtxVideoState.WAIT_LORA_SELECTION
        item = build_ltx_video_lora_item(lora_name)
        if item:
            current_items.append(item)

    fsm_data["lora_items"] = current_items
    await robust_edit_text(
        query.message,
        _build_lora_selection_message(context, current_items),
        reply_markup=_build_ltx_lora_selection_keyboard(context, current_items),
        parse_mode="Markdown",
    )
    return LtxVideoState.WAIT_LORA_SELECTION


async def process_initial_setup(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer(text=_t(context, "fsm.common.task_initializing"), cache_time=2)
    fsm_data = context.user_data.get(LTX_VIDEO_DATA_KEY)
    if not fsm_data:
        with contextlib.suppress(Exception):
            await query.answer(_t(context, "fsm.ltx_video.expired_alert"), show_alert=True)
        return ConversationHandler.END

    data = query.data or ""
    if data == "ltx_mode_v2v_audio":
        fsm_data["ltx_mode"] = LTX_MODE_I2V
        with contextlib.suppress(Exception):
            await query.answer(LTX_V2V_AUDIO_DISABLED_MESSAGE, show_alert=True)
    elif data == "ltx_mode_flf2v":
        fsm_data["ltx_mode"] = LTX_MODE_FLF2V
    elif data == "ltx_mode_i2v":
        fsm_data["ltx_mode"] = LTX_MODE_I2V
    elif data.startswith("set_ltxres_"):
        fsm_data["resolution"] = data.split("_")[2]
    elif data.startswith("set_ltxdur_"):
        fsm_data["duration"] = data.split("_")[2]
    elif data == LTX_SETUP_CONFIRM_CALLBACK:
        return await _confirm_initial_setup(update, context)
    else:
        return LtxVideoState.WAIT_MODE_SELECTION

    await robust_edit_text(
        query.message,
        _build_initial_setup_message(context, fsm_data),
        reply_markup=_build_initial_setup_keyboard(context, fsm_data),
        parse_mode="Markdown",
    )
    return LtxVideoState.WAIT_MODE_SELECTION


async def _confirm_initial_setup(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    fsm_data = context.user_data.get(LTX_VIDEO_DATA_KEY)
    if not fsm_data:
        with contextlib.suppress(Exception):
            await query.answer(_t(context, "fsm.ltx_video.expired_alert"), show_alert=True)
        return ConversationHandler.END

    ltx_mode = str(fsm_data.get("ltx_mode") or LTX_MODE_I2V)
    if ltx_mode == LTX_MODE_V2V_AUDIO:
        fsm_data["ltx_mode"] = LTX_MODE_I2V
        with contextlib.suppress(Exception):
            await query.answer(LTX_V2V_AUDIO_DISABLED_MESSAGE, show_alert=True)
        await robust_edit_text(
            query.message,
            _build_initial_setup_message(context, fsm_data),
            reply_markup=_build_initial_setup_keyboard(context, fsm_data),
            parse_mode="Markdown",
        )
        return LtxVideoState.WAIT_MODE_SELECTION

    if ltx_mode == LTX_MODE_FLF2V:
        await robust_edit_text(
            query.message,
            f"{_build_lora_summary_text(context, _get_ltx_video_items(fsm_data), empty_key='fsm.image_to_video.current_lora')}\n\n设置已确认。请先上传起始帧图片。",
            parse_mode="Markdown",
        )
        return LtxVideoState.WAIT_IMAGE

    await robust_edit_text(
        query.message,
        f"{_build_image_request_text(context, lora_items=_get_ltx_video_items(fsm_data))}\n\n设置已确认。",
        parse_mode="Markdown",
    )
    return LtxVideoState.WAIT_IMAGE


async def handle_mode_selection(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    return await process_initial_setup(update, context)


async def receive_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message
    fsm_data = context.user_data[LTX_VIDEO_DATA_KEY]
    file_id, suffix = _extract_image_file(update)
    if not file_id:
        await robust_reply_text(message, _t(context, "fsm.common.invalid_image"))
        return LtxVideoState.WAIT_IMAGE

    try:
        new_file = await context.bot.get_file(file_id)
        local_path = await download_telegram_file_to_fsm_temp(
            telegram_file=new_file,
            suffix=suffix,
            name_hint="ltx_video",
        )
        fsm_data["image_path"] = local_path
    except Exception as e:
        logger.error(
            "Error downloading image for FSM user %s: %s",
            update.effective_user.id if update.effective_user else "Unknown",
            e,
        )
        await robust_reply_text(message, _t(context, "fsm.common.download_image_failed"))
        return LtxVideoState.WAIT_IMAGE

    if fsm_data.get("ltx_mode") == LTX_MODE_FLF2V:
        await robust_reply_text(
            message,
            "起始帧已收到。请继续上传终止帧图片。",
            parse_mode="Markdown",
        )
        return LtxVideoState.WAIT_END_IMAGE

    return await _send_prompt_request_message(update, context, message=message)


async def receive_end_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message
    fsm_data = context.user_data[LTX_VIDEO_DATA_KEY]
    file_id, suffix = _extract_image_file(update)
    if not file_id:
        await robust_reply_text(message, _t(context, "fsm.common.invalid_image"))
        return LtxVideoState.WAIT_END_IMAGE

    try:
        new_file = await context.bot.get_file(file_id)
        local_path = await download_telegram_file_to_fsm_temp(
            telegram_file=new_file,
            suffix=suffix,
            name_hint="ltx_video_end",
        )
        fsm_data["end_image_path"] = local_path
    except Exception as e:
        logger.error(
            "Error downloading end image for LTX FSM user %s: %s",
            update.effective_user.id if update.effective_user else "Unknown",
            e,
        )
        await robust_reply_text(message, _t(context, "fsm.common.download_image_failed"))
        return LtxVideoState.WAIT_END_IMAGE

    return await _send_prompt_request_message(update, context, message=message)


async def receive_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message
    fsm_data = context.user_data[LTX_VIDEO_DATA_KEY]
    file_id, suffix, file_size, is_document = _extract_video_file(update)
    if not file_id:
        if is_document:
            await robust_reply_text(message, _t(context, "fsm.common.invalid_video_file"))
        else:
            await robust_reply_text(message, _t(context, "fsm.common.invalid_video"))
        return LtxVideoState.WAIT_VIDEO

    if _is_video_too_large(file_size):
        await robust_reply_text(message, f"视频过大，请上传 {LTX_MAX_INPUT_VIDEO_MB}MB 内的视频。")
        return LtxVideoState.WAIT_VIDEO

    try:
        new_file = await context.bot.get_file(file_id)
        if _is_video_too_large(getattr(new_file, "file_size", None)):
            await robust_reply_text(message, f"视频过大，请上传 {LTX_MAX_INPUT_VIDEO_MB}MB 内的视频。")
            return LtxVideoState.WAIT_VIDEO

        local_path = await download_telegram_file_to_fsm_temp(
            telegram_file=new_file,
            suffix=suffix,
            name_hint="ltx_video_audio_input",
        )
        if _is_video_too_large(os.path.getsize(local_path)):
            cleanup_fsm_temp_files([local_path])
            await robust_reply_text(message, f"视频过大，请上传 {LTX_MAX_INPUT_VIDEO_MB}MB 内的视频。")
            return LtxVideoState.WAIT_VIDEO
        fsm_data["video_path"] = local_path
    except Exception as e:
        logger.error(
            "Error downloading input video for LTX FSM user %s: %s",
            update.effective_user.id if update.effective_user else "Unknown",
            e,
        )
        await robust_reply_text(message, _t(context, "fsm.common.download_video_failed"))
        return LtxVideoState.WAIT_VIDEO

    return await _send_prompt_request_message(update, context, message=message)


async def process_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle settings change via inline keyboard"""
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data

    fsm_data = context.user_data.get(LTX_VIDEO_DATA_KEY, {})
    if not fsm_data:
        with contextlib.suppress(Exception):
            await query.answer(_t(context, "fsm.ltx_video.expired_alert"), show_alert=True)
        return ConversationHandler.END

    if data.startswith("set_ltxres_"):
        fsm_data["resolution"] = data.split("_")[2]
    elif data.startswith("set_ltxdur_"):
        fsm_data["duration"] = data.split("_")[2]

    res = fsm_data["resolution"]
    dur = fsm_data["duration"]

    from src.core.user_core import get_or_create_user_by_telegram

    internal_user, _ = await get_or_create_user_by_telegram(user_id)
    internal_user_id = internal_user.id

    user_group = await permission_service.get_user_group(internal_user_id)
    user_identity = await permission_service.get_user_identity(internal_user_id)
    reply_markup = get_ltx_video_settings_keyboard(
        user_group, user_identity, res, dur, getattr(context, "lang", "zh")
    )

    base_cost = LTX_RESOLUTION_COST.get(res, 10)
    multiplier = LTX_DURATION_MULTIPLIER.get(dur, 1.0)
    cost = int(base_cost * multiplier)

    msg_text = _build_settings_message(
        context,
        resolution=res,
        duration=dur,
        cost=cost,
        lora_items=_get_ltx_video_items(fsm_data),
        english_prompt_only=True,
    )

    with contextlib.suppress(Exception):
        await robust_edit_text(
            query.message, msg_text, reply_markup=reply_markup, parse_mode="Markdown"
        )

    await query.answer(text=_t(context, "fsm.common.task_initializing"), cache_time=2)
    return LtxVideoState.WAIT_SETTINGS_AND_PROMPT


async def receive_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message
    prompt = message.text.strip()

    if is_global_menu_command(prompt):
        return await unexpected_input(update, context)

    fsm_data = context.user_data.get(LTX_VIDEO_DATA_KEY)
    if not fsm_data:
        await robust_reply_text(message, _t(context, "fsm.common.already_submitted"))
        return ConversationHandler.END

    fsm_data["prompt"] = prompt

    reply_markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton(_t(context, "fsm.ltx_video.confirm_button"), callback_data="confirm_ltx_video")]]
    )
    msg_text = _t(context, "fsm.ltx_video.confirm_text", prompt=prompt)

    await robust_reply_text(
        message, msg_text, reply_markup=reply_markup, parse_mode="Markdown"
    )
    return LtxVideoState.WAIT_CONFIRMATION


async def confirm_generation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        from src.utils import safe_answer_query

        await safe_answer_query(query, text=_t(context, "fsm.common.task_initializing"), cache_time=2)
    user_id = query.from_user.id

    fsm_data = context.user_data.get(LTX_VIDEO_DATA_KEY)
    if not fsm_data:
        with contextlib.suppress(Exception):
            await query.answer(_t(context, "fsm.common.already_submitted"), show_alert=True)
        return ConversationHandler.END

    res = fsm_data["resolution"]
    dur = fsm_data["duration"]
    ltx_mode = str(fsm_data.get("ltx_mode") or LTX_MODE_I2V)
    if ltx_mode == LTX_MODE_V2V_AUDIO:
        logger.info("user=%s tried disabled LTX video audio mode from bot", user_id)
        with contextlib.suppress(Exception):
            await query.answer(LTX_V2V_AUDIO_DISABLED_MESSAGE, show_alert=True)
        with contextlib.suppress(Exception):
            await robust_edit_text(query.message, LTX_V2V_AUDIO_DISABLED_MESSAGE)
        _cleanup_context(context)
        return ConversationHandler.END

    prompt = fsm_data.get("prompt", "")
    lora_items = _get_ltx_video_items(fsm_data)
    if not lora_items:
        fallback_lora_name = str(fsm_data.get("lora_name") or "")
        if fallback_lora_name:
            fallback_item = build_ltx_video_lora_item(
                fallback_lora_name,
                strength=fsm_data.get("lora_strength"),
            )
            lora_items = [fallback_item] if fallback_item else []
    first_lora_item = lora_items[0] if lora_items else None
    lora_name = str(first_lora_item["name"]) if first_lora_item else ""
    lora_strength = float(first_lora_item["strength"]) if first_lora_item else None

    base_cost = LTX_RESOLUTION_COST.get(res, 10)
    multiplier = LTX_DURATION_MULTIPLIER.get(dur, 1.0)
    cost = int(base_cost * multiplier)

    image_path = fsm_data.get("image_path")
    end_image_path = fsm_data.get("end_image_path")
    video_path = fsm_data.get("video_path")
    ltx_prev_task_id = str(fsm_data.get("extension_prev_task_id") or "").strip()
    ltx_chain_task_ids = normalize_ltx_video_chain_task_ids(
        fsm_data.get("chain_task_ids")
    )
    if ltx_prev_task_id and not ltx_chain_task_ids:
        ltx_chain_task_ids = build_ltx_full_chain_task_ids(
            chain_task_ids=[],
            current_task_id=ltx_prev_task_id,
        )
    missing_input = (
        (ltx_mode == LTX_MODE_V2V_AUDIO and not video_path)
        or (ltx_mode == LTX_MODE_FLF2V and (not image_path or not end_image_path))
        or (ltx_mode == LTX_MODE_I2V and not image_path)
    )
    if missing_input:
        logger.warning("user=%s missing LTX input before submit mode=%s", user_id, ltx_mode)
        with contextlib.suppress(Exception):
            await query.answer(_t(context, "fsm.ltx_video.missing_image_resend"), show_alert=True)
        _cleanup_context(context)
        return ConversationHandler.END

    if not update.effective_user:
        return ConversationHandler.END
    user = update.effective_user
    try:
        await permission_service.check_quota(
            user.id, user.username, user.full_name, cost=cost
        )
    except Exception as e:
        from src.core.exceptions import InsufficientCreditsError

        if isinstance(e, InsufficientCreditsError):
            chat_id = update.effective_chat.id
            msg = _t(
                context,
                "fsm.common.insufficient_credits",
                current=e.current,
                cost=e.cost,
            )
            from src.utils import robust_send_message

            await robust_send_message(context.bot, chat_id, msg, parse_mode="Markdown")
            _cleanup_context(context)
            return ConversationHandler.END
        raise e

    image_path = fsm_data.pop("image_path", None)
    end_image_path = fsm_data.pop("end_image_path", None)
    video_path = fsm_data.pop("video_path", None)
    missing_input = (
        (ltx_mode == LTX_MODE_V2V_AUDIO and not video_path)
        or (ltx_mode == LTX_MODE_FLF2V and (not image_path or not end_image_path))
        or (ltx_mode == LTX_MODE_I2V and not image_path)
    )
    if missing_input:
        logger.warning(
            "user=%s LTX inputs consumed by another request before submit mode=%s",
            user_id,
            ltx_mode,
        )
        with contextlib.suppress(Exception):
            await query.answer(_t(context, "fsm.common.already_submitted"), show_alert=True)
        _cleanup_context(context)
        return ConversationHandler.END

    with contextlib.suppress(Exception):
        await robust_edit_text(
            query.message,
            _t(context, "fsm.ltx_video.submit", cost=cost),
        )

    context.user_data["ltx_video_resolution"] = res
    context.user_data["ltx_video_duration"] = dur
    context.user_data["ltx_video_mode"] = ltx_mode

    create_background_task(
        context,
        process_ltx_video_task(
            update=update,
            context=context,
            prompt=prompt,
            image_path=image_path,
            end_image_path=end_image_path,
            video_path=video_path,
            ltx_mode=ltx_mode,
            ltx_prev_task_id=ltx_prev_task_id or None,
            ltx_chain_task_ids=ltx_chain_task_ids or None,
            lora_name=lora_name,
            lora_strength=lora_strength,
            lora_items=lora_items or None,
            cleanup=True,
        ),
    )

    _cleanup_context(context)
    await query.answer(text=_t(context, "fsm.common.task_initializing"), cache_time=2)
    return ConversationHandler.END


async def start_ltx_video_extension(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    query = update.callback_query
    if query:
        with contextlib.suppress(Exception):
            await query.answer(text=_t(context, "fsm.common.task_initializing"), cache_time=2)

    if context.user_data.get("in_conversation"):
        target_message = query.message if query else update.effective_message
        if target_message:
            await robust_reply_text(target_message, _t(context, "fsm.common.conflict"))
        return ConversationHandler.END

    meta = (
        context.bot_data.get(f"msg_meta_{query.message.message_id}", {})
        if query and query.message
        else {}
    )
    base_task_id = _resolve_callback_task_id(
        meta=meta,
        query=query,
        callback_prefix=LTX_EXTEND_CALLBACK_PREFIX,
    )
    if not base_task_id:
        target_message = query.message if query else update.effective_message
        if target_message:
            await robust_reply_text(target_message, _t(context, "fsm.ltx_video.expired_alert"))
        return ConversationHandler.END

    try:
        history = await load_owned_ltx_history(
            task_id=base_task_id,
            telegram_user_id=update.effective_user.id,
            username=update.effective_user.username,
        )
        meta = _merge_history_context_into_meta(history, meta)
        start_image_path = await download_ltx_last_frame_to_fsm_temp(history=history)
    except LtxVideoExtensionError as exc:
        target_message = query.message if query else update.effective_message
        if target_message:
            await robust_reply_text(target_message, f"❌ {exc}")
        return ConversationHandler.END
    except Exception as exc:
        logger.error("prepare ltx_video extension failed: %s", exc)
        target_message = query.message if query else update.effective_message
        if target_message:
            await robust_reply_text(
                target_message,
                f"❌ {_t(context, 'fsm.common.download_image_failed')}",
            )
        return ConversationHandler.END

    context.user_data["in_conversation"] = LTX_VIDEO_CONVERSATION_TAG
    context.user_data[LTX_VIDEO_DATA_KEY] = {
        "resolution": _resolution_from_history(history),
        "duration": _duration_label_from_history(history),
        "ltx_mode": LTX_MODE_I2V,
        "image_path": start_image_path,
        "end_image_path": None,
        "video_path": None,
        "lora_items": _resolve_lora_items_from_meta(meta),
        "extension_prev_task_id": base_task_id,
        "chain_task_ids": build_ltx_full_chain_task_ids(
            chain_task_ids=normalize_ltx_video_chain_task_ids(
                meta.get("ltx_chain_task_ids")
            ),
            current_task_id=base_task_id,
        ),
    }
    target_message = query.message if query else update.effective_message
    if target_message:
        await robust_reply_text(
            target_message,
            "已载入上一段尾帧作为新的起始帧。你可以调整时长后输入下一段提示词。",
            parse_mode="Markdown",
        )
        return await _send_settings_message(update, context, message=target_message)
    _cleanup_context(context)
    return ConversationHandler.END


async def cancel_conversation(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    return await handle_standard_fsm_cancel(
        update,
        context,
        cleanup_func=lambda: _cleanup_context(context),
        translate_func=_t,
        reply_text_func=robust_reply_text,
    )


async def timeout_conversation(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    return await handle_standard_fsm_timeout(
        update,
        context,
        cleanup_func=lambda: _cleanup_context(context),
        translate_func=_t,
        reply_text_func=robust_reply_text,
    )


async def unexpected_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await handle_standard_fsm_unexpected_input(
        update,
        context,
        cleanup_func=lambda: _cleanup_context(context),
        translate_func=_t,
        reply_text_func=robust_reply_text,
    )


def get_ltx_video_fsm_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("ltx_video", start_ltx_video),
            MessageHandler(I18nFilter("menu.ltx_video"), start_ltx_video),
            CallbackQueryHandler(start_ltx_video, pattern="^fsm_start_ltx_video$"),
            CallbackQueryHandler(
                start_ltx_video_extension,
                pattern=rf"^{LTX_EXTEND_CALLBACK_PREFIX}(?::.+)?$",
            ),
        ],
        states={
            LtxVideoState.WAIT_LORA_SELECTION: [
                CallbackQueryHandler(
                    handle_lora_selection,
                    pattern="^(toggle_ltx_lora_|done_ltx_lora_select$|clear_ltx_lora_select$|skip_ltx_lora_select$)",
                ),
                MessageHandler(
                    (filters.TEXT | filters.COMMAND) & ~filters.Regex(r"^/cancel$"),
                    unexpected_input,
                ),
            ],
            LtxVideoState.WAIT_MODE_SELECTION: [
                CallbackQueryHandler(
                    process_initial_setup,
                    pattern=(
                        r"^(ltx_mode_(i2v|flf2v|v2v_audio)"
                        r"|set_ltx(res|dur)_"
                        rf"|{LTX_SETUP_CONFIRM_CALLBACK}$)"
                    ),
                ),
                MessageHandler(
                    (filters.TEXT | filters.COMMAND) & ~filters.Regex(r"^/cancel$"),
                    unexpected_input,
                ),
            ],
            LtxVideoState.WAIT_IMAGE: [
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, receive_image),
                MessageHandler(
                    (filters.TEXT | filters.COMMAND) & ~filters.Regex(r"^/cancel$"),
                    unexpected_input,
                ),
            ],
            LtxVideoState.WAIT_END_IMAGE: [
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, receive_end_image),
                MessageHandler(
                    (filters.TEXT | filters.COMMAND) & ~filters.Regex(r"^/cancel$"),
                    unexpected_input,
                ),
            ],
            LtxVideoState.WAIT_VIDEO: [
                MessageHandler(filters.VIDEO | filters.Document.ALL, receive_video),
                MessageHandler(
                    (filters.TEXT | filters.COMMAND) & ~filters.Regex(r"^/cancel$"),
                    unexpected_input,
                ),
            ],
            LtxVideoState.WAIT_SETTINGS_AND_PROMPT: [
                CallbackQueryHandler(process_settings, pattern="^set_ltx(res|dur)_"),
                MessageHandler(
                    (filters.TEXT | filters.COMMAND) & ~filters.Regex(r"^/cancel$"),
                    receive_prompt,
                ),
                MessageHandler(
                    filters.PHOTO | filters.VIDEO | filters.Document.ALL, unexpected_input
                ),
            ],
            LtxVideoState.WAIT_CONFIRMATION: [
                CallbackQueryHandler(confirm_generation, pattern="^confirm_ltx_video$"),
                MessageHandler(
                    (filters.TEXT | filters.COMMAND) & ~filters.Regex(r"^/cancel$"),
                    unexpected_input,
                ),
                MessageHandler(
                    filters.PHOTO | filters.VIDEO | filters.Document.ALL, unexpected_input
                ),
            ],
            ConversationHandler.TIMEOUT: [
                MessageHandler(filters.ALL, timeout_conversation)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
        conversation_timeout=300,
        name="ltx_video_fsm",
        persistent=False,
    )
