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

from src.constants import RESOLUTION_COST
from src.handlers.conversation_states import FaceVideoState
from src.handlers.prompt_router import GLOBAL_REVERSE_MAP, is_global_menu_command
from src.services.bot_task_service import process_face_video_task
from src.services.permission_service import permission_service
from src.services.fsm_temp_file_service import (
    cleanup_fsm_temp_files,
    download_telegram_file_to_fsm_temp,
)
from src.utils import create_background_task, robust_edit_text, robust_reply_text
import contextlib

from src.filters.i18n_filter import I18nFilter
from src.i18n.translator import get_text

logger = logging.getLogger("fsm.face_video")


def _t(context: ContextTypes.DEFAULT_TYPE, key: str, **kwargs) -> str:
    translator = getattr(context, "t", None)
    if callable(translator):
        return translator(key, **kwargs)
    lang = getattr(context, "lang", None)
    if not lang and getattr(context, "user_data", None):
        lang = context.user_data.get("language_code")
    return get_text(key, lang or "zh", **kwargs)


# --- Helpers ---
def _cleanup_context(context: ContextTypes.DEFAULT_TYPE, _user_id: int):
    """Clean up user data upon exit to prevent memory leaks and reset conversation locks."""
    # Remove conversation lock
    context.user_data.pop("in_conversation", None)

    # Clean up downloaded files to avoid disk leaks
    pending_files = context.user_data.pop("face_video_data", {})
    cleanup_fsm_temp_files(
        [pending_files.get("face_image_path"), pending_files.get("video_path")]
    )


# --- Entry Point ---
async def start_face_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point for Video Face Swap."""
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

    # 1. Concurrency Check (User Data Lock)
    if context.user_data.get("in_conversation"):
        msg = _t(context, "fsm.common.conflict")
        if update.callback_query:
            await robust_edit_text(update.callback_query.message, msg)
        else:
            await robust_reply_text(update.message, msg)
        return ConversationHandler.END

    # 2. Lock the user context for this flow
    context.user_data["in_conversation"] = "FACE_VIDEO"
    # Initialize isolated data storage
    context.user_data["face_video_data"] = {}

    msg = _t(context, "fsm.face_video.start")
    if update.callback_query:
        await robust_edit_text(
            update.callback_query.message, msg, parse_mode="Markdown"
        )
    else:
        await robust_reply_text(update.message, msg, parse_mode="Markdown")

    return FaceVideoState.WAIT_FACE_IMAGE


# --- State 1: Receive Face Image ---
async def receive_face_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """State 1: Handle uploaded face image."""
    user_id = update.effective_user.id
    message = update.message

    # Handle document vs photo
    if message.document:
        if not message.document.mime_type.startswith("image/"):
            await robust_reply_text(
                message, _t(context, "fsm.common.invalid_image_file")
            )
            return FaceVideoState.WAIT_FACE_IMAGE
        file_id = message.document.file_id
    elif message.photo:
        file_id = message.photo[-1].file_id
    else:
        await robust_reply_text(message, _t(context, "fsm.common.invalid_image"))
        return FaceVideoState.WAIT_FACE_IMAGE

    # Download file
    try:
        new_file = await context.bot.get_file(file_id)
        local_path = await download_telegram_file_to_fsm_temp(
            telegram_file=new_file,
            suffix=".png",
            name_hint="face_video_face",
        )

        # Save to FSM isolated data
        context.user_data["face_video_data"]["face_image_path"] = local_path
    except Exception as e:
        logger.error(f"Error downloading face image for FSM user {user_id}: {e}")
        await robust_reply_text(message, _t(context, "fsm.common.download_image_failed"))
        return FaceVideoState.WAIT_FACE_IMAGE

    await robust_reply_text(
        message,
        _t(context, "fsm.face_video.face_received"),
        parse_mode="Markdown",
    )
    return FaceVideoState.WAIT_VIDEO


# --- State 2: Receive Video ---
async def receive_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """State 2: Handle uploaded video and prompt for resolution."""
    user_id = update.effective_user.id
    message = update.message

    if message.document:
        if not message.document.mime_type.startswith("video/"):
            await robust_reply_text(
                message, _t(context, "fsm.common.invalid_video_file")
            )
            return FaceVideoState.WAIT_VIDEO
        file_id = message.document.file_id
    elif message.video:
        file_id = message.video.file_id
    else:
        await robust_reply_text(message, _t(context, "fsm.common.invalid_video"))
        return FaceVideoState.WAIT_VIDEO

    # Download file
    try:
        new_file = await context.bot.get_file(file_id)
        local_path = await download_telegram_file_to_fsm_temp(
            telegram_file=new_file,
            suffix=".mp4",
            name_hint="face_video_video",
        )

        context.user_data["face_video_data"]["video_path"] = local_path
    except Exception as e:
        logger.error(f"Error downloading video for FSM user {user_id}: {e}")
        await robust_reply_text(
            message, _t(context, "fsm.common.download_video_failed")
        )
        return FaceVideoState.WAIT_VIDEO

    # Present Resolution Selection
    keyboard = [
        [
            InlineKeyboardButton(
                _t(
                    context,
                    "fsm.face_video.resolution_720",
                    cost=RESOLUTION_COST.get("720p", 18),
                ),
                callback_data="fsm_fv_res_720",
            ),
            InlineKeyboardButton(
                _t(
                    context,
                    "fsm.face_video.resolution_1024",
                    cost=RESOLUTION_COST.get("1024p", 36),
                ),
                callback_data="fsm_fv_res_1024",
            ),
        ],
        [InlineKeyboardButton(_t(context, "fsm.face_video.cancel_button"), callback_data="fsm_fv_cancel")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await robust_reply_text(
        message,
        _t(context, "fsm.face_video.video_received"),
        reply_markup=reply_markup,
        parse_mode="Markdown",
    )
    return FaceVideoState.SELECT_RESOLUTION


# --- State 3: Resolution Selected ---
async def process_resolution_selection(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """State 3: User selected resolution, start task execution."""
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data

    await query.answer(text=_t(context, "fsm.common.task_initializing"), cache_time=2)

    if data == "fsm_fv_cancel":
        await robust_edit_text(query.message, _t(context, "fsm.face_video.cancelled_short"))
        _cleanup_context(context, user_id)
        return ConversationHandler.END

    # Parse resolution
    res_str = data.split("_")[-1]
    resolution = int(res_str)
    cost = RESOLUTION_COST.get(f"{res_str}p", 20)
    duration = 121  # Assuming a max standard duration

    # Validate Priority & Balance
    from src.core.user_core import get_or_create_user_by_telegram

    internal_user, _ = await get_or_create_user_by_telegram(user_id)
    priority = await permission_service.calculate_user_priority(internal_user.id)
    if priority <= 0:
        await robust_edit_text(
            query.message,
            _t(context, "fsm.face_video.priority_exhausted"),
        )
        _cleanup_context(context, user_id)
        return ConversationHandler.END

    fsm_data = context.user_data.get("face_video_data", {})
    if not fsm_data:
        with contextlib.suppress(Exception):
            await query.answer(_t(context, "fsm.face_video.expired_alert"), show_alert=True)
        return ConversationHandler.END

    face_path = fsm_data.pop("face_image_path", None)
    video_path = fsm_data.pop("video_path", None)

    if not face_path or not video_path:
        return ConversationHandler.END  # Prevent double submit

    # Update message
    await robust_edit_text(
        query.message,
        _t(context, "fsm.face_video.submitting", resolution=resolution, cost=cost),
    )

    create_background_task(
        context,
        process_face_video_task(
            context,
            query.message.chat_id,
            user_id,
            query.from_user.username,
            face_path,
            video_path,
            resolution,
            duration=duration,
            cost=cost,
            message_id=query.message.message_id,
            cleanup=True,  # TaskService will delete the files
        ),
    )

    # Conversation finished successfully!
    _cleanup_context(context, user_id)
    return ConversationHandler.END


# --- Fallbacks & Timeout ---
async def cancel_conversation(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """User invoked /cancel during the FSM."""
    user_id = update.effective_user.id
    msg = _t(context, "fsm.common.cancelled")

    if update.callback_query:
        await robust_edit_text(update.callback_query.message, msg)
    else:
        await robust_reply_text(update.message, msg)

    _cleanup_context(context, user_id)
    return ConversationHandler.END


async def timeout_conversation(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Triggered when conversation times out (e.g. user took too long)."""
    # Note: Depending on PTB version, timeout might be triggered via different mechanism.
    # But usually it calls the TIMEOUT fallback.
    user_id = update.effective_user.id if update.effective_user else "Unknown"
    logger.info(f"FSM timeout for user {user_id}")

    if update and update.message:
        await robust_reply_text(
            update.message,
            _t(context, "fsm.common.timeout"),
        )

    _cleanup_context(context, user_id)
    return ConversationHandler.END


async def unexpected_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text if update.message else ""
    if text and is_global_menu_command(text):
        route_key = GLOBAL_REVERSE_MAP.get(text)
        user_id = update.effective_user.id if update.effective_user else "Unknown"
        _cleanup_context(context, user_id)
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
    return None  # Return None keeps the state unchanged in PTB


# --- FSM Factory ---
def get_face_video_fsm_handler() -> ConversationHandler:
    """Factory to build the Face Video ConversationHandler."""
    return ConversationHandler(
        entry_points=[
            CommandHandler("video_swap", start_face_video),
            MessageHandler(I18nFilter("menu.face_video"), start_face_video),
            CallbackQueryHandler(start_face_video, pattern="^fsm_start_face_video$"),
        ],
        states={
            FaceVideoState.WAIT_FACE_IMAGE: [
                MessageHandler(
                    filters.PHOTO | filters.Document.IMAGE, receive_face_image
                ),
                MessageHandler(
                    (filters.TEXT | filters.COMMAND) & ~filters.Regex(r"^/cancel$"),
                    unexpected_input,
                ),
            ],
            FaceVideoState.WAIT_VIDEO: [
                MessageHandler(filters.VIDEO | filters.Document.VIDEO, receive_video),
                MessageHandler(
                    (filters.TEXT | filters.COMMAND) & ~filters.Regex(r"^/cancel$"),
                    unexpected_input,
                ),
            ],
            FaceVideoState.SELECT_RESOLUTION: [
                CallbackQueryHandler(
                    process_resolution_selection, pattern="^fsm_fv_res_"
                ),
                CallbackQueryHandler(
                    process_resolution_selection, pattern="^fsm_fv_cancel$"
                ),
            ],
            # PTB uses ConversationHandler.TIMEOUT internally
            ConversationHandler.TIMEOUT: [
                MessageHandler(filters.ALL, timeout_conversation)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
        conversation_timeout=300,  # 5 minutes timeout to prevent dangling locks
        name="face_video_fsm",
        persistent=False,  # Assuming no FSM persistence in DB for now
    )
