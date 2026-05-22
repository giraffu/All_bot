import os
import time
import uuid

from telegram import Update

from config import MINIO_TEMPLATE_BUCKET
from src.constants import MODE_NONE, MODE_TEMPLATE_CONTRIBUTE, TEMP_TEMPLATE_DIR
from src.services.permission_service import permission_service
from src.services.storage import storage
from src.utils import robust_reply_text


async def handle_media_message(
    update: Update,
    context,
    *,
    unsupported_message: str | None = None,
    on_template_contribution,
    on_photo_idle,
):
    mode = context.user_data.get("mode", MODE_NONE)
    if mode == MODE_TEMPLATE_CONTRIBUTE:
        return await on_template_contribution(update, context)
    if unsupported_message:
        await robust_reply_text(update.message, unsupported_message)
        return None
    return await on_photo_idle(update, context)


async def handle_media_entry(
    update: Update,
    context,
    *,
    unsupported_message: str | None = None,
    is_mentioned,
    ensure_access_and_reward,
    on_template_contribution,
    on_photo_idle,
    handle_media_message_fn=None,
):
    if handle_media_message_fn is None:
        handle_media_message_fn = handle_media_message
    if not is_mentioned(update, context):
        return None
    if not await ensure_access_and_reward(update, context):
        return None
    return await handle_media_message_fn(
        update,
        context,
        unsupported_message=unsupported_message,
        on_template_contribution=on_template_contribution,
        on_photo_idle=on_photo_idle,
    )


async def handle_photo_idle(update: Update, context):
    now = time.time()
    last_reminder = context.user_data.get("last_reminder_time", 0)
    if now - last_reminder < 3.0:
        return None

    from src.i18n.keyboards import get_main_menu_keyboard

    reply_markup = get_main_menu_keyboard(context.lang)
    await robust_reply_text(
        update.message,
        "⚠️ **请先选择功能模式**\n\n点击下方菜单选择您想要的功能 👇",
        reply_markup=reply_markup,
        parse_mode="Markdown",
    )
    context.user_data["last_reminder_time"] = now
    return None


def resolve_template_upload_meta(message) -> tuple[str | None, str, str]:
    if message.photo:
        return message.photo[-1].file_id, ".png", "图片"
    if message.video:
        file_ext = os.path.splitext(message.video.file_name or "video.mp4")[1] or ".mp4"
        return message.video.file_id, file_ext, "视频"
    if message.document:
        file_ext = os.path.splitext(message.document.file_name or "file")[1]
        return message.document.file_id, file_ext, "文件"
    return None, ".png", "图片"


def resolve_template_db_file_type(message) -> str:
    if message.video:
        return "video"
    if message.document:
        return "document"
    return "photo"


async def handle_template_contribution(update: Update, context, logger):
    message = update.message
    user = update.effective_user
    username = user.username

    file_id, file_ext, file_type_name = resolve_template_upload_meta(message)
    if not file_id:
        return None

    try:
        file = await context.bot.get_file(file_id)
        local_filename = f"{user.id}_{uuid.uuid4().hex}{file_ext}"
        local_path = os.path.join(TEMP_TEMPLATE_DIR, local_filename)
        await file.download_to_drive(local_path)

        minio_object_name = f"temps/{local_filename}"
        storage.upload_file(local_path, minio_object_name, bucket=MINIO_TEMPLATE_BUCKET)

        file_type_db = resolve_template_db_file_type(message)
        await permission_service.record_contribution(user.id, local_path, file_type_db)

        context.user_data["contributed_count"] = context.user_data.get(
            "contributed_count", 0
        ) + 1
        count = context.user_data["contributed_count"]
        await robust_reply_text(
            message, f"✅ 已经收到 {count} 张图片/视频，待审核收入模板库。"
        )

        logger.info(
            "[Template Contribution] User %s(%s) saved %s: %s (Recorded in DB)",
            user.id,
            username,
            file_type_name,
            local_path,
        )
        return None
    except Exception as exc:
        logger.error("Error saving template contribution: %s", exc, exc_info=True)
        await robust_reply_text(message, f"❌ 保存失败：{str(exc)}")
        return None
