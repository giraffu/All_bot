import asyncio
import logging
import os
import signal
from pathlib import Path

from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

from src.database.core import AsyncSessionLocal, init_db
from src.services.storage import storage
from src.services.support_ticket_service import add_user_message
from src.services.telegram_runtime_bootstrap import (
    build_telegram_bot_base_url,
    build_telegram_httpx_request,
    resolve_telegram_file_base_url,
)

logger = logging.getLogger("support_bot")
WELCOME = "欢迎联系 QQCC 客服 👋\n\n请点击下方按钮选择反馈类型：充值问题、Bug 反馈或意见反馈。\n\n也可以直接发送文字、图片或文件，我们会将其记录为“未分类留言”并尽快处理。\n\n若遇到充值未到账，请附上付款截图，并注明购买的套餐与付款时间；信息越完整，处理越快。\n\n请勿发送账号密码、验证码或 Bot Token 等敏感信息。"
KEYBOARD = ReplyKeyboardMarkup(
    [["充值问题", "Bug反馈", "意见反馈"]], resize_keyboard=True
)
CATEGORY_BY_TEXT = {"充值问题": "recharge", "Bug反馈": "bug", "意见反馈": "suggestion"}


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
        return []
    key = f"support/{message.from_user.id}/{message.message_id}/{Path(filename).name}"
    try:
        remote = await context.bot.get_file(attachment.file_id)
        data = await remote.download_as_bytearray()
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
        return [
            {
                "object_key": key,
                "filename": filename,
                "mime_type": mime,
                "telegram_file_id": attachment.file_id,
            }
        ]
    except Exception:
        logger.exception("support attachment upload failed")
        return []


async def receive(update: Update, context):
    message = update.effective_message
    body = (message.text or message.caption or "").strip() or None
    category = CATEGORY_BY_TEXT.get(body or "", "uncategorized")
    if category != "uncategorized" and not message.photo and not message.document:
        body = None
    attachments = await _store_attachment(message, context)
    async with AsyncSessionLocal() as session:
        ticket = await add_user_message(
            session,
            telegram_user=message.from_user,
            telegram_message_id=message.message_id,
            body=body,
            attachments=attachments,
            category=category,
        )
    await message.reply_text(
        f"已记录您的反馈（工单 #{ticket.id}），客服会尽快回复。", reply_markup=KEYBOARD
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
        MessageHandler(
            (filters.TEXT & ~filters.COMMAND) | filters.PHOTO | filters.Document.ALL,
            receive,
        )
    )
    app.run_polling(poll_interval=2, stop_signals=(signal.SIGINT, signal.SIGTERM))


if __name__ == "__main__":
    main()
