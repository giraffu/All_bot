import logging
from collections.abc import Awaitable, Callable

from config import ENABLE_PUBLIC_SHARE
from src.constants import (
    MODE_CUSTOM_VIDEO,
    MODE_EDIT,
    MODE_FACESWAP_STEP1,
    MODE_IMAGE_TO_VIDEO,
    MODE_I2I_PRO,
    MODE_IMG2IMG_LORA,
    MODE_LTX_VIDEO,
    MODE_MASTURBATION,
    MODE_NAME_MAP,
    MODE_PENETRATION_STEP1,
    MODE_UNDRESS,
)
from src.i18n.translator import get_text
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


def build_result_reply_markup(task_type, task_id, allow_contribute, reply_markup):
    allowed_gallery_types = [
        MODE_I2I_PRO,
        MODE_EDIT,
        MODE_CUSTOM_VIDEO,
        MODE_IMAGE_TO_VIDEO,
        MODE_LTX_VIDEO,
        MODE_IMG2IMG_LORA,
    ]
    show_gallery_btn = task_type in allowed_gallery_types and allow_contribute

    keyboard = []
    if show_gallery_btn:
        keyboard.append(
            [
                InlineKeyboardButton(
                    "🚀 一键投稿至广场",
                    callback_data=f"submit_gallery_{task_id}",
                )
            ]
        )

    keyboard.append(
        [
            InlineKeyboardButton("👍", callback_data="rate_like"),
            InlineKeyboardButton("👎", callback_data="rate_dislike"),
        ]
    )

    if ENABLE_PUBLIC_SHARE:
        keyboard.insert(
            0,
            [InlineKeyboardButton("公开", callback_data="public_share_request")],
        )

    final_markup = reply_markup or InlineKeyboardMarkup(keyboard)
    if reply_markup and show_gallery_btn:
        has_gallery = any(
            btn.callback_data and btn.callback_data.startswith("submit_gallery_")
            for row in final_markup.inline_keyboard
            for btn in row
        )
        if not has_gallery:
            new_keyboard = [list(row) for row in final_markup.inline_keyboard]
            new_keyboard.insert(
                0,
                [
                    InlineKeyboardButton(
                        "🚀 一键投稿至广场",
                        callback_data=f"submit_gallery_{task_id}",
                    )
                ],
            )
            final_markup = InlineKeyboardMarkup(new_keyboard)

    return final_markup


def resolve_result_mode_name(task_type):
    mode_name = MODE_NAME_MAP.get(task_type, task_type)
    if task_type == "face_swap":
        return MODE_NAME_MAP.get(MODE_FACESWAP_STEP1)
    if task_type == "penetration":
        return MODE_NAME_MAP.get(MODE_PENETRATION_STEP1)
    if task_type == "undress":
        return MODE_NAME_MAP.get(MODE_UNDRESS)
    if task_type == "masturbation":
        return MODE_NAME_MAP.get(MODE_MASTURBATION)
    return mode_name


def record_result_message_meta(context, sent_msg, task_type, prompt, task_id):
    if not sent_msg:
        return
    context.bot_data[f"msg_meta_{sent_msg.message_id}"] = {
        "mode_name": resolve_result_mode_name(task_type),
        "prompt": prompt,
        "task_id": task_id,
    }


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
    cancel_markup = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton(
                _translate(lang, "task.status_cancel_button"),
                callback_data=f"cancel_task_{task_id}",
            )
        ]]
    )

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

        if status == "done":
            final_info = info
            if not is_video and last_progress != 100:
                await update_status_message(
                    _translate(lang, "task.status_generating_progress", progress=100)
                )
            break

        if status in ["error", "failed", "cancelled"]:
            if status == "cancelled":
                logger.warning("Task %s was cancelled.", task_id)
                if on_cancelled is not None:
                    maybe_awaitable = on_cancelled()
                    if maybe_awaitable is not None:
                        await maybe_awaitable
                return None
            raise RuntimeError(info.get("error", "Unknown error"))

        if status == "pending":
            raw_pos = info.get("queue_pos")
            queue_pos = None
            if raw_pos is not None:
                try:
                    queue_pos = int(raw_pos) + 1
                except (ValueError, TypeError):
                    queue_pos = raw_pos
            else:
                queue_pos = info.get("queue_remaining")

            if queue_pos is not None:
                if queue_pos != last_queue_pos or last_status != "pending":
                    if await update_status_message(
                        f"{_translate(lang, 'task.status_pending_position', queue_pos=queue_pos)}{vip_suffix}",
                        show_cancel_button=True,
                        parse_mode="Markdown",
                    ):
                        last_queue_pos = queue_pos
                        last_status = "pending"
            else:
                if last_status != "pending":
                    if await update_status_message(
                        f"{_translate(lang, 'task.status_pending')}{vip_suffix}",
                        show_cancel_button=True,
                        parse_mode="Markdown",
                    ):
                        last_status = "pending"
            continue

        if progress != last_progress or last_status == "pending":
            text = (
                _translate(lang, "task.status_generating_video")
                if is_video
                else _translate(lang, "task.status_generating_progress", progress=progress)
            )
            if await update_status_message(text):
                last_progress = progress
                last_status = status

    return final_info
