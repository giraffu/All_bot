import logging
import os

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
    MODE_BLOWJOB,
    MODE_CLOSEUP_BLOWJOB,
    MODE_DOGGY_STYLE,
    MODE_PERFECT_VIDEO_INSERT,
    MODE_UNDRESS_TONGUE,
    RESOLUTION_COST,
    get_video_settings_keyboard,
)
from src.handlers.fsm.fsm_shared import (
    handle_standard_fsm_cancel,
    handle_standard_fsm_timeout,
    handle_standard_fsm_unexpected_input,
    translate_fsm_text,
)
from src.handlers.conversation_states import QuickVideoState
from src.handlers.prompt_router import GLOBAL_REVERSE_MAP, is_global_menu_command
from src.services.permission_service import permission_service
from src.services.task_service_entrypoints_video import process_video_task_template
from src.services.fsm_temp_file_service import (
    cleanup_fsm_temp_files,
    download_telegram_file_to_fsm_temp,
)
from src.utils import create_background_task, robust_edit_text, robust_reply_text
import contextlib

from src.filters.i18n_filter import I18nFilter

logger = logging.getLogger("fsm.quick_video")

QUICK_VIDEO_MODES = {
    "menu.video_edit_missionary": MODE_PERFECT_VIDEO_INSERT,
    "menu.video_edit_doggy": MODE_DOGGY_STYLE,
    "menu.video_edit_blowjob": MODE_BLOWJOB,
    "menu.video_edit_undress_tongue": MODE_UNDRESS_TONGUE,
    "menu.video_edit_closeup_blowjob": MODE_CLOSEUP_BLOWJOB,
}


_t = translate_fsm_text


def _cleanup_context(context: ContextTypes.DEFAULT_TYPE, _user_id: int):
    context.user_data.pop("in_conversation", None)
    fsm_data = context.user_data.pop("quick_video_data", {})
    cleanup_fsm_temp_files([fsm_data.get("image_path")])


async def start_quick_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point for 懒人动图 (单步图生视频)"""
    message = update.message or update.edited_message
    text = message.text.strip() if message and message.text else ""

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

    mode = None
    route_key = GLOBAL_REVERSE_MAP.get(text)
    if route_key:
        mode = QUICK_VIDEO_MODES.get(route_key)

    if not mode:
        return ConversationHandler.END

    context.user_data["in_conversation"] = f"QUICK_VIDEO_{mode}"
    context.user_data["quick_video_data"] = {
        "mode": mode,
        "resolution": DEFAULT_RESOLUTION,
        "duration": DEFAULT_DURATION,
        "image_path": None,
    }

    mode_name = text[2:] if len(text) > 2 else text
    msg = _t(context, "fsm.quick_video.start", mode_name=mode_name)
    await robust_reply_text(update.message, msg, parse_mode="Markdown")
    return QuickVideoState.WAIT_IMAGE


async def receive_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    message = update.message
    fsm_data = context.user_data["quick_video_data"]

    if message.document:
        if not message.document.mime_type.startswith("image/"):
            await robust_reply_text(message, _t(context, "fsm.common.invalid_image"))
            return QuickVideoState.WAIT_IMAGE
        file_id = message.document.file_id
    elif message.photo:
        file_id = message.photo[-1].file_id
    else:
        await robust_reply_text(message, _t(context, "fsm.common.invalid_image"))
        return QuickVideoState.WAIT_IMAGE

    try:
        new_file = await context.bot.get_file(file_id)
        local_path = await download_telegram_file_to_fsm_temp(
            telegram_file=new_file,
            suffix=".png",
            name_hint="quick_video",
        )
        fsm_data["image_path"] = local_path
    except Exception as e:
        logger.error(f"Error downloading image for FSM user {user_id}: {e}")
        await robust_reply_text(message, _t(context, "fsm.common.download_image_failed"))
        return QuickVideoState.WAIT_IMAGE

    # Send settings keyboard
    from src.core.user_core import get_or_create_user_by_telegram

    internal_user, _ = await get_or_create_user_by_telegram(user_id)
    internal_user_id = internal_user.id

    user_group = await permission_service.get_user_group(internal_user_id)
    user_identity = await permission_service.get_user_identity(internal_user_id)

    res = fsm_data["resolution"]
    dur = fsm_data["duration"]
    reply_markup = get_video_settings_keyboard(
        user_group, user_identity, res, dur, context.lang
    )

    base_cost = RESOLUTION_COST.get(res, 6)
    multiplier = DURATION_MULTIPLIER.get(dur, 1.0)
    cost = int(base_cost * multiplier)

    start_button_text = _t(context, "fsm.quick_video.start_button")
    msg_text = _t(
        context,
        "fsm.quick_video.settings_text",
        resolution=res,
        duration=dur,
        cost=cost,
        start_button=start_button_text,
    )

    # Add a "Start Generation" button
    keyboard = list(reply_markup.inline_keyboard)
    keyboard.append(
        [InlineKeyboardButton(start_button_text, callback_data="qvid_start_generation")]
    )
    reply_markup = InlineKeyboardMarkup(keyboard)

    await robust_reply_text(
        message, msg_text, reply_markup=reply_markup, parse_mode="Markdown"
    )
    return QuickVideoState.WAIT_SETTINGS


async def process_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data

    fsm_data = context.user_data.get("quick_video_data", {})
    if not fsm_data:
        with contextlib.suppress(Exception):
            await query.answer(_t(context, "fsm.quick_video.expired_alert"), show_alert=True)
        return ConversationHandler.END

    if data == "qvid_start_generation":
        await query.answer(text=_t(context, "fsm.common.task_initializing"), cache_time=2)
        return await start_generation(update, context)

    if data.startswith("set_res_"):
        new_res = data.split("_")[2]
        if new_res == "1024p" and fsm_data.get("duration") == "10s":
            fsm_data["duration"] = "8s"
            with contextlib.suppress(Exception):
                await query.answer(
                    _t(context, "fsm.quick_video.res_dur_conflict"), show_alert=True
                )
        fsm_data["resolution"] = new_res
    elif data.startswith("set_dur_"):
        new_dur = data.split("_")[2]
        if new_dur == "10s" and fsm_data.get("resolution") == "1024p":
            fsm_data["resolution"] = "720p"
            with contextlib.suppress(Exception):
                await query.answer(
                    _t(context, "fsm.quick_video.dur_res_conflict"), show_alert=True
                )
        fsm_data["duration"] = new_dur

    res = fsm_data["resolution"]
    dur = fsm_data["duration"]

    from src.core.user_core import get_or_create_user_by_telegram

    internal_user, _ = await get_or_create_user_by_telegram(user_id)
    internal_user_id = internal_user.id

    user_group = await permission_service.get_user_group(internal_user_id)
    user_identity = await permission_service.get_user_identity(internal_user_id)
    reply_markup = get_video_settings_keyboard(
        user_group, user_identity, res, dur, context.lang
    )

    base_cost = RESOLUTION_COST.get(res, 6)
    multiplier = DURATION_MULTIPLIER.get(dur, 1.0)
    cost = int(base_cost * multiplier)

    start_button_text = _t(context, "fsm.quick_video.start_button")
    msg_text = _t(
        context,
        "fsm.quick_video.settings_text",
        resolution=res,
        duration=dur,
        cost=cost,
        start_button=start_button_text,
    )

    keyboard = list(reply_markup.inline_keyboard)
    keyboard.append(
        [InlineKeyboardButton(start_button_text, callback_data="qvid_start_generation")]
    )
    reply_markup = InlineKeyboardMarkup(keyboard)

    with contextlib.suppress(Exception):
        await robust_edit_text(
            query.message, msg_text, reply_markup=reply_markup, parse_mode="Markdown"
        )

    await query.answer(text=_t(context, "fsm.common.task_initializing"), cache_time=2)
    return QuickVideoState.WAIT_SETTINGS


async def start_generation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        from src.utils import safe_answer_query

        await safe_answer_query(query, text=_t(context, "fsm.common.task_initializing"), cache_time=2)
    user_id = query.from_user.id

    fsm_data = context.user_data.get("quick_video_data", {})
    if not fsm_data:
        return ConversationHandler.END

    image_path = fsm_data.pop("image_path", None)
    if not image_path:
        logger.warning(
            f"user={user_id} image_path missing or already consumed in quick_video"
        )
        with contextlib.suppress(Exception):
            await query.answer(_t(context, "fsm.quick_video.already_submitted"), show_alert=True)
        _cleanup_context(context, user_id)
        return ConversationHandler.END

    res = fsm_data["resolution"]
    dur = fsm_data["duration"]
    mode = fsm_data["mode"]

    if res == "1024p" and dur == "10s":
        res = "720p"
        fsm_data["resolution"] = "720p"

    base_cost = RESOLUTION_COST.get(res, 6)
    multiplier = DURATION_MULTIPLIER.get(dur, 1.0)
    cost = int(base_cost * multiplier)

    # Keep the selected settings in context so the background task can resolve them.
    # until they are refactored to take params directly
    context.user_data["custom_video_resolution"] = res
    context.user_data["custom_video_duration"] = dur
    context.user_data["mode"] = mode

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
            if image_path and os.path.exists(image_path):
                with contextlib.suppress(OSError):
                    os.remove(image_path)
            _cleanup_context(context, user_id)
            return ConversationHandler.END
        raise e

    await robust_edit_text(
        query.message, _t(context, "fsm.quick_video.submit", cost=cost)
    )

    video_modes = {
        MODE_PERFECT_VIDEO_INSERT: ("perfect_video_insert", "missionary sex"),
        MODE_DOGGY_STYLE: ("doggy_style", "doggy style sex"),
        MODE_BLOWJOB: ("blowjob", "undress blowjob"),
        MODE_UNDRESS_TONGUE: ("undress_tongue", "undress and show tongue"),
        MODE_CLOSEUP_BLOWJOB: ("closeup_blowjob", "closeup blowjob sex"),
    }

    if mode in video_modes:
        default_prompt_key, default_prompt_text = video_modes[mode]
        create_background_task(
            context,
            process_video_task_template(
                context=context,
                mode=mode,
                default_prompt_key=default_prompt_key,
                default_prompt_text=default_prompt_text,
                image_path=image_path,
                cleanup=True,
                allow_contribute=True,
                chat_id=query.message.chat_id,
                user_id=user_id,
                username=update.effective_user.username,
                status_msg_id=query.message.message_id,
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
        prefer_edit_callback=True,
        reply_text_func=robust_reply_text,
        edit_text_func=robust_edit_text,
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


def get_quick_video_fsm_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            MessageHandler(
                I18nFilter(
                    [
                        "menu.video_edit_missionary",
                        "menu.video_edit_doggy",
                        "menu.video_edit_blowjob",
                        "menu.video_edit_undress_tongue",
                        "menu.video_edit_closeup_blowjob",
                    ]
                ),
                start_quick_video,
            )
        ],
        states={
            QuickVideoState.WAIT_IMAGE: [
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, receive_image),
                MessageHandler(
                    (filters.TEXT | filters.COMMAND) & ~filters.Regex(r"^/cancel$"),
                    unexpected_input,
                ),
            ],
            QuickVideoState.WAIT_SETTINGS: [
                CallbackQueryHandler(
                    process_settings, pattern="^set_(res|dur)_|^qvid_start_generation$"
                ),
                MessageHandler(
                    filters.ALL & ~filters.Regex(r"^/cancel$"), unexpected_input
                ),
            ],
            ConversationHandler.TIMEOUT: [
                MessageHandler(filters.ALL, timeout_conversation)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
        conversation_timeout=300,
        name="quick_video_fsm",
        persistent=False,
    )
