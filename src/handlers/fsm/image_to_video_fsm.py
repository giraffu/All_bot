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

from src.constants import (
    DEFAULT_DURATION,
    DEFAULT_RESOLUTION,
    DURATION_MULTIPLIER,
    MODE_CUSTOM_VIDEO,
    MODE_IMAGE_TO_VIDEO,
    RESOLUTION_COST,
    get_video_settings_keyboard,
)
from src.handlers.fsm.fsm_shared import (
    handle_standard_fsm_cancel,
    handle_standard_fsm_timeout,
    handle_standard_fsm_unexpected_input,
    translate_fsm_text,
)
from src.handlers.conversation_states import ImageToVideoState
from src.handlers.prompt_router import is_global_menu_command
from src.lora_catalog import VIDEO_LORA_MODELS, get_video_lora_display_name
from src.services.task_service_entrypoints_generation import process_image_to_video_task
from src.services.permission_service import permission_service
from src.services.fsm_temp_file_service import (
    cleanup_fsm_temp_files,
    download_telegram_file_to_fsm_temp,
)
from src.utils import create_background_task, robust_edit_text, robust_reply_text
import contextlib

from src.filters.i18n_filter import I18nFilter

logger = logging.getLogger("fsm.image_to_video")

IMAGE_TO_VIDEO_DATA_KEY = "image_to_video_data"
IMAGE_TO_VIDEO_CONVERSATION_TAG = "IMAGE_TO_VIDEO"


_t = translate_fsm_text


def _get_image_to_video_data(context: ContextTypes.DEFAULT_TYPE) -> dict | None:
    """Return unified image-to-video FSM state."""
    return context.user_data.get(IMAGE_TO_VIDEO_DATA_KEY)


def _set_image_to_video_data(
    context: ContextTypes.DEFAULT_TYPE, data: dict[str, object]
) -> None:
    context.user_data[IMAGE_TO_VIDEO_DATA_KEY] = data


def _pop_image_to_video_data(context: ContextTypes.DEFAULT_TYPE) -> dict:
    """Pop unified image-to-video FSM state."""
    return context.user_data.pop(IMAGE_TO_VIDEO_DATA_KEY, {}) or {}


def _cleanup_context(context: ContextTypes.DEFAULT_TYPE, _user_id: int):
    context.user_data.pop("in_conversation", None)
    pending_files = _pop_image_to_video_data(context)
    cleanup_fsm_temp_files([pending_files.get("image_path")])


def _get_lora_display_name(lora_name: str | None, *, lang: str = "zh") -> str:
    normalized_name = lora_name or ""
    return get_video_lora_display_name(normalized_name, lang)


def _build_lora_selection_keyboard(lang: str = "zh") -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(
            get_video_lora_display_name(backend_name, lang),
            callback_data=f"lora_select_{backend_name}",
        )
        for backend_name in VIDEO_LORA_MODELS.keys()
    ]
    keyboard = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    return InlineKeyboardMarkup(keyboard)


def _build_image_request_text(
    lora_name: str | None, *, from_compat_alias: bool, lang: str = "zh"
) -> str:
    lora_display_name = get_video_lora_display_name(lora_name or "", lang)
    from src.i18n.translator import get_text

    header = get_text("fsm.image_to_video.mode_header", lang)
    if from_compat_alias:
        header = get_text("fsm.image_to_video.compat_mode_header", lang)

    return (
        f"{header}\n\n"
        f"{get_text('fsm.image_to_video.current_lora', lang, model_name=lora_display_name)}\n\n"
        f"{get_text('fsm.image_to_video.send_image', lang)}\n"
        f"{get_text('fsm.image_to_video.image_note', lang)}\n\n"
        "随时可以发送 /cancel 退出流程。"
    )


def _build_settings_message(
    fsm_data: dict[str, object], cost: int, *, lang: str = "zh"
) -> str:
    resolution = fsm_data["resolution"]
    duration = fsm_data["duration"]
    lora_display_name = _get_lora_display_name(fsm_data.get("lora_name"), lang=lang)

    from src.i18n.translator import get_text

    return get_text(
        "fsm.image_to_video.settings_text",
        lang,
        resolution=resolution,
        duration=duration,
        cost=cost,
        model_name=lora_display_name,
    )


def _build_submit_message(lora_name: str | None, cost: int, *, lang: str = "zh") -> str:
    from src.i18n.translator import get_text

    key = "fsm.image_to_video.submit_plain" if not lora_name else "fsm.image_to_video.submit_lora"
    return get_text(key, lang, cost=cost)


def _compute_video_generation_cost(resolution: str, duration: str) -> int:
    base_cost = RESOLUTION_COST.get(resolution, 6)
    multiplier = DURATION_MULTIPLIER.get(duration, 1.0)
    return int(base_cost * multiplier)


def _resolve_image_to_video_task_type(context: ContextTypes.DEFAULT_TYPE) -> str:
    return (
        MODE_CUSTOM_VIDEO
        if context.user_data.get("in_conversation") == "CUSTOM_VIDEO"
        else MODE_IMAGE_TO_VIDEO
    )


async def _load_video_generation_access_profile(
    *,
    user_id: int,
) -> tuple[int, str, str]:
    from src.core.user_core import get_or_create_user_by_telegram

    internal_user, _ = await get_or_create_user_by_telegram(user_id)
    internal_user_id = internal_user.id
    user_group = await permission_service.get_user_group(internal_user_id)
    user_identity = await permission_service.get_user_identity(internal_user_id)
    return internal_user_id, user_group, user_identity


async def _build_video_settings_view_model(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    fsm_data: dict[str, object],
) -> tuple[InlineKeyboardMarkup, int, str]:
    _internal_user_id, user_group, user_identity = (
        await _load_video_generation_access_profile(user_id=user_id)
    )
    resolution = str(fsm_data["resolution"])
    duration = str(fsm_data["duration"])
    reply_markup = get_video_settings_keyboard(
        user_group, user_identity, resolution, duration, getattr(context, "lang", "zh")
    )
    cost = _compute_video_generation_cost(resolution, duration)
    msg_text = _build_settings_message(
        fsm_data, cost, lang=getattr(context, "lang", "zh")
    )
    return reply_markup, cost, msg_text


async def _send_start_message(
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


def _initialize_image_to_video_context(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    conversation_tag: str,
    preset_lora_name: str | None = None,
) -> None:
    context.user_data["in_conversation"] = conversation_tag
    data = {
        "resolution": DEFAULT_RESOLUTION,
        "duration": DEFAULT_DURATION,
        "image_path": None,
        "lora_name": preset_lora_name,
    }
    _set_image_to_video_data(context, data)


async def _start_image_to_video_flow(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    conversation_tag: str = IMAGE_TO_VIDEO_CONVERSATION_TAG,
    preset_lora_name: str | None = None,
    skip_lora_selection: bool = False,
) -> int:
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
        if update.message:
            await robust_reply_text(update.message, msg)
        elif update.callback_query:
            await robust_edit_text(update.callback_query.message, msg)
        return ConversationHandler.END

    _initialize_image_to_video_context(
        context,
        conversation_tag=conversation_tag,
        preset_lora_name=preset_lora_name,
    )

    if skip_lora_selection:
        await _send_start_message(
            update,
            _build_image_request_text(
                preset_lora_name,
                from_compat_alias=conversation_tag == "CUSTOM_VIDEO",
                lang=getattr(context, "lang", "zh"),
            ),
        )
        return ImageToVideoState.WAIT_IMAGE

    msg = _t(context, "fsm.image_to_video.select_lora")
    await _send_start_message(
        update,
        msg,
        reply_markup=_build_lora_selection_keyboard(getattr(context, "lang", "zh")),
    )
    return ImageToVideoState.WAIT_LORA_SELECTION


async def start_image_to_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Preferred entry point for the unified image-to-video flow."""
    return await _start_image_to_video_flow(
        update,
        context,
        conversation_tag=IMAGE_TO_VIDEO_CONVERSATION_TAG,
    )


async def start_custom_video(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Legacy /custom_video entry point backed by the unified image-to-video flow."""
    return await _start_image_to_video_flow(
        update,
        context,
        conversation_tag="CUSTOM_VIDEO",
        preset_lora_name="",
        skip_lora_selection=True,
    )


async def handle_lora_selection(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer(text=_t(context, "fsm.common.task_initializing"), cache_time=2)
    data = query.data

    if not data.startswith("lora_select_"):
        return ImageToVideoState.WAIT_LORA_SELECTION

    lora_name = data.replace("lora_select_", "")
    fsm_data = _get_image_to_video_data(context) or {}
    if not fsm_data:
        await query.edit_message_text(_t(context, "fsm.image_to_video.expired_alert"))
        return ConversationHandler.END

    fsm_data["lora_name"] = lora_name

    msg = _build_image_request_text(
        lora_name, from_compat_alias=False, lang=getattr(context, "lang", "zh")
    )
    await robust_edit_text(query.message, msg, parse_mode="Markdown")
    return ImageToVideoState.WAIT_IMAGE


async def receive_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    message = update.message
    fsm_data = _get_image_to_video_data(context)
    if not fsm_data:
        await robust_reply_text(
            message, _t(context, "fsm.common.expired_cleaned")
        )
        return ConversationHandler.END

    if message.document:
        if not message.document.mime_type.startswith("image/"):
            await robust_reply_text(message, _t(context, "fsm.common.invalid_image"))
            return ImageToVideoState.WAIT_IMAGE
        file_id = message.document.file_id
    elif message.photo:
        file_id = message.photo[-1].file_id
    else:
        await robust_reply_text(message, _t(context, "fsm.common.invalid_image"))
        return ImageToVideoState.WAIT_IMAGE

    try:
        new_file = await context.bot.get_file(file_id)
        local_path = await download_telegram_file_to_fsm_temp(
            telegram_file=new_file,
            suffix=".png",
            name_hint="image_to_video",
        )
        fsm_data["image_path"] = local_path
    except Exception as e:
        logger.error(f"Error downloading image for FSM user {user_id}: {e}")
        await robust_reply_text(message, _t(context, "fsm.common.download_image_failed"))
        return ImageToVideoState.WAIT_IMAGE

    reply_markup, _cost, msg_text = await _build_video_settings_view_model(
        context=context,
        user_id=user_id,
        fsm_data=fsm_data,
    )

    await robust_reply_text(
        message, msg_text, reply_markup=reply_markup, parse_mode="Markdown"
    )
    return ImageToVideoState.WAIT_SETTINGS_AND_PROMPT


async def process_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle settings change via inline keyboard"""
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data

    fsm_data = _get_image_to_video_data(context) or {}
    if not fsm_data:
        with contextlib.suppress(Exception):
            await query.answer(_t(context, "fsm.image_to_video.expired_alert"), show_alert=True)
        return ConversationHandler.END

    if data.startswith("set_res_"):
        new_res = data.split("_")[2]
        if new_res == "1024p" and fsm_data.get("duration") == "10s":
            fsm_data["duration"] = "8s"
            with contextlib.suppress(Exception):
                await query.answer(
                    _t(context, "fsm.image_to_video.res_dur_conflict"), show_alert=True
                )
        fsm_data["resolution"] = new_res
    elif data.startswith("set_dur_"):
        new_dur = data.split("_")[2]
        if new_dur == "10s" and fsm_data.get("resolution") == "1024p":
            fsm_data["resolution"] = "720p"
            with contextlib.suppress(Exception):
                await query.answer(
                    _t(context, "fsm.image_to_video.dur_res_conflict"), show_alert=True
                )
        fsm_data["duration"] = new_dur

    reply_markup, _cost, msg_text = await _build_video_settings_view_model(
        context=context,
        user_id=user_id,
        fsm_data=fsm_data,
    )

    with contextlib.suppress(Exception):
        await robust_edit_text(
            query.message, msg_text, reply_markup=reply_markup, parse_mode="Markdown"
        )

    await query.answer(text="⏳ 任务初始化中...", cache_time=2)
    return ImageToVideoState.WAIT_SETTINGS_AND_PROMPT


async def receive_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    message = update.message
    prompt = message.text.strip()

    if is_global_menu_command(prompt):
        return await unexpected_input(update, context)

    fsm_data = _get_image_to_video_data(context)
    if not fsm_data:
        await robust_reply_text(message, _t(context, "fsm.common.already_submitted"))
        return ConversationHandler.END

    res = fsm_data["resolution"]
    dur = fsm_data["duration"]
    lora_name = fsm_data["lora_name"]

    if res == "1024p" and dur == "10s":
        res = "720p"
        fsm_data["resolution"] = "720p"

    cost = _compute_video_generation_cost(res, dur)

    image_path = fsm_data.get("image_path")
    if not image_path:
        logger.warning(
            f"user={user_id} image_path missing before submit in image_to_video"
        )
        await robust_reply_text(message, _t(context, "fsm.common.missing_image_resend"))
        _cleanup_context(context, user_id)
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
                "fsm.common.insufficient_credits", current=e.current, cost=e.cost
            )
            from src.utils import robust_send_message

            await robust_send_message(context.bot, chat_id, msg, parse_mode="Markdown")
            _cleanup_context(context, user_id)
            return ConversationHandler.END
        raise e

    image_path = fsm_data.pop("image_path", None)
    if not image_path:
        logger.warning(
            f"user={user_id} image_path consumed by another request before submit in image_to_video"
        )
        await robust_reply_text(message, _t(context, "fsm.common.already_submitted"))
        _cleanup_context(context, user_id)
        return ConversationHandler.END

    await robust_reply_text(
        message, _build_submit_message(lora_name, cost, lang=getattr(context, "lang", "zh"))
    )

    task_type = _resolve_image_to_video_task_type(context)
    create_background_task(
        context,
        process_image_to_video_task(
            context=context,
            chat_id=message.chat_id,
            user_id=user_id,
            username=update.effective_user.username,
            prompt=prompt,
            images=[image_path],
            resolution=res,
            duration=dur,
            task_type=task_type,
            cleanup=True,
            lora_name=lora_name,
        ),
    )

    _cleanup_context(context, user_id)
    return ConversationHandler.END


async def cancel_conversation(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    return await handle_standard_fsm_cancel(
        update,
        context,
        cleanup_func=lambda: _cleanup_context(
            context, update.effective_user.id if update.effective_user else 0
        ),
        translate_func=_t,
        reply_text_func=robust_reply_text,
    )


async def timeout_conversation(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    return await handle_standard_fsm_timeout(
        update,
        context,
        cleanup_func=lambda: _cleanup_context(
            context, update.effective_user.id if update.effective_user else 0
        ),
        translate_func=_t,
        reply_text_func=robust_reply_text,
    )


async def unexpected_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await handle_standard_fsm_unexpected_input(
        update,
        context,
        cleanup_func=lambda: _cleanup_context(
            context, update.effective_user.id if update.effective_user else 0
        ),
        translate_func=_t,
        reply_text_func=robust_reply_text,
    )


def _build_image_to_video_fsm_handler(
    *,
    entry_points: list,
    handler_name: str,
) -> ConversationHandler:
    return ConversationHandler(
        entry_points=entry_points,
        states={
            ImageToVideoState.WAIT_LORA_SELECTION: [
                CallbackQueryHandler(handle_lora_selection, pattern="^lora_select_"),
                MessageHandler(
                    (filters.TEXT | filters.COMMAND) & ~filters.Regex(r"^/cancel$"),
                    unexpected_input,
                ),
            ],
            ImageToVideoState.WAIT_IMAGE: [
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, receive_image),
                MessageHandler(
                    (filters.TEXT | filters.COMMAND) & ~filters.Regex(r"^/cancel$"),
                    unexpected_input,
                ),
            ],
            ImageToVideoState.WAIT_SETTINGS_AND_PROMPT: [
                CallbackQueryHandler(process_settings, pattern="^set_(res|dur)_"),
                MessageHandler(
                    (filters.TEXT | filters.COMMAND) & ~filters.Regex(r"^/cancel$"),
                    receive_prompt,
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
        name=handler_name,
        persistent=False,
    )


def get_image_to_video_fsm_handler() -> ConversationHandler:
    return _build_image_to_video_fsm_handler(
        entry_points=[
            CommandHandler("image_to_video", start_image_to_video),
            CommandHandler("video_lora", start_image_to_video),
            CommandHandler("custom_video", start_custom_video),
            MessageHandler(I18nFilter("menu.video_lora"), start_image_to_video),
            MessageHandler(I18nFilter("menu.custom_video"), start_custom_video),
            CallbackQueryHandler(
                start_image_to_video, pattern="^fsm_start_image_to_video$"
            ),
            CallbackQueryHandler(
                start_image_to_video, pattern="^fsm_start_video_lora$"
            ),
            CallbackQueryHandler(
                start_custom_video, pattern="^fsm_start_custom_video$"
            ),
        ],
        handler_name="image_to_video_fsm",
    )
