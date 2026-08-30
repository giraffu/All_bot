import asyncio
import json
import logging
import os
from pathlib import Path
import subprocess

from telegram import Update
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from src.domain_config.ltx25_video_upscale import (
    LTX25_VIDEO_UPSCALE_COST,
    LTX25_VIDEO_UPSCALE_MAX_BYTES,
)
from src.filters.i18n_filter import I18nFilter
from src.handlers.conversation_states import Ltx25VideoUpscaleState
from src.handlers.fsm.fsm_shared import (
    handle_standard_fsm_cancel,
    handle_standard_fsm_timeout,
    translate_fsm_text,
)
from src.services.fsm_temp_file_service import (
    cleanup_fsm_temp_files,
    download_telegram_file_to_fsm_temp,
)
from src.services.task_service_entrypoints_specialized import (
    process_ltx25_video_upscale_task,
)
from src.utils import create_background_task, robust_reply_text

logger = logging.getLogger("fsm.ltx25_video_upscale")
_t = translate_fsm_text
DATA_KEY = "ltx25_video_upscale_data"
LOCK = "LTX25_VIDEO_UPSCALE"
VIDEO_SUFFIXES = {".mp4", ".mov", ".webm"}


def _enabled() -> bool:
    return os.getenv("LTX25_VIDEO_UPSCALE_ENABLED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _cleanup_context(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("in_conversation", None)
    data = context.user_data.pop(DATA_KEY, {})
    video_path = data.get("video_path")
    if video_path:
        cleanup_fsm_temp_files([video_path])


def _probe_duration_seconds(path: str) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            path,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError("ffprobe failed")
    return float(json.loads(result.stdout.decode("utf-8"))["format"]["duration"])


async def start_upscale(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not _enabled():
        await robust_reply_text(
            update.message, _t(context, "fsm.ltx25_upscale.disabled")
        )
        return ConversationHandler.END
    if context.user_data.get("in_conversation"):
        await robust_reply_text(update.message, _t(context, "fsm.common.conflict"))
        return ConversationHandler.END
    context.user_data["in_conversation"] = LOCK
    context.user_data[DATA_KEY] = {}
    await robust_reply_text(
        update.message,
        _t(
            context,
            "fsm.ltx25_upscale.start",
            cost=LTX25_VIDEO_UPSCALE_COST,
            max_mb=LTX25_VIDEO_UPSCALE_MAX_BYTES // 1024 // 1024,
        ),
    )
    return Ltx25VideoUpscaleState.WAIT_VIDEO


def _video_info(update: Update):
    message = update.message
    if message and message.video:
        return (
            message.video.file_id,
            ".mp4",
            message.video.file_size,
            message.video.duration,
        )
    if (
        message
        and message.document
        and (message.document.mime_type or "").startswith("video/")
    ):
        suffix = Path(message.document.file_name or "").suffix.lower()
        return (
            message.document.file_id,
            suffix if suffix in VIDEO_SUFFIXES else ".mp4",
            message.document.file_size,
            None,
        )
    return None, ".mp4", None, None


async def receive_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message
    file_id, suffix, size, telegram_duration = _video_info(update)
    if not file_id:
        await robust_reply_text(message, _t(context, "fsm.common.invalid_video"))
        return Ltx25VideoUpscaleState.WAIT_VIDEO
    if size and size > LTX25_VIDEO_UPSCALE_MAX_BYTES:
        await robust_reply_text(message, _t(context, "fsm.ltx25_upscale.too_large"))
        return Ltx25VideoUpscaleState.WAIT_VIDEO
    if telegram_duration and telegram_duration > 5:
        await robust_reply_text(message, _t(context, "fsm.ltx25_upscale.too_long"))
        return Ltx25VideoUpscaleState.WAIT_VIDEO
    local_path = None
    try:
        telegram_file = await context.bot.get_file(file_id)
        local_path = await download_telegram_file_to_fsm_temp(
            telegram_file=telegram_file,
            suffix=suffix,
            name_hint="ltx25_upscale",
        )
        if os.path.getsize(local_path) > LTX25_VIDEO_UPSCALE_MAX_BYTES:
            raise ValueError("too_large")
        duration = await asyncio.to_thread(_probe_duration_seconds, local_path)
        if duration > 5.1:
            cleanup_fsm_temp_files([local_path])
            await robust_reply_text(message, _t(context, "fsm.ltx25_upscale.too_long"))
            return Ltx25VideoUpscaleState.WAIT_VIDEO
    except ValueError as exc:
        cleanup_fsm_temp_files([local_path])
        key = (
            "fsm.ltx25_upscale.too_large"
            if str(exc) == "too_large"
            else "fsm.common.invalid_video"
        )
        await robust_reply_text(message, _t(context, key))
        return Ltx25VideoUpscaleState.WAIT_VIDEO
    except Exception as exc:
        cleanup_fsm_temp_files([local_path])
        logger.warning("Failed to prepare LTX-2.5 upscale upload: %s", exc)
        await robust_reply_text(
            message, _t(context, "fsm.common.download_video_failed")
        )
        return Ltx25VideoUpscaleState.WAIT_VIDEO

    context.user_data[DATA_KEY]["video_path"] = local_path
    owned_path = context.user_data[DATA_KEY].pop("video_path")
    user = update.effective_user
    await robust_reply_text(message, _t(context, "fsm.ltx25_upscale.submitting"))
    create_background_task(
        context,
        process_ltx25_video_upscale_task(
            context=context,
            chat_id=message.chat_id,
            user_id=user.id,
            username=user.username,
            video_path=owned_path,
            message_id=message.message_id,
            cleanup=True,
        ),
    )
    _cleanup_context(context)
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await handle_standard_fsm_cancel(
        update,
        context,
        cleanup_func=lambda: _cleanup_context(context),
        translate_func=_t,
        reply_text_func=robust_reply_text,
    )


async def timeout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await handle_standard_fsm_timeout(
        update,
        context,
        cleanup_func=lambda: _cleanup_context(context),
        translate_func=_t,
        reply_text_func=robust_reply_text,
    )


def get_ltx25_video_upscale_fsm_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            MessageHandler(I18nFilter("menu.video_upscale"), start_upscale),
            CommandHandler("video_upscale", start_upscale),
        ],
        states={
            Ltx25VideoUpscaleState.WAIT_VIDEO: [
                MessageHandler(filters.VIDEO | filters.Document.VIDEO, receive_video),
                MessageHandler(filters.ALL & ~filters.COMMAND, receive_video),
            ],
            ConversationHandler.TIMEOUT: [MessageHandler(filters.ALL, timeout)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        conversation_timeout=300,
        name="ltx25_video_upscale_fsm",
        persistent=False,
    )
