import logging
from collections.abc import Awaitable, Callable

from src.core.task_lifecycle_contract import (
    is_backend_cancelled_status,
    is_backend_failed_status,
    is_backend_success_status,
)
from src.i18n.translator import get_text
from src.services.tg_task_progress_presentation import (
    build_done_progress_text,
    build_pending_status_text,
    build_running_status_text,
    normalize_pending_queue_position,
)
from src.services.tg_task_result_presentation import (
    build_result_reply_markup,
    record_result_message_meta,
)
from src.utils import (
    robust_delete_message,
    robust_edit_text,
    robust_send_photo,
    robust_send_message,
    robust_send_video,
)
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)


class TelegramMessageAdapter:
    def __init__(self, bot, chat_id, message_id):
        self.bot = bot
        self.chat_id = chat_id
        self.message_id = message_id

    async def edit_text(self, text, parse_mode=None, reply_markup=None):
        try:
            await self.bot.edit_message_text(
                chat_id=self.chat_id,
                message_id=self.message_id,
                text=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
            )
        except Exception as exc:
            logger.debug("TelegramMessageAdapter edit_text failed: %s", exc)

    async def delete(self):
        try:
            await self.bot.delete_message(
                chat_id=self.chat_id,
                message_id=self.message_id,
            )
        except Exception as exc:
            logger.debug("TelegramMessageAdapter delete failed: %s", exc)


class TelegramBotContextAdapter:
    def __init__(self, application):
        self.bot = application.bot
        self.bot_data = getattr(application, "bot_data", {})


def _translate(lang: str, key: str, **kwargs) -> str:
    return get_text(key, lang or "zh", **kwargs)


def build_cancel_task_markup(
    task_id: str | None,
    *,
    lang: str = "zh",
) -> InlineKeyboardMarkup | None:
    if not task_id:
        return None
    return InlineKeyboardMarkup(
        [[
            InlineKeyboardButton(
                _translate(lang, "task.status_cancel_button"),
                callback_data=f"cancel_task_{task_id}",
            )
        ]]
    )


async def get_or_send_status_message(context, chat_id, status_msg_id, text):
    if status_msg_id:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_msg_id,
                text=text,
            )
            return TelegramMessageAdapter(context.bot, chat_id, status_msg_id)
        except Exception:
            pass
    return await robust_send_message(context.bot, chat_id, text)


async def send_result_media(
    *,
    context,
    chat_id,
    media_bytes,
    is_video,
    caption,
    task_type,
    task_id,
    allow_contribute,
    reply_markup,
    prompt,
    lang: str = "zh",
):
    final_markup = build_result_reply_markup(
        task_type=task_type,
        task_id=task_id,
        allow_contribute=allow_contribute,
        reply_markup=reply_markup,
    )
    sender = robust_send_video if is_video else robust_send_photo
    media_key = "video" if is_video else "photo"
    default_caption = _translate(
        lang,
        "task.status_completion_video" if is_video else "task.status_completion_image",
    )
    send_kwargs = {
        media_key: media_bytes,
        "caption": caption or default_caption,
        "reply_markup": final_markup,
    }
    sent_msg = await sender(context.bot, chat_id, **send_kwargs)
    record_result_message_meta(context, sent_msg, task_type, prompt, task_id)
    return sent_msg


async def cleanup_completion_status_message(*, status_msg, delete_status, send_result):
    if not (delete_status and send_result and status_msg):
        return
    try:
        await robust_delete_message(status_msg)
    except Exception as exc:
        logger.debug("Cleanup completion status failed: %s", exc)


def _translate_dynamic_name(lang: str, *, prefix: str, raw_value: str | None) -> str:
    if not raw_value:
        return ""
    translated = get_text(f"{prefix}.{raw_value}", lang)
    if translated != f"{prefix}.{raw_value}":
        return translated
    return raw_value


def build_vip_suffix(identity_str=None, user_group=None, *, lang: str = "zh"):
    privileges = []
    if identity_str and identity_str not in [
        "外门弟子",
        "凡人",
        "练气期",
        "筑基期",
        "金丹期",
        "元婴期",
        "default",
    ]:
        privileges.append(
            _translate_dynamic_name(lang, prefix="identity", raw_value=identity_str)
        )
    if user_group and user_group in ["元婴期", "金丹期", "筑基期"]:
        privileges.append(_translate_dynamic_name(lang, prefix="group", raw_value=user_group))
    if not privileges:
        return ""
    return get_text("task.status_vip_suffix", lang, privileges=" + ".join(privileges))


async def monitor_task_progress(
    *,
    task_id,
    status_msg,
    is_video,
    monitor_func,
    identity_str=None,
    user_group=None,
    lang: str = "zh",
    on_cancelled: Callable[[], Awaitable[None] | None] | None = None,
    edit_status_text_func=None,
):
    edit_status_text_func = edit_status_text_func or robust_edit_text
    last_progress = 0
    last_status = None
    last_queue_pos = None
    final_info = None
    cancel_markup = build_cancel_task_markup(task_id, lang=lang)

    async def update_status_message(text, *, show_cancel_button=False, **kwargs):
        if not status_msg:
            return False
        try:
            kwargs["reply_markup"] = cancel_markup if show_cancel_button else None
            await edit_status_text_func(status_msg, text, **kwargs)
            return True
        except Exception as exc:
            logger.warning("Failed to update status message for task %s: %s", task_id, exc)
            return False

    vip_suffix = build_vip_suffix(identity_str=identity_str, user_group=user_group, lang=lang)

    async for info in monitor_func(task_id, is_video=is_video):
        status = info.get("status")
        progress = info.get("progress", 0)

        if is_backend_success_status(status):
            final_info = info
            if not is_video and last_progress != 100:
                await update_status_message(build_done_progress_text(lang=lang))
            break

        if is_backend_cancelled_status(status):
            logger.warning("Task %s was cancelled.", task_id)
            if on_cancelled is not None:
                maybe_awaitable = on_cancelled()
                if maybe_awaitable is not None:
                    await maybe_awaitable
            return None

        if is_backend_failed_status(status) or status == "failed":
            raise RuntimeError(info.get("error", "Unknown error"))

        if status == "pending":
            queue_pos = normalize_pending_queue_position(info)

            if queue_pos is not None:
                if queue_pos != last_queue_pos or last_status != "pending":
                    if await update_status_message(
                        build_pending_status_text(
                            info=info,
                            vip_suffix=vip_suffix,
                            lang=lang,
                        ),
                        show_cancel_button=True,
                        parse_mode="Markdown",
                    ):
                        last_queue_pos = queue_pos
                        last_status = "pending"
            else:
                if last_status != "pending":
                    if await update_status_message(
                        build_pending_status_text(
                            info=info,
                            vip_suffix=vip_suffix,
                            lang=lang,
                        ),
                        show_cancel_button=True,
                        parse_mode="Markdown",
                    ):
                        last_status = "pending"
            continue

        if progress != last_progress or last_status == "pending":
            text = build_running_status_text(
                is_video=is_video,
                progress=progress,
                lang=lang,
            )
            if await update_status_message(text):
                last_progress = progress
                last_status = status

    return final_info
