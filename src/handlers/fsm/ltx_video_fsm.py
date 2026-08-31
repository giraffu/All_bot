import logging
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
    MODE_LTX_VIDEO,
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
    prepare_ltx_extension_fsm_data,
)
from src.services.permission_service import permission_service
from src.services.advanced_video_submission_service import (
    AdvancedVideoSubmissionReject,
    build_ltx_video_submission_plan,
    create_ltx_video_submission_task,
)
from src.services.advanced_video_settings_view_service import (
    apply_ltx_video_settings_callback,
    build_ltx_initial_setup_view,
    build_ltx_lora_summary_text,
    build_ltx_prompt_settings_view,
)
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
LTX_SETUP_CONFIRM_CALLBACK = "ltx_setup_confirm"
_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


_t = translate_fsm_text


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
    return build_ltx_lora_summary_text(
        lora_items,
        lang=getattr(context, "lang", "zh"),
        translate_func=lambda key, **kwargs: _t(context, key, **kwargs),
        empty_key=empty_key,
    )


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
        }.get(mode, "Single start frame")
    return {
        LTX_MODE_FLF2V: "首尾帧",
    }.get(mode, "单首帧")


def _is_extension_flow(fsm_data: dict[str, Any]) -> bool:
    return bool(fsm_data.get("is_extension"))


def _build_initial_setup_keyboard(
    context: ContextTypes.DEFAULT_TYPE,
    fsm_data: dict[str, Any],
) -> InlineKeyboardMarkup:
    view = build_ltx_initial_setup_view(
        fsm_data,
        lang=getattr(context, "lang", "zh"),
        translate_func=lambda key, **kwargs: _t(context, key, **kwargs),
        lora_items=_get_ltx_video_items(fsm_data),
    )
    fsm_data["resolution"] = view.resolution
    fsm_data["duration"] = view.duration
    return view.reply_markup


def _build_initial_setup_message(
    context: ContextTypes.DEFAULT_TYPE,
    fsm_data: dict[str, Any],
) -> str:
    view = build_ltx_initial_setup_view(
        fsm_data,
        lang=getattr(context, "lang", "zh"),
        translate_func=lambda key, **kwargs: _t(context, key, **kwargs),
        lora_items=_get_ltx_video_items(fsm_data),
    )
    fsm_data["resolution"] = view.resolution
    fsm_data["duration"] = view.duration
    return view.message_text


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


def _cleanup_context(context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("in_conversation", None)
    pending_files = context.user_data.pop(LTX_VIDEO_DATA_KEY, {})
    cleanup_fsm_temp_files(
        [
            pending_files.get("image_path"),
            pending_files.get("end_image_path"),
        ]
    )


def _release_context_without_files(
    context: ContextTypes.DEFAULT_TYPE,
) -> dict[str, Any]:
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
            await query.answer(
                text=_t(context, "fsm.common.task_initializing"), cache_time=2
            )

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
            await query.answer(
                _t(context, "fsm.ltx_video.expired_alert"), show_alert=True
            )
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
        (
            index
            for index, item in enumerate(current_items)
            if str(item["name"]) == lora_name
        ),
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
            await query.answer(
                _t(context, "fsm.ltx_video.expired_alert"), show_alert=True
            )
        return ConversationHandler.END

    data = query.data or ""
    if data == "ltx_mode_flf2v":
        fsm_data["ltx_mode"] = LTX_MODE_FLF2V
    elif data == "ltx_mode_i2v":
        fsm_data["ltx_mode"] = LTX_MODE_I2V
    elif apply_ltx_video_settings_callback(fsm_data, callback_data=data):
        pass
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
            await query.answer(
                _t(context, "fsm.ltx_video.expired_alert"), show_alert=True
            )
        return ConversationHandler.END

    ltx_mode = str(fsm_data.get("ltx_mode") or LTX_MODE_I2V)
    if ltx_mode == LTX_MODE_FLF2V:
        if _is_extension_flow(fsm_data) and fsm_data.get("image_path"):
            await robust_edit_text(
                query.message,
                f"{_build_lora_summary_text(context, _get_ltx_video_items(fsm_data), empty_key='fsm.image_to_video.current_lora')}\n\n设置已确认。请上传本段终止帧图片。",
                parse_mode="Markdown",
            )
            return LtxVideoState.WAIT_END_IMAGE
        await robust_edit_text(
            query.message,
            f"{_build_lora_summary_text(context, _get_ltx_video_items(fsm_data), empty_key='fsm.image_to_video.current_lora')}\n\n设置已确认。请先上传起始帧图片。",
            parse_mode="Markdown",
        )
        return LtxVideoState.WAIT_IMAGE

    if _is_extension_flow(fsm_data) and fsm_data.get("image_path"):
        await robust_edit_text(
            query.message,
            _build_prompt_request_text(context, fsm_data),
            parse_mode="Markdown",
        )
        return LtxVideoState.WAIT_SETTINGS_AND_PROMPT

    await robust_edit_text(
        query.message,
        f"{_build_image_request_text(context, lora_items=_get_ltx_video_items(fsm_data))}\n\n设置已确认。",
        parse_mode="Markdown",
    )
    return LtxVideoState.WAIT_IMAGE


async def receive_initial_setup_image(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    fsm_data = context.user_data.get(LTX_VIDEO_DATA_KEY)
    if not fsm_data:
        await robust_reply_text(
            update.message,
            _t(context, "fsm.ltx_video.expired_alert"),
        )
        return ConversationHandler.END

    if _is_extension_flow(fsm_data) and fsm_data.get("image_path"):
        fsm_data["ltx_mode"] = LTX_MODE_FLF2V
        return await receive_end_image(update, context)

    return await receive_image(update, context)


async def receive_initial_setup_text(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int | None:
    text = (update.message.text or "").strip() if update.message else ""
    if is_global_menu_command(text):
        return await unexpected_input(update, context)

    fsm_data = context.user_data.get(LTX_VIDEO_DATA_KEY)
    if not fsm_data:
        await robust_reply_text(
            update.message,
            _t(context, "fsm.ltx_video.expired_alert"),
        )
        return ConversationHandler.END

    ltx_mode = str(fsm_data.get("ltx_mode") or LTX_MODE_I2V)
    if (
        _is_extension_flow(fsm_data)
        and fsm_data.get("image_path")
        and ltx_mode == LTX_MODE_I2V
    ):
        return await receive_prompt(update, context)

    return await unexpected_input(update, context)


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
        await robust_reply_text(
            message, _t(context, "fsm.common.download_image_failed")
        )
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
        await robust_reply_text(
            message, _t(context, "fsm.common.download_image_failed")
        )
        return LtxVideoState.WAIT_END_IMAGE

    return await _send_prompt_request_message(update, context, message=message)


async def process_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle settings change via inline keyboard"""
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data

    fsm_data = context.user_data.get(LTX_VIDEO_DATA_KEY, {})
    if not fsm_data:
        with contextlib.suppress(Exception):
            await query.answer(
                _t(context, "fsm.ltx_video.expired_alert"), show_alert=True
            )
        return ConversationHandler.END

    apply_ltx_video_settings_callback(fsm_data, callback_data=data)

    from src.core.user_core import get_or_create_user_by_telegram

    internal_user, _ = await get_or_create_user_by_telegram(user_id)
    internal_user_id = internal_user.id

    user_group = await permission_service.get_user_group(internal_user_id)
    user_identity = await permission_service.get_user_identity(internal_user_id)
    view = build_ltx_prompt_settings_view(
        fsm_data,
        lang=getattr(context, "lang", "zh"),
        translate_func=lambda key, **kwargs: _t(context, key, **kwargs),
        user_group=user_group,
        user_identity=user_identity,
        lora_items=_get_ltx_video_items(fsm_data),
    )
    fsm_data["resolution"] = view.resolution
    fsm_data["duration"] = view.duration

    with contextlib.suppress(Exception):
        await robust_edit_text(
            query.message,
            view.message_text,
            reply_markup=view.reply_markup,
            parse_mode="Markdown",
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
        [
            [
                InlineKeyboardButton(
                    _t(context, "fsm.ltx_video.confirm_button"),
                    callback_data="confirm_ltx_video",
                )
            ]
        ]
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

        await safe_answer_query(
            query, text=_t(context, "fsm.common.task_initializing"), cache_time=2
        )
    user_id = query.from_user.id

    fsm_data = context.user_data.get(LTX_VIDEO_DATA_KEY)
    if not fsm_data:
        with contextlib.suppress(Exception):
            await query.answer(
                _t(context, "fsm.common.already_submitted"), show_alert=True
            )
        return ConversationHandler.END

    submission_plan = build_ltx_video_submission_plan(
        fsm_data=fsm_data,
        max_loras=MAX_LTX_VIDEO_LORAS,
    )
    if isinstance(submission_plan, AdvancedVideoSubmissionReject):
        logger.warning("user=%s missing LTX input before submit", user_id)
        with contextlib.suppress(Exception):
            await query.answer(
                _t(context, "fsm.ltx_video.missing_image_resend"), show_alert=True
            )
        _cleanup_context(context)
        return ConversationHandler.END
    cost = submission_plan.cost

    if not update.effective_user:
        return ConversationHandler.END
    user = update.effective_user
    try:
        await permission_service.check_quota(
            user.id,
            user.username,
            user.full_name,
            cost=cost,
            task_type=MODE_LTX_VIDEO,
            client_type=(getattr(context, "bot_data", None) or {}).get(
                "bot_client_type", "bot"
            ),
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
    consumed_plan = build_ltx_video_submission_plan(
        fsm_data={
            **fsm_data,
            "image_path": image_path,
            "end_image_path": end_image_path,
        },
        max_loras=MAX_LTX_VIDEO_LORAS,
    )
    if isinstance(consumed_plan, AdvancedVideoSubmissionReject):
        logger.warning(
            "user=%s LTX inputs consumed by another request before submit",
            user_id,
        )
        with contextlib.suppress(Exception):
            await query.answer(
                _t(context, "fsm.common.already_submitted"), show_alert=True
            )
        _cleanup_context(context)
        return ConversationHandler.END

    with contextlib.suppress(Exception):
        await robust_edit_text(
            query.message,
            _t(context, "fsm.ltx_video.submit", cost=cost),
        )

    create_background_task(
        context,
        create_ltx_video_submission_task(
            plan=consumed_plan,
            update=update,
            context=context,
            process_ltx_video_task_func=process_ltx_video_task,
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
            await query.answer(
                text=_t(context, "fsm.common.task_initializing"), cache_time=2
            )

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
            await robust_reply_text(
                target_message, _t(context, "fsm.ltx_video.expired_alert")
            )
        return ConversationHandler.END

    try:
        seed = await prepare_ltx_extension_fsm_data(
            base_task_id=base_task_id,
            telegram_user_id=update.effective_user.id,
            username=update.effective_user.username,
            meta=meta,
            max_loras=MAX_LTX_VIDEO_LORAS,
        )
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
    context.user_data[LTX_VIDEO_DATA_KEY] = seed.fsm_data
    target_message = query.message if query else update.effective_message
    if target_message:
        fsm_data = context.user_data[LTX_VIDEO_DATA_KEY]
        await robust_reply_text(
            target_message,
            _build_initial_setup_message(context, fsm_data),
            reply_markup=_build_initial_setup_keyboard(context, fsm_data),
            parse_mode="Markdown",
        )
        return LtxVideoState.WAIT_MODE_SELECTION
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
                        r"^(ltx_mode_(i2v|flf2v)"
                        r"|set_ltx(res|dur)_"
                        rf"|{LTX_SETUP_CONFIRM_CALLBACK}$)"
                    ),
                ),
                MessageHandler(
                    filters.PHOTO | filters.Document.IMAGE,
                    receive_initial_setup_image,
                ),
                MessageHandler(
                    (filters.TEXT | filters.COMMAND) & ~filters.Regex(r"^/cancel$"),
                    receive_initial_setup_text,
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
                MessageHandler(
                    filters.PHOTO | filters.Document.IMAGE, receive_end_image
                ),
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
                    filters.PHOTO | filters.VIDEO | filters.Document.ALL,
                    unexpected_input,
                ),
            ],
            LtxVideoState.WAIT_CONFIRMATION: [
                CallbackQueryHandler(confirm_generation, pattern="^confirm_ltx_video$"),
                MessageHandler(
                    (filters.TEXT | filters.COMMAND) & ~filters.Regex(r"^/cancel$"),
                    unexpected_input,
                ),
                MessageHandler(
                    filters.PHOTO | filters.VIDEO | filters.Document.ALL,
                    unexpected_input,
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
