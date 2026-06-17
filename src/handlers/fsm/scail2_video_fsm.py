import contextlib
import logging
import os
from pathlib import Path

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
    MODE_NAME_MAP,
    MODE_SCAIL2_ACTION_TRANSFER,
    MODE_SCAIL2_VIDEO_REPLACEMENT,
)
from src.core.exceptions import InsufficientCreditsError
from src.domain_config.scail2_video import (
    SCAIL2_ALLOWED_DURATION_SECONDS,
    get_scail2_cost,
    normalize_scail2_duration_seconds,
)
from src.filters.i18n_filter import I18nFilter
from src.handlers.conversation_states import Scail2VideoState
from src.handlers.fsm.fsm_shared import (
    handle_standard_fsm_cancel,
    handle_standard_fsm_timeout,
    handle_standard_fsm_unexpected_input,
    translate_fsm_text,
)
from src.handlers.prompt_router import is_global_menu_command
from src.services.fsm_temp_file_service import (
    cleanup_fsm_temp_files,
    download_telegram_file_to_fsm_temp,
)
from src.services.permission_service import permission_service
from src.services.task_service_entrypoints_specialized import process_scail2_video_task
from src.utils import create_background_task, robust_edit_text, robust_reply_text

logger = logging.getLogger("fsm.scail2_video")

_t = translate_fsm_text

SCAIL2_VIDEO_DATA_KEY = "scail2_video_data"
SCAIL2_CONVERSATION_LOCK = "SCAIL2_VIDEO"
SCAIL2_MAX_MOTION_VIDEO_MB = 40
SCAIL2_MAX_MOTION_VIDEO_BYTES = SCAIL2_MAX_MOTION_VIDEO_MB * 1024 * 1024
_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
_VIDEO_SUFFIXES = {".mp4", ".mov", ".webm", ".avi", ".mkv"}
_CANCEL_COMMAND_FILTER = filters.Regex(r"^/cancel(?:@\w+)?(?:\s|$)")
_NON_CANCEL_INPUT_FILTER = filters.ALL & ~_CANCEL_COMMAND_FILTER
_NON_CANCEL_TEXT_OR_COMMAND_FILTER = (
    (filters.TEXT | filters.COMMAND) & ~_CANCEL_COMMAND_FILTER
)


def _cleanup_context(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("in_conversation", None)
    pending_files = context.user_data.pop(SCAIL2_VIDEO_DATA_KEY, {})
    cleanup_fsm_temp_files(
        [
            pending_files.get("reference_image_path"),
            pending_files.get("motion_video_path"),
        ]
    )


def _consume_scail2_inputs(
    context: ContextTypes.DEFAULT_TYPE,
) -> tuple[str | None, str | None]:
    fsm_data = context.user_data.get(SCAIL2_VIDEO_DATA_KEY, {})
    return (
        fsm_data.pop("reference_image_path", None),
        fsm_data.pop("motion_video_path", None),
    )


def _get_mode_name(context: ContextTypes.DEFAULT_TYPE, task_type: str) -> str:
    return _t(context, MODE_NAME_MAP[task_type])


def _safe_suffix(file_name: str | None, *, default: str, allowed: set[str]) -> str:
    suffix = Path(file_name or "").suffix.lower()
    return suffix if suffix in allowed else default


def _build_duration_keyboard(context: ContextTypes.DEFAULT_TYPE) -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton(
                _t(
                    context,
                    "fsm.scail2_video.duration_button",
                    duration=duration,
                    cost=get_scail2_cost(duration, strict=True),
                ),
                callback_data=f"fsm_scail2_duration_{duration}",
            )
            for duration in SCAIL2_ALLOWED_DURATION_SECONDS
        ],
        [
            InlineKeyboardButton(
                _t(context, "fsm.scail2_video.cancel_button"),
                callback_data="fsm_scail2_cancel",
            )
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def _extract_reference_image(update: Update) -> tuple[str | None, str, int | None]:
    message = update.message
    if not message:
        return None, ".png", None

    if message.document:
        mime_type = message.document.mime_type or ""
        if not mime_type.startswith("image/"):
            return None, ".png", None
        return (
            message.document.file_id,
            _safe_suffix(
                message.document.file_name,
                default=".png",
                allowed=_IMAGE_SUFFIXES,
            ),
            message.document.file_size,
        )

    if message.photo:
        return message.photo[-1].file_id, ".jpg", None

    return None, ".png", None


def _extract_motion_video(update: Update) -> tuple[str | None, str, int | None, bool]:
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


def _is_too_large(size: int | None) -> bool:
    return bool(size and size > SCAIL2_MAX_MOTION_VIDEO_BYTES)


async def _start_scail2_video(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    task_type: str,
) -> int:
    from src.utils import is_maintenance_mode

    if is_maintenance_mode():
        await robust_reply_text(
            update.message,
            _t(context, "fsm.common.maintenance"),
            parse_mode="Markdown",
        )
        return ConversationHandler.END

    if context.user_data.get("in_conversation"):
        await robust_reply_text(update.message, _t(context, "fsm.common.conflict"))
        return ConversationHandler.END

    cost = get_scail2_cost(5, strict=True)
    context.user_data["in_conversation"] = SCAIL2_CONVERSATION_LOCK
    context.user_data[SCAIL2_VIDEO_DATA_KEY] = {"task_type": task_type}

    await robust_reply_text(
        update.message,
        _t(
            context,
            "fsm.scail2_video.start",
            mode_name=_get_mode_name(context, task_type),
            cost=cost,
        ),
        parse_mode="Markdown",
    )
    return Scail2VideoState.WAIT_REFERENCE_IMAGE


async def start_video_replacement(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    return await _start_scail2_video(
        update,
        context,
        task_type=MODE_SCAIL2_VIDEO_REPLACEMENT,
    )


async def start_action_transfer(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    return await _start_scail2_video(
        update,
        context,
        task_type=MODE_SCAIL2_ACTION_TRANSFER,
    )


async def receive_reference_image(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    message = update.message
    file_id, suffix, _file_size = _extract_reference_image(update)
    if not file_id:
        if message and message.document:
            await robust_reply_text(
                message, _t(context, "fsm.common.invalid_image_file")
            )
        else:
            await robust_reply_text(message, _t(context, "fsm.common.invalid_image"))
        return Scail2VideoState.WAIT_REFERENCE_IMAGE

    try:
        new_file = await context.bot.get_file(file_id)
        local_path = await download_telegram_file_to_fsm_temp(
            telegram_file=new_file,
            suffix=suffix,
            name_hint="scail2_reference",
        )
        context.user_data[SCAIL2_VIDEO_DATA_KEY][
            "reference_image_path"
        ] = local_path
    except Exception as exc:
        user_id = getattr(update.effective_user, "id", "unknown")
        logger.error("Error downloading SCAIL-2 reference image for %s: %s", user_id, exc)
        await robust_reply_text(message, _t(context, "fsm.common.download_image_failed"))
        return Scail2VideoState.WAIT_REFERENCE_IMAGE

    await robust_reply_text(
        message,
        _t(
            context,
            "fsm.scail2_video.reference_received",
            max_mb=SCAIL2_MAX_MOTION_VIDEO_MB,
        ),
        parse_mode="Markdown",
    )
    return Scail2VideoState.WAIT_MOTION_VIDEO


async def receive_motion_video(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    message = update.message
    file_id, suffix, file_size, is_document = _extract_motion_video(update)
    if not file_id:
        if is_document:
            await robust_reply_text(
                message, _t(context, "fsm.common.invalid_video_file")
            )
        else:
            await robust_reply_text(message, _t(context, "fsm.common.invalid_video"))
        return Scail2VideoState.WAIT_MOTION_VIDEO

    if _is_too_large(file_size):
        await robust_reply_text(
            message,
            _t(
                context,
                "fsm.scail2_video.video_too_large",
                max_mb=SCAIL2_MAX_MOTION_VIDEO_MB,
            ),
        )
        return Scail2VideoState.WAIT_MOTION_VIDEO

    try:
        new_file = await context.bot.get_file(file_id)
        if _is_too_large(getattr(new_file, "file_size", None)):
            await robust_reply_text(
                message,
                _t(
                    context,
                    "fsm.scail2_video.video_too_large",
                    max_mb=SCAIL2_MAX_MOTION_VIDEO_MB,
                ),
            )
            return Scail2VideoState.WAIT_MOTION_VIDEO

        local_path = await download_telegram_file_to_fsm_temp(
            telegram_file=new_file,
            suffix=suffix,
            name_hint="scail2_motion",
        )

        if _is_too_large(os.path.getsize(local_path)):
            cleanup_fsm_temp_files([local_path])
            await robust_reply_text(
                message,
                _t(
                    context,
                    "fsm.scail2_video.video_too_large",
                    max_mb=SCAIL2_MAX_MOTION_VIDEO_MB,
                ),
            )
            return Scail2VideoState.WAIT_MOTION_VIDEO

        context.user_data[SCAIL2_VIDEO_DATA_KEY]["motion_video_path"] = local_path
    except Exception as exc:
        user_id = getattr(update.effective_user, "id", "unknown")
        logger.error("Error downloading SCAIL-2 motion video for %s: %s", user_id, exc)
        await robust_reply_text(message, _t(context, "fsm.common.download_video_failed"))
        return Scail2VideoState.WAIT_MOTION_VIDEO

    await robust_reply_text(
        message,
        _t(context, "fsm.scail2_video.video_received"),
        parse_mode="Markdown",
    )
    return Scail2VideoState.WAIT_PROMPT


async def receive_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message
    prompt = (message.text or "").strip() if message else ""

    if is_global_menu_command(prompt):
        return await unexpected_input(update, context)

    if not prompt:
        await robust_reply_text(message, _t(context, "fsm.scail2_video.empty_prompt"))
        return Scail2VideoState.WAIT_PROMPT

    fsm_data = context.user_data.get(SCAIL2_VIDEO_DATA_KEY)
    if not fsm_data:
        await robust_reply_text(message, _t(context, "fsm.common.already_submitted"))
        return ConversationHandler.END

    fsm_data["prompt"] = prompt
    await robust_reply_text(
        message,
        _t(context, "fsm.scail2_video.prompt_received"),
        reply_markup=_build_duration_keyboard(context),
        parse_mode="Markdown",
    )
    return Scail2VideoState.WAIT_DURATION


async def receive_non_text_prompt(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    await robust_reply_text(update.message, _t(context, "fsm.scail2_video.prompt_only"))
    return Scail2VideoState.WAIT_PROMPT


async def process_duration_selection(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    user = query.from_user
    data = query.data or ""

    if data == "fsm_scail2_cancel":
        await query.answer(text=_t(context, "fsm.common.task_initializing"), cache_time=2)
        await robust_edit_text(
            query.message, _t(context, "fsm.scail2_video.cancelled_short")
        )
        _cleanup_context(context)
        return ConversationHandler.END

    fsm_data = context.user_data.get(SCAIL2_VIDEO_DATA_KEY)
    if not fsm_data:
        with contextlib.suppress(Exception):
            await query.answer(
                _t(context, "fsm.scail2_video.expired_alert"),
                show_alert=True,
            )
        return ConversationHandler.END

    await query.answer(text=_t(context, "fsm.common.task_initializing"), cache_time=2)

    try:
        duration = normalize_scail2_duration_seconds(
            data.rsplit("_", 1)[-1],
            strict=True,
        )
    except Exception:
        await robust_edit_text(
            query.message,
            _t(context, "fsm.scail2_video.invalid_duration"),
        )
        _cleanup_context(context)
        return ConversationHandler.END

    cost = get_scail2_cost(duration, strict=True)
    try:
        await permission_service.check_quota(
            user.id,
            user.username,
            getattr(user, "full_name", None),
            cost=cost,
        )
    except Exception as exc:
        if isinstance(exc, InsufficientCreditsError):
            await robust_edit_text(
                query.message,
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
        raise

    reference_path, motion_path = _consume_scail2_inputs(context)
    task_type = fsm_data.get("task_type")
    prompt = fsm_data.get("prompt", "")

    if not reference_path or not motion_path or not task_type or not prompt:
        await robust_edit_text(query.message, _t(context, "fsm.common.already_submitted"))
        _cleanup_context(context)
        return ConversationHandler.END

    await robust_edit_text(
        query.message,
        _t(
            context,
            "fsm.scail2_video.submitting",
            mode_name=_get_mode_name(context, task_type),
            duration=duration,
            cost=cost,
        ),
    )

    create_background_task(
        context,
        process_scail2_video_task(
            context=context,
            chat_id=query.message.chat_id,
            user_id=user.id,
            username=user.username,
            task_type=task_type,
            reference_image_path=reference_path,
            motion_video_path=motion_path,
            prompt=prompt,
            duration=duration,
            message_id=query.message.message_id,
            cleanup=True,
        ),
    )

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
        cleanup_func=lambda: _cleanup_context(context),
        translate_func=_t,
        reply_text_func=robust_reply_text,
    )


async def unexpected_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    result = await handle_standard_fsm_unexpected_input(
        update,
        context,
        cleanup_func=lambda: _cleanup_context(context),
        translate_func=_t,
        reply_text_func=robust_reply_text,
    )
    return Scail2VideoState.WAIT_REFERENCE_IMAGE if result is None else result


async def unexpected_motion_input(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    result = await handle_standard_fsm_unexpected_input(
        update,
        context,
        cleanup_func=lambda: _cleanup_context(context),
        translate_func=_t,
        reply_text_func=robust_reply_text,
    )
    return Scail2VideoState.WAIT_MOTION_VIDEO if result is None else result


def get_scail2_video_fsm_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            MessageHandler(
                I18nFilter("menu.video_to_video_replacement"),
                start_video_replacement,
            ),
            MessageHandler(
                I18nFilter("menu.video_to_video_action_transfer"),
                start_action_transfer,
            ),
        ],
        states={
            Scail2VideoState.WAIT_REFERENCE_IMAGE: [
                MessageHandler(
                    filters.PHOTO | filters.Document.ALL,
                    receive_reference_image,
                ),
                MessageHandler(
                    _NON_CANCEL_TEXT_OR_COMMAND_FILTER,
                    unexpected_input,
                ),
                MessageHandler(_NON_CANCEL_INPUT_FILTER, receive_reference_image),
            ],
            Scail2VideoState.WAIT_MOTION_VIDEO: [
                MessageHandler(
                    filters.VIDEO | filters.Document.ALL,
                    receive_motion_video,
                ),
                MessageHandler(
                    _NON_CANCEL_TEXT_OR_COMMAND_FILTER,
                    unexpected_motion_input,
                ),
                MessageHandler(_NON_CANCEL_INPUT_FILTER, receive_motion_video),
            ],
            Scail2VideoState.WAIT_PROMPT: [
                MessageHandler(
                    _NON_CANCEL_TEXT_OR_COMMAND_FILTER,
                    receive_prompt,
                ),
                MessageHandler(
                    filters.PHOTO | filters.VIDEO | filters.Document.ALL,
                    receive_non_text_prompt,
                ),
                MessageHandler(_NON_CANCEL_INPUT_FILTER, receive_non_text_prompt),
            ],
            Scail2VideoState.WAIT_DURATION: [
                CallbackQueryHandler(
                    process_duration_selection,
                    pattern="^fsm_scail2_duration_",
                ),
                CallbackQueryHandler(
                    process_duration_selection,
                    pattern="^fsm_scail2_cancel$",
                ),
            ],
            ConversationHandler.TIMEOUT: [
                MessageHandler(_NON_CANCEL_INPUT_FILTER, timeout_conversation)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
        conversation_timeout=300,
        name="scail2_video_fsm",
        persistent=False,
    )
