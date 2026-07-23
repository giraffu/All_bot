import asyncio
import logging
import os
import signal
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from src.database.core import AsyncSessionLocal, init_db
from src.services.storage import storage
from src.services.support_ticket_service import finalize_ticket_submission
from src.services.telegram_runtime_bootstrap import (
    build_telegram_bot_base_url,
    build_telegram_httpx_request,
    resolve_telegram_file_base_url,
)
from support_bot.attachment_service import download_attachment_bytes

logger = logging.getLogger("support_bot")
WELCOME = "欢迎联系 QQCC 客服 👋\n\n请选择下方服务类型，我们会按类别安排处理：\n💳 充值问题｜充值未到账、套餐或支付疑问\n🛠 Bug反馈｜功能异常、报错或无法使用\n💡 意见反馈｜功能建议与体验意见\n🤝 商业合作｜渠道、推广、内容或其他合作\n\n选择分类后，可连续发送问题描述、截图或文件。每次内容记录后，请点击“结束提交”完成工单；5 分钟没有继续发送时也会自动提交。也可以直接留言，系统会按“未分类”收集。\n\n充值未到账请附付款截图，并注明购买套餐、付款时间和付款方式；信息越完整，处理越快。\n\n请勿发送账号密码、验证码或 Bot Token 等敏感信息。"
KEYBOARD = ReplyKeyboardMarkup(
    [["充值问题", "Bug反馈"], ["意见反馈", "商业合作"]], resize_keyboard=True
)
CATEGORY_BY_TEXT = {
    "充值问题": "recharge",
    "Bug反馈": "bug",
    "意见反馈": "suggestion",
    "商业合作": "business",
}
CATEGORY_PROMPTS = {
    "recharge": "已选择【充值问题】💳\n请发送问题描述，并附上付款截图、购买套餐、付款时间和付款方式，以便我们尽快核对。",
    "bug": "已选择【Bug反馈】🛠\n请发送问题描述、操作步骤、预期结果和实际现象；如有报错截图或录屏，也请一并发送。",
    "suggestion": "已选择【意见反馈】💡\n请发送你的建议、使用场景或希望改进的体验，我们会认真评估。",
    "business": "已选择【商业合作】🤝\n请发送合作方向、项目或品牌简介、合作诉求及方便联系的方式，我们会尽快与你对接。",
}
MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024
SUBMISSION_TIMEOUT_SECONDS = 300
SUBMISSION_KEY = "support_submission"
FINISH_CALLBACK_PREFIX = "support_finish:"
TIMEOUT_JOB_PREFIX = "support_submission_timeout:"
RECORDED_MESSAGE = (
    "已记录这条内容。你可以继续发送文字、图片或文件；全部发送完毕后，请点击“结束提交”。"
)


async def start(update: Update, _context):
    await update.effective_message.reply_text(WELCOME, reply_markup=KEYBOARD)


async def _store_attachment(message, context):
    attachment = None
    if message.photo:
        attachment = message.photo[-1]
        filename, mime = f"photo-{attachment.file_unique_id}.jpg", "image/jpeg"
    elif message.document:
        attachment = message.document
        filename, mime = (
            attachment.file_name or f"document-{attachment.file_unique_id}",
            attachment.mime_type or "application/octet-stream",
        )
    if not attachment:
        return [], None
    if attachment.file_size and attachment.file_size > MAX_ATTACHMENT_BYTES:
        return [], "附件超过 20MB，请压缩后重新发送。"
    key = f"support/{message.from_user.id}/{message.message_id}/{Path(filename).name}"
    try:
        remote = await context.bot.get_file(attachment.file_id)
        data = await download_attachment_bytes(remote)
        if not storage.r2_client or not storage.r2_bucket:
            raise RuntimeError("R2 unavailable")
        await asyncio.to_thread(
            storage.r2_client.put_object,
            Bucket=storage.r2_bucket,
            Key=key,
            Body=bytes(data),
            ContentType=mime,
        )
        storage.mark_r2_object_exists(key)
        return (
            [
                {
                    "object_key": key,
                    "filename": filename,
                    "mime_type": mime,
                    "telegram_file_id": attachment.file_id,
                    "size_bytes": len(data),
                }
            ],
            None,
        )
    except Exception:
        logger.exception("support attachment upload failed")
        return [], "附件暂时保存失败，请稍后重新发送。"


def _message_created_at(message) -> datetime:
    created_at = getattr(message, "date", None)
    if created_at is None:
        return datetime.now()
    if created_at.tzinfo is not None:
        return created_at.astimezone().replace(tzinfo=None)
    return created_at


def _new_submission(message, category: str) -> dict:
    user = message.from_user
    return {
        "id": uuid4().hex,
        "category": category,
        "messages": [],
        "user": {
            "id": user.id,
            "username": getattr(user, "username", None),
            "full_name": getattr(user, "full_name", None),
            "language_code": getattr(user, "language_code", None),
        },
        "chat_id": message.chat_id,
        "finalizing": False,
    }


def _timeout_job_name(user_id: int) -> str:
    return f"{TIMEOUT_JOB_PREFIX}{user_id}"


def _cancel_timeout(context, user_id: int) -> None:
    if not context.job_queue:
        return
    for job in context.job_queue.get_jobs_by_name(_timeout_job_name(user_id)):
        job.schedule_removal()


def _schedule_timeout(context, draft: dict) -> None:
    user_id = int(draft["user"]["id"])
    _cancel_timeout(context, user_id)
    if not context.job_queue:
        logger.warning("support submission timeout unavailable: JobQueue is disabled")
        return
    context.job_queue.run_once(
        _timeout_submission,
        SUBMISSION_TIMEOUT_SECONDS,
        data={"submission_id": draft["id"]},
        chat_id=int(draft["chat_id"]),
        user_id=user_id,
        name=_timeout_job_name(user_id),
    )


def _finish_markup(submission_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "结束提交",
                    callback_data=f"{FINISH_CALLBACK_PREFIX}{submission_id}",
                )
            ]
        ]
    )


def _clear_active_submission(context, submission_id: str | None = None) -> None:
    draft = context.user_data.get(SUBMISSION_KEY)
    if not draft or (submission_id is not None and draft["id"] != submission_id):
        return
    _cancel_timeout(context, int(draft["user"]["id"]))
    context.user_data.pop(SUBMISSION_KEY, None)


async def _persist_active_submission(context):
    draft = context.user_data.get(SUBMISSION_KEY)
    if not draft or not draft["messages"]:
        return None
    if draft.get("finalizing"):
        raise RuntimeError("support submission is already being finalized")
    draft["finalizing"] = True
    try:
        user = draft["user"]
        async with AsyncSessionLocal() as session:
            ticket = await finalize_ticket_submission(
                session,
                telegram_user_id=int(user["id"]),
                username=user.get("username"),
                full_name=user.get("full_name"),
                language_code=user.get("language_code"),
                category=draft["category"],
                messages=list(draft["messages"]),
            )
    except Exception:
        draft["finalizing"] = False
        raise
    _clear_active_submission(context, draft["id"])
    return ticket


async def _start_category_submission(message, context, category: str) -> None:
    current = context.user_data.get(SUBMISSION_KEY)
    if current and current.get("finalizing"):
        await message.reply_text("上一条工单正在提交，请稍候再选择新分类。")
        return
    if current and current["category"] == category:
        _schedule_timeout(context, current)
        await message.reply_text(
            f"{CATEGORY_PROMPTS[category]}\n\n当前提交仍在进行，请继续发送内容。",
            reply_markup=KEYBOARD,
        )
        return

    if current:
        if current["messages"]:
            try:
                ticket = await _persist_active_submission(context)
            except Exception:
                logger.exception("support submission auto-finalize failed")
                await message.reply_text(
                    "上一条工单暂时提交失败，内容仍已保留。请稍后点击“结束提交”重试。",
                    reply_markup=_finish_markup(current["id"]),
                )
                return
            await message.reply_text(
                f"上一条工单 #{ticket.id} 已自动结束并提交。",
                reply_markup=KEYBOARD,
            )
        else:
            _clear_active_submission(context, current["id"])

    draft = _new_submission(message, category)
    context.user_data[SUBMISSION_KEY] = draft
    _schedule_timeout(context, draft)
    await message.reply_text(
        f"{CATEGORY_PROMPTS[category]}\n\n本次工单正在收集中。",
        reply_markup=KEYBOARD,
    )


async def receive(update: Update, context):
    message = update.effective_message
    body = (message.text or message.caption or "").strip() or None
    category = CATEGORY_BY_TEXT.get(body or "", "uncategorized")
    if category != "uncategorized" and not message.photo and not message.document:
        await _start_category_submission(message, context, category)
        return

    draft = context.user_data.get(SUBMISSION_KEY)
    if draft and draft.get("finalizing"):
        await message.reply_text("上一条工单正在提交，请稍候后重新发送这条内容。")
        return
    if draft is None:
        draft = _new_submission(message, "uncategorized")
        context.user_data[SUBMISSION_KEY] = draft

    attachments, attachment_error = await _store_attachment(message, context)
    if attachment_error:
        _schedule_timeout(context, draft)
        reply_markup = _finish_markup(draft["id"]) if draft["messages"] else KEYBOARD
        await message.reply_text(attachment_error, reply_markup=reply_markup)
        return

    if not body and not attachments:
        await message.reply_text("请发送文字、图片或文件。", reply_markup=KEYBOARD)
        return

    if not any(
        item["telegram_message_id"] == message.message_id for item in draft["messages"]
    ):
        draft["messages"].append(
            {
                "telegram_message_id": message.message_id,
                "body": body,
                "attachments": attachments,
                "created_at": _message_created_at(message),
            }
        )
    _schedule_timeout(context, draft)
    await message.reply_text(
        RECORDED_MESSAGE,
        reply_markup=_finish_markup(draft["id"]),
    )


async def finish_submission(update: Update, context):
    query = update.callback_query
    await query.answer()
    submission_id = (query.data or "")[len(FINISH_CALLBACK_PREFIX) :]
    draft = context.user_data.get(SUBMISSION_KEY)
    if not draft or draft["id"] != submission_id:
        await query.message.reply_text(
            "该次工单提交已结束。",
            reply_markup=KEYBOARD,
        )
        return
    if not draft["messages"]:
        _clear_active_submission(context, draft["id"])
        await query.message.reply_text(
            "本次没有可提交的内容，已结束。",
            reply_markup=KEYBOARD,
        )
        return
    if draft.get("finalizing"):
        await query.message.reply_text("工单正在提交，请稍候。")
        return
    try:
        ticket = await _persist_active_submission(context)
    except Exception:
        logger.exception("support submission finalize failed")
        await query.message.reply_text(
            "工单暂时提交失败，内容仍已保留，请稍后重试。",
            reply_markup=_finish_markup(draft["id"]),
        )
        return
    await query.message.reply_text(
        f"工单 #{ticket.id} 已提交，客服会尽快回复。",
        reply_markup=KEYBOARD,
    )


async def _timeout_submission(context):
    expected_id = (context.job.data or {}).get("submission_id")
    draft = context.user_data.get(SUBMISSION_KEY)
    if not draft or draft["id"] != expected_id:
        return
    if draft.get("finalizing"):
        _schedule_timeout(context, draft)
        return
    if not draft["messages"]:
        _clear_active_submission(context, draft["id"])
        await context.bot.send_message(
            chat_id=draft["chat_id"],
            text="本次没有收到工单内容，提交已自动结束。",
            reply_markup=KEYBOARD,
        )
        return
    try:
        ticket = await _persist_active_submission(context)
    except Exception:
        logger.exception("support submission timeout finalize failed")
        _schedule_timeout(context, draft)
        await context.bot.send_message(
            chat_id=draft["chat_id"],
            text="工单自动提交暂时失败，内容仍已保留。你可以点击“结束提交”重试。",
            reply_markup=_finish_markup(draft["id"]),
        )
        return
    await context.bot.send_message(
        chat_id=draft["chat_id"],
        text=f"5 分钟内没有收到新内容，工单 #{ticket.id} 已自动结束并提交。",
        reply_markup=KEYBOARD,
    )


def main():
    token = os.getenv("SUPPORT_BOT_TOKEN")
    if not token:
        raise SystemExit("SUPPORT_BOT_TOKEN is required")
    app = (
        ApplicationBuilder()
        .token(token)
        .base_url(build_telegram_bot_base_url())
        .base_file_url(resolve_telegram_file_base_url())
        .request(build_telegram_httpx_request())
        .get_updates_request(build_telegram_httpx_request())
        .post_init(lambda _: init_db())
        .build()
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(
        CallbackQueryHandler(
            finish_submission,
            pattern=rf"^{FINISH_CALLBACK_PREFIX}",
        )
    )
    app.add_handler(
        MessageHandler(
            (filters.TEXT & ~filters.COMMAND) | filters.PHOTO | filters.Document.ALL,
            receive,
        )
    )
    app.run_polling(poll_interval=2, stop_signals=(signal.SIGINT, signal.SIGTERM))


if __name__ == "__main__":
    main()
