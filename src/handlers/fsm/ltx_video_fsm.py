import logging
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
from src.handlers.conversation_states import LtxVideoState
from src.handlers.prompt_router import GLOBAL_REVERSE_MAP, is_global_menu_command
from src.lora_catalog import (
    LTX_VIDEO_LORA_OPTIONS,
    build_ltx_video_lora_item,
    get_ltx_video_lora_display_name,
    normalize_ltx_video_lora_items,
    resolve_ltx_video_lora_name,
)
from src.services.bot_task_service import process_ltx_video_task
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
from src.i18n.translator import get_text

logger = logging.getLogger("fsm.ltx_video")

MAX_LTX_VIDEO_LORAS = 3


def _t(context: ContextTypes.DEFAULT_TYPE, key: str, **kwargs) -> str:
    translator = getattr(context, "t", None)
    if callable(translator):
        return translator(key, **kwargs)
    lang = getattr(context, "lang", None)
    if not lang and getattr(context, "user_data", None):
        lang = context.user_data.get("language_code")
    return get_text(key, lang or "zh", **kwargs)


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


def _build_image_request_text(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    lora_items: list[dict[str, Any]],
) -> str:
    return (
        f"{_build_lora_summary_text(context, lora_items, empty_key='fsm.image_to_video.current_lora')}\n\n"
        f"{_t(context, 'fsm.ltx_video.start')}"
    )


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


def _cleanup_context(context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("in_conversation", None)
    pending_files = context.user_data.pop("ltx_video_data", {})
    cleanup_fsm_temp_files([pending_files.get("image_path")])


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

    context.user_data["in_conversation"] = "LTX_VIDEO"
    context.user_data["ltx_video_data"] = {
        "resolution": "1280x704",
        "duration": "5s",
        "image_path": None,
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
    fsm_data = context.user_data.get("ltx_video_data")
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
            _build_image_request_text(
                context,
                lora_items=_get_ltx_video_items(fsm_data),
            ),
            parse_mode="Markdown",
        )
        return LtxVideoState.WAIT_IMAGE

    if data == "done_ltx_lora_select" or data == "skip_ltx_lora_select":
        if data == "skip_ltx_lora_select":
            fsm_data["lora_items"] = []
        await robust_edit_text(
            query.message,
            _build_image_request_text(
                context,
                lora_items=_get_ltx_video_items(fsm_data),
            ),
            parse_mode="Markdown",
        )
        return LtxVideoState.WAIT_IMAGE

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


async def receive_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    message = update.message
    fsm_data = context.user_data["ltx_video_data"]

    if message.document:
        if not message.document.mime_type.startswith("image/"):
            await robust_reply_text(message, _t(context, "fsm.common.invalid_image"))
            return LtxVideoState.WAIT_IMAGE
        file_id = message.document.file_id
    elif message.photo:
        file_id = message.photo[-1].file_id
    else:
        await robust_reply_text(message, _t(context, "fsm.common.invalid_image"))
        return LtxVideoState.WAIT_IMAGE

    try:
        new_file = await context.bot.get_file(file_id)
        local_path = await download_telegram_file_to_fsm_temp(
            telegram_file=new_file,
            suffix=".png",
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

    # Send settings keyboard
    from src.core.user_core import get_or_create_user_by_telegram

    internal_user, _ = await get_or_create_user_by_telegram(user_id)
    internal_user_id = internal_user.id

    user_group = await permission_service.get_user_group(internal_user_id)
    user_identity = await permission_service.get_user_identity(internal_user_id)

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
    )

    await robust_reply_text(
        message, msg_text, reply_markup=reply_markup, parse_mode="Markdown"
    )
    return LtxVideoState.WAIT_SETTINGS_AND_PROMPT


async def process_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle settings change via inline keyboard"""
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data

    fsm_data = context.user_data.get("ltx_video_data", {})
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

    fsm_data = context.user_data.get("ltx_video_data")
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

    fsm_data = context.user_data.get("ltx_video_data")
    if not fsm_data:
        with contextlib.suppress(Exception):
            await query.answer(_t(context, "fsm.common.already_submitted"), show_alert=True)
        return ConversationHandler.END

    res = fsm_data["resolution"]
    dur = fsm_data["duration"]
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
    if not image_path:
        logger.warning(f"user={user_id} image_path missing before submit in ltx_video")
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
    if not image_path:
        logger.warning(
            f"user={user_id} image_path consumed by another request before submit in ltx_video"
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

    create_background_task(
        context,
        process_ltx_video_task(
            update=update,
            context=context,
            prompt=prompt,
            image_path=image_path,
            lora_name=lora_name,
            lora_strength=lora_strength,
            lora_items=lora_items or None,
            cleanup=True,
        ),
    )

    _cleanup_context(context)
    await query.answer(text=_t(context, "fsm.common.task_initializing"), cache_time=2)
    return ConversationHandler.END


async def cancel_conversation(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    msg = _t(context, "fsm.common.cancelled")
    await robust_reply_text(update.message, msg)
    _cleanup_context(context)
    return ConversationHandler.END


async def timeout_conversation(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if update and update.message:
        await robust_reply_text(
            update.message,
            _t(context, "fsm.common.timeout"),
        )
    _cleanup_context(context)
    return ConversationHandler.END


async def unexpected_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text if update.message else ""
    if text and is_global_menu_command(text):
        route_key = GLOBAL_REVERSE_MAP.get(text)
        _cleanup_context(context)
        if route_key == "menu.switch_lang" and update.effective_user:
            from src.handlers.message_handler_runtime import toggle_user_language

            reply_text, reply_markup = await toggle_user_language(
                context, update.effective_user
            )
            await robust_reply_text(
                update.message, reply_text, reply_markup=reply_markup
            )
            return ConversationHandler.END
        await robust_reply_text(update.message, _t(context, "system.fsm_exit_hint"))
        return ConversationHandler.END

    await robust_reply_text(update.message, _t(context, "system.fsm_in_progress_hint"))
    return None


def get_ltx_video_fsm_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("ltx_video", start_ltx_video),
            MessageHandler(I18nFilter("menu.ltx_video"), start_ltx_video),
            CallbackQueryHandler(start_ltx_video, pattern="^fsm_start_ltx_video$"),
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
            LtxVideoState.WAIT_IMAGE: [
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, receive_image),
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
                    filters.PHOTO | filters.Document.IMAGE, unexpected_input
                ),
            ],
            LtxVideoState.WAIT_CONFIRMATION: [
                CallbackQueryHandler(confirm_generation, pattern="^confirm_ltx_video$"),
                MessageHandler(
                    (filters.TEXT | filters.COMMAND) & ~filters.Regex(r"^/cancel$"),
                    unexpected_input,
                ),
                MessageHandler(
                    filters.PHOTO | filters.Document.IMAGE, unexpected_input
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
