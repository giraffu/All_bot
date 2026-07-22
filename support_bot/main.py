import asyncio
import logging
import os
import signal
from pathlib import Path

from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

from src.database.core import AsyncSessionLocal, init_db
from src.services.storage import storage
from src.services.support_ticket_service import add_user_message, select_ticket_category
from src.services.telegram_runtime_bootstrap import (
    build_telegram_bot_base_url,
    build_telegram_httpx_request,
    resolve_telegram_file_base_url,
)
from support_bot.attachment_service import download_attachment_bytes

logger = logging.getLogger("support_bot")
WELCOME = "欢迎联系 QQCC 客服 👋\n\n请选择下方服务类型，我们会按类别安排处理：\n💳 充值问题｜充值未到账、套餐或支付疑问\n🛠 Bug反馈｜功能异常、报错或无法使用\n💡 意见反馈｜功能建议与体验意见\n🤝 商业合作｜渠道、推广、内容或其他合作\n\n选择分类后，请继续发送问题描述、截图或文件。也可以直接留言，系统会按“未分类”记录。\n\n充值未到账请附付款截图，并注明购买套餐、付款时间和付款方式；信息越完整，处理越快。\n\n请勿发送账号密码、验证码或 Bot Token 等敏感信息。"
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


async def receive(update: Update, context):
    message = update.effective_message
    body = (message.text or message.caption or "").strip() or None
    category = CATEGORY_BY_TEXT.get(body or "", "uncategorized")
    if category != "uncategorized" and not message.photo and not message.document:
        async with AsyncSessionLocal() as session:
            ticket = await select_ticket_category(
                session,
                telegram_user=message.from_user,
                category=category,
            )
        await message.reply_text(
            f"{CATEGORY_PROMPTS[category]}\n\n工单 #{ticket.id} 已准备好，后续内容会自动归入该工单。",
            reply_markup=KEYBOARD,
        )
        return
    attachments, attachment_error = await _store_attachment(message, context)
    if attachment_error:
        body = "\n".join(value for value in (body, f"[{attachment_error}]") if value)
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
        "\n".join(
            value
            for value in (
                f"已记录您的反馈（工单 #{ticket.id}），客服会尽快回复。",
                attachment_error,
            )
            if value
        ),
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
        MessageHandler(
            (filters.TEXT & ~filters.COMMAND) | filters.PHOTO | filters.Document.ALL,
            receive,
        )
    )
    app.run_polling(poll_interval=2, stop_signals=(signal.SIGINT, signal.SIGTERM))


if __name__ == "__main__":
    main()
