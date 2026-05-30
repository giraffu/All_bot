import contextlib
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from src.constants import MODE_WAN22_VIDEO_V2
from src.filters.i18n_filter import I18nFilter
from src.handlers.conversation_states import Wan22VideoV2State
from src.handlers.fsm.fsm_shared import (
    handle_standard_fsm_cancel,
    handle_standard_fsm_timeout,
    handle_standard_fsm_unexpected_input,
    translate_fsm_text,
)
from src.handlers.prompt_router import is_global_menu_command
from src.services.task_service_generation_wan22 import (
    process_wan22_video_v2_generation_task as process_wan22_video_v2_task,
)
from src.services.wan22_video_v2_config import (
    WAN22_VIDEO_V2_DEFAULT_RESOLUTION_PRESET,
    WAN22_VIDEO_V2_RESOLUTION_PRESETS,
    get_wan22_video_v2_cost,
    get_wan22_video_v2_resolution_label,
)
from src.services.fsm_temp_file_service import (
    cleanup_fsm_temp_files,
    download_telegram_file_to_fsm_temp,
)
from src.services.permission_service import permission_service
from src.utils import create_background_task, robust_edit_text, robust_reply_text

logger = logging.getLogger("fsm.wan22_video_v2")

WAN22_VIDEO_V2_DATA_KEY = "wan22_video_v2_data"
WAN22_VIDEO_V2_CONVERSATION_TAG = "WAN22_VIDEO_V2"
_t = translate_fsm_text


def _default_negative_prompt_label(context: ContextTypes.DEFAULT_TYPE) -> str:
    lang = getattr(context, "lang", "zh")
    return "Default negative prompt" if lang == "en" else "默认负面提示词"


def _get_data(context: ContextTypes.DEFAULT_TYPE) -> dict | None:
    return context.user_data.get(WAN22_VIDEO_V2_DATA_KEY)


def _set_data(context: ContextTypes.DEFAULT_TYPE, data: dict[str, object]) -> None:
    context.user_data[WAN22_VIDEO_V2_DATA_KEY] = data


def _pop_data(context: ContextTypes.DEFAULT_TYPE) -> dict:
    return context.user_data.pop(WAN22_VIDEO_V2_DATA_KEY, {}) or {}


def _cleanup_context(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("in_conversation", None)
    data = _pop_data(context)
    cleanup_fsm_temp_files(
        [
            data.get("start_image_path"),
            data.get("end_image_path"),
        ]
    )


def _release_context_without_files(context: ContextTypes.DEFAULT_TYPE) -> dict:
    context.user_data.pop("in_conversation", None)
    return _pop_data(context)


def _build_end_frame_choice_keyboard(context: ContextTypes.DEFAULT_TYPE) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    _t(context, "fsm.wan22_video_v2.enable_end_frame"),
                    callback_data="wan22v2_end_frame_yes",
                ),
                InlineKeyboardButton(
                    _t(context, "fsm.wan22_video_v2.disable_end_frame"),
                    callback_data="wan22v2_end_frame_no",
                ),
            ]
        ]
    )


def _build_settings_keyboard(
    context: ContextTypes.DEFAULT_TYPE, data: dict[str, object]
) -> InlineKeyboardMarkup:
    current_resolution = str(
        data.get("resolution_preset") or WAN22_VIDEO_V2_DEFAULT_RESOLUTION_PRESET
    )
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    (
                        f"• {_t(context, 'fsm.wan22_video_v2.resolution_fast')}"
                        if current_resolution == "fast"
                        else _t(context, "fsm.wan22_video_v2.resolution_fast")
                    ),
                    callback_data="wan22v2_res_fast",
                ),
                InlineKeyboardButton(
                    (
                        f"• {_t(context, 'fsm.wan22_video_v2.resolution_standard')}"
                        if current_resolution == "standard"
                        else _t(context, "fsm.wan22_video_v2.resolution_standard")
                    ),
                    callback_data="wan22v2_res_standard",
                ),
                InlineKeyboardButton(
                    (
                        f"• {_t(context, 'fsm.wan22_video_v2.resolution_hd')}"
                        if current_resolution == "hd"
                        else _t(context, "fsm.wan22_video_v2.resolution_hd")
                    ),
                    callback_data="wan22v2_res_hd",
                ),
            ],
            [
                InlineKeyboardButton(
                    _t(context, "fsm.wan22_video_v2.submit_button"),
                    callback_data="wan22v2_submit",
                )
            ],
        ]
    )


def _build_skip_negative_prompt_keyboard(
    context: ContextTypes.DEFAULT_TYPE,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    _t(context, "fsm.wan22_video_v2.skip_negative_prompt"),
                    callback_data="wan22v2_skip_negative_prompt",
                )
            ]
        ]
    )


def _build_settings_message(
    context: ContextTypes.DEFAULT_TYPE, data: dict[str, object]
) -> str:
    lang = getattr(context, "lang", "zh")
    status_yes = _t(context, "fsm.wan22_video_v2.status_yes")
    status_no = _t(context, "fsm.wan22_video_v2.status_no")
    negative_prompt = str(data.get("negative_prompt") or "").strip()
    resolution_preset = str(
        data.get("resolution_preset") or WAN22_VIDEO_V2_DEFAULT_RESOLUTION_PRESET
    )
    resolution_label = get_wan22_video_v2_resolution_label(
        resolution_preset,
        lang=lang,
    )
    cost = get_wan22_video_v2_cost(resolution_preset)
    return _t(
        context,
        "fsm.wan22_video_v2.settings_text",
        use_end_frame=status_yes if data.get("use_end_frame") else status_no,
        end_frame_ready=(
            status_yes
            if (not data.get("use_end_frame") or data.get("end_image_path"))
            else status_no
        ),
        prompt=str(data.get("prompt") or "").strip() or "-",
        negative_prompt=negative_prompt or _default_negative_prompt_label(context),
        resolution_preset=resolution_label,
        duration="5s" if lang == "en" else "5 秒",
        cost=cost,
    )


async def _send_or_edit_message(
    update: Update,
    message_text: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    query = update.callback_query
    if query:
        await robust_edit_text(
            query.message,
            message_text,
            reply_markup=reply_markup,
            parse_mode="Markdown",
        )
        return

    if update.message:
        await robust_reply_text(
            update.message,
            message_text,
            reply_markup=reply_markup,
            parse_mode="Markdown",
        )


async def _ask_for_prompt(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    await _send_or_edit_message(update, _t(context, "fsm.wan22_video_v2.send_prompt"))
    return Wan22VideoV2State.WAIT_PROMPT


async def _show_settings(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    data = _get_data(context) or {}
    await _send_or_edit_message(
        update,
        _build_settings_message(context, data),
        reply_markup=_build_settings_keyboard(context, data),
    )
    return Wan22VideoV2State.WAIT_SETTINGS


def _extract_image_file_id(message) -> str | None:
    if message.document:
        mime_type = message.document.mime_type or ""
        if not mime_type.startswith("image/"):
            return None
        return message.document.file_id
    if message.photo:
        return message.photo[-1].file_id
    return None


async def _download_image_to_temp(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    file_id: str,
    name_hint: str,
) -> str:
    telegram_file = await context.bot.get_file(file_id)
    return await download_telegram_file_to_fsm_temp(
        telegram_file=telegram_file,
        suffix=".png",
        name_hint=name_hint,
    )


async def start_wan22_video_v2(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    if query:
        with contextlib.suppress(Exception):
            await query.answer(text=_t(context, "fsm.common.task_initializing"), cache_time=2)

    from src.utils import is_maintenance_mode

    if is_maintenance_mode():
        msg = _t(context, "fsm.common.maintenance")
        await _send_or_edit_message(update, msg)
        return ConversationHandler.END

    if context.user_data.get("in_conversation"):
        await _send_or_edit_message(update, _t(context, "fsm.common.conflict"))
        return ConversationHandler.END

    context.user_data["in_conversation"] = WAN22_VIDEO_V2_CONVERSATION_TAG
    _set_data(
        context,
        {
            "start_image_path": None,
            "end_image_path": None,
            "use_end_frame": False,
            "resolution_preset": WAN22_VIDEO_V2_DEFAULT_RESOLUTION_PRESET,
            "prompt": "",
            "negative_prompt": "",
        },
    )
    await _send_or_edit_message(update, _t(context, "fsm.wan22_video_v2.start"))
    return Wan22VideoV2State.WAIT_START_IMAGE


async def receive_start_image(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    message = update.message
    data = _get_data(context)
    if not data:
        await robust_reply_text(message, _t(context, "fsm.common.expired_cleaned"))
        return ConversationHandler.END

    file_id = _extract_image_file_id(message)
    if not file_id:
        await robust_reply_text(message, _t(context, "fsm.common.invalid_image"))
        return Wan22VideoV2State.WAIT_START_IMAGE

    try:
        data["start_image_path"] = await _download_image_to_temp(
            context,
            file_id=file_id,
            name_hint="wan22_video_v2_start",
        )
    except Exception as exc:
        logger.error("download start image failed for wan22_video_v2: %s", exc)
        await robust_reply_text(message, _t(context, "fsm.common.download_image_failed"))
        return Wan22VideoV2State.WAIT_START_IMAGE

    await robust_reply_text(
        message,
        _t(context, "fsm.wan22_video_v2.end_frame_choice"),
        reply_markup=_build_end_frame_choice_keyboard(context),
        parse_mode="Markdown",
    )
    return Wan22VideoV2State.WAIT_END_FRAME_CHOICE


async def choose_end_frame_mode(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer(text=_t(context, "fsm.common.task_initializing"), cache_time=2)
    data = _get_data(context)
    if not data:
        with contextlib.suppress(Exception):
            await query.answer(_t(context, "fsm.wan22_video_v2.expired_alert"), show_alert=True)
        return ConversationHandler.END

    use_end_frame = query.data == "wan22v2_end_frame_yes"
    data["use_end_frame"] = use_end_frame
    data["end_image_path"] = None

    if use_end_frame:
        await robust_edit_text(
            query.message,
            _t(context, "fsm.wan22_video_v2.send_end_image"),
            parse_mode="Markdown",
        )
        return Wan22VideoV2State.WAIT_END_IMAGE

    await robust_edit_text(
        query.message,
        _t(context, "fsm.wan22_video_v2.single_frame_confirmed"),
        parse_mode="Markdown",
    )
    return await _ask_for_prompt(update, context)


async def receive_end_image(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    message = update.message
    data = _get_data(context)
    if not data:
        await robust_reply_text(message, _t(context, "fsm.common.expired_cleaned"))
        return ConversationHandler.END

    file_id = _extract_image_file_id(message)
    if not file_id:
        await robust_reply_text(message, _t(context, "fsm.common.invalid_image"))
        return Wan22VideoV2State.WAIT_END_IMAGE

    try:
        data["end_image_path"] = await _download_image_to_temp(
            context,
            file_id=file_id,
            name_hint="wan22_video_v2_end",
        )
    except Exception as exc:
        logger.error("download end image failed for wan22_video_v2: %s", exc)
        await robust_reply_text(message, _t(context, "fsm.common.download_image_failed"))
        return Wan22VideoV2State.WAIT_END_IMAGE

    await robust_reply_text(message, _t(context, "fsm.wan22_video_v2.end_image_received"))
    return await _ask_for_prompt(update, context)


async def receive_prompt(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    message = update.message
    prompt = (message.text or "").strip()
    if is_global_menu_command(prompt):
        return await unexpected_input(update, context)

    data = _get_data(context)
    if not data:
        await robust_reply_text(message, _t(context, "fsm.common.already_submitted"))
        return ConversationHandler.END

    data["prompt"] = prompt
    await robust_reply_text(
        message,
        _t(context, "fsm.wan22_video_v2.send_negative_prompt"),
        reply_markup=_build_skip_negative_prompt_keyboard(context),
        parse_mode="Markdown",
    )
    return Wan22VideoV2State.WAIT_NEGATIVE_PROMPT


async def receive_negative_prompt(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    message = update.message
    negative_prompt = (message.text or "").strip()
    if is_global_menu_command(negative_prompt):
        return await unexpected_input(update, context)

    data = _get_data(context)
    if not data:
        await robust_reply_text(message, _t(context, "fsm.common.already_submitted"))
        return ConversationHandler.END

    data["negative_prompt"] = negative_prompt
    return await _show_settings(update, context)


async def skip_negative_prompt(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer(text=_t(context, "fsm.common.task_initializing"), cache_time=2)
    data = _get_data(context)
    if not data:
        with contextlib.suppress(Exception):
            await query.answer(_t(context, "fsm.wan22_video_v2.expired_alert"), show_alert=True)
        return ConversationHandler.END

    data["negative_prompt"] = ""
    return await _show_settings(update, context)


async def handle_settings_action(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer(text=_t(context, "fsm.common.task_initializing"), cache_time=2)
    data = _get_data(context)
    if not data:
        with contextlib.suppress(Exception):
            await query.answer(_t(context, "fsm.wan22_video_v2.expired_alert"), show_alert=True)
        return ConversationHandler.END

    callback_data = query.data or ""
    if callback_data.startswith("wan22v2_res_"):
        selected_preset = callback_data.removeprefix("wan22v2_res_")
        if selected_preset in WAN22_VIDEO_V2_RESOLUTION_PRESETS:
            data["resolution_preset"] = selected_preset

    if callback_data == "wan22v2_submit":
        return await submit_generation(update, context)

    await robust_edit_text(
        query.message,
        _build_settings_message(context, data),
        reply_markup=_build_settings_keyboard(context, data),
        parse_mode="Markdown",
    )
    return Wan22VideoV2State.WAIT_SETTINGS


async def submit_generation(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    user = update.effective_user
    data = _get_data(context)
    if not data or not user:
        if query:
            with contextlib.suppress(Exception):
                await query.answer(_t(context, "fsm.wan22_video_v2.expired_alert"), show_alert=True)
        return ConversationHandler.END

    start_image_path = data.get("start_image_path")
    if not start_image_path:
        if query:
            with contextlib.suppress(Exception):
                await query.answer(_t(context, "fsm.common.missing_image_resend"), show_alert=True)
        _cleanup_context(context)
        return ConversationHandler.END

    if data.get("use_end_frame") and not data.get("end_image_path"):
        if query:
            with contextlib.suppress(Exception):
                await query.answer(_t(context, "fsm.wan22_video_v2.missing_end_image"), show_alert=True)
        return Wan22VideoV2State.WAIT_SETTINGS

    resolution_preset = str(
        data.get("resolution_preset") or WAN22_VIDEO_V2_DEFAULT_RESOLUTION_PRESET
    )
    cost = get_wan22_video_v2_cost(resolution_preset)

    try:
        await permission_service.check_quota(
            user.id,
            user.username,
            user.full_name,
            cost=cost,
        )
    except Exception as exc:
        from src.core.exceptions import InsufficientCreditsError
        from src.utils import robust_send_message

        if isinstance(exc, InsufficientCreditsError):
            await robust_send_message(
                context.bot,
                update.effective_chat.id,
                _t(
                    context,
                    "fsm.common.insufficient_credits",
                    current=exc.current,
                    cost=exc.cost,
                ),
                parse_mode="Markdown",
            )
            _cleanup_context(context)
            return ConversationHandler.END
        raise exc

    images = [start_image_path]
    if data.get("use_end_frame") and data.get("end_image_path"):
        images.append(str(data["end_image_path"]))

    if query:
        with contextlib.suppress(Exception):
            await robust_edit_text(
                query.message,
                _t(context, "fsm.wan22_video_v2.submitting", cost=cost),
                parse_mode="Markdown",
            )

    create_background_task(
        context,
        process_wan22_video_v2_task(
            context=context,
            chat_id=update.effective_chat.id,
            user_id=user.id,
            username=user.username,
            prompt=str(data.get("prompt") or "").strip(),
            negative_prompt=str(data.get("negative_prompt") or "").strip(),
            images=images,
            use_end_frame=bool(data.get("use_end_frame")),
            resolution_preset=resolution_preset,
            cleanup=True,
        ),
    )
    _release_context_without_files(context)
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


def get_wan22_video_v2_fsm_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("wan22_video_v2", start_wan22_video_v2),
            MessageHandler(I18nFilter("menu.wan22_video_v2"), start_wan22_video_v2),
            CallbackQueryHandler(
                start_wan22_video_v2, pattern="^fsm_start_wan22_video_v2$"
            ),
        ],
        states={
            Wan22VideoV2State.WAIT_START_IMAGE: [
                MessageHandler(
                    filters.PHOTO | filters.Document.IMAGE, receive_start_image
                ),
                MessageHandler(
                    (filters.TEXT | filters.COMMAND) & ~filters.Regex(r"^/cancel$"),
                    unexpected_input,
                ),
            ],
            Wan22VideoV2State.WAIT_END_FRAME_CHOICE: [
                CallbackQueryHandler(
                    choose_end_frame_mode,
                    pattern="^wan22v2_end_frame_(yes|no)$",
                ),
                MessageHandler(
                    (filters.TEXT | filters.COMMAND) & ~filters.Regex(r"^/cancel$"),
                    unexpected_input,
                ),
            ],
            Wan22VideoV2State.WAIT_END_IMAGE: [
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, receive_end_image),
                MessageHandler(
                    (filters.TEXT | filters.COMMAND) & ~filters.Regex(r"^/cancel$"),
                    unexpected_input,
                ),
            ],
            Wan22VideoV2State.WAIT_PROMPT: [
                MessageHandler(
                    (filters.TEXT | filters.COMMAND) & ~filters.Regex(r"^/cancel$"),
                    receive_prompt,
                ),
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, unexpected_input),
            ],
            Wan22VideoV2State.WAIT_NEGATIVE_PROMPT: [
                CallbackQueryHandler(
                    skip_negative_prompt, pattern="^wan22v2_skip_negative_prompt$"
                ),
                MessageHandler(
                    (filters.TEXT | filters.COMMAND) & ~filters.Regex(r"^/cancel$"),
                    receive_negative_prompt,
                ),
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, unexpected_input),
            ],
            Wan22VideoV2State.WAIT_SETTINGS: [
                CallbackQueryHandler(
                    handle_settings_action,
                    pattern=r"^wan22v2_(submit|res_(fast|standard|hd))$",
                ),
                MessageHandler(
                    (filters.TEXT | filters.COMMAND) & ~filters.Regex(r"^/cancel$"),
                    unexpected_input,
                ),
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, unexpected_input),
            ],
            ConversationHandler.TIMEOUT: [
                MessageHandler(filters.ALL, timeout_conversation)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
        conversation_timeout=300,
        name="wan22_video_v2_fsm",
        persistent=False,
    )
