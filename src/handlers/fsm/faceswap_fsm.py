from src.handlers.prompt_router import is_global_menu_command
import os
import logging
import asyncio
import uuid
import re
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters
)
from src.handlers.conversation_states import FaceSwapState
from src.services.permission_service import permission_service
from src.services.task_service import TaskService
from src.utils import robust_reply_text, robust_edit_text, load_prompts, create_background_task
from src.constants import TASK_COSTS, MODE_FACESWAP_STEP1

logger = logging.getLogger("fsm.faceswap")

def _cleanup_context(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    context.user_data.pop('in_conversation', None)
    pending_files = context.user_data.pop('faceswap_data', {})
    for key in ['face_image_path', 'body_image_path']:
        path = pending_files.get(key)
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except Exception as e:
                logger.error(f"Failed to remove {path}: {e}")

async def start_faceswap(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point for Two-person Face Swap (快速换脸)."""
    query = update.callback_query
    if query:
        try:
            await query.answer(text="⏳ 任务初始化中...", cache_time=2)
        except Exception:
            pass
    user_id = update.effective_user.id
    logger.info(f"User {user_id} triggered start_faceswap with text: {update.message.text if update.message else 'None'}")
    
    from src.utils import is_maintenance_mode
    if is_maintenance_mode():
        msg = "⚠️ 🛠️ **系统正在维护升级中**\n\n为了提供更好的服务，当前生图/生视频节点正在维护，暂不接受新任务。\n\n您的灵石和会员权益不受影响，请稍后再试！"
        if update.callback_query:
            await robust_edit_text(update.callback_query.message, msg, parse_mode="Markdown")
        else:
            await robust_reply_text(update.message, msg, parse_mode="Markdown")
        return ConversationHandler.END

    if context.user_data.get('in_conversation'):
        msg = "⚠️ 您当前有未完成的交互流程，请先发送 /cancel 退出当前流程后再试。"
        if update.callback_query:
            await robust_edit_text(update.callback_query.message, msg)
        else:
            await robust_reply_text(update.message, msg)
        return ConversationHandler.END

    context.user_data['in_conversation'] = "FACESWAP"
    context.user_data['faceswap_data'] = {}

    msg = "🎭 **欢迎使用双人换脸功能！**\n\n【第一步】请发送一张包含**清晰正脸**的图片（作为人脸提供者）。\n\n随时可以发送 /cancel 退出流程。"
    if update.callback_query:
        await robust_edit_text(update.callback_query.message, msg, parse_mode="Markdown")
    else:
        await robust_reply_text(update.message, msg, parse_mode="Markdown")

    return FaceSwapState.WAIT_FACE_IMAGE

async def receive_face_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    message = update.message

    if message.document:
        if not message.document.mime_type.startswith('image/'):
            await robust_reply_text(message, "❌ 格式错误！请发送图片。")
            return FaceSwapState.WAIT_FACE_IMAGE
        file_id = message.document.file_id
    elif message.photo:
        file_id = message.photo[-1].file_id
    else:
        await robust_reply_text(message, "❌ 无法识别。请发送图片！")
        return FaceSwapState.WAIT_FACE_IMAGE

    try:
        new_file = await context.bot.get_file(file_id)
        os.makedirs("/tmp/bot_fsm_tmp", exist_ok=True)
        local_path = f"/tmp/bot_fsm_tmp/{uuid.uuid4()}_face.png"
        await new_file.download_to_drive(local_path)
        context.user_data['faceswap_data']['face_image_path'] = local_path
    except Exception as e:
        
        logger.error(f"Error downloading face image for FSM user {user_id}: {e}")
        await robust_reply_text(message, "❌ 下载图片失败，请重试或发送 /cancel 退出。")
        return FaceSwapState.WAIT_FACE_IMAGE

    await robust_reply_text(
        message,
        "✅ **人脸图片已收到！**\n\n【第二步】请发送一张**目标身体图片**（即你想把脸换到哪张图上）。\n\n随时可以发送 /cancel 退出流程。",
        parse_mode="Markdown"
    )
    return FaceSwapState.WAIT_BODY_IMAGE

async def receive_body_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    message = update.message

    if message.document:
        if not message.document.mime_type.startswith('image/'):
            await robust_reply_text(message, "❌ 格式错误！请发送图片。")
            return FaceSwapState.WAIT_BODY_IMAGE
        file_id = message.document.file_id
    elif message.photo:
        file_id = message.photo[-1].file_id
    else:
        await robust_reply_text(message, "❌ 无法识别。请发送图片！")
        return FaceSwapState.WAIT_BODY_IMAGE

    cost = TASK_COSTS.get(MODE_FACESWAP_STEP1, 1)
    if not update.effective_user: return ConversationHandler.END
    user = update.effective_user
    if not await permission_service.check_quota(user.id, user.username, user.full_name, context.bot, update.effective_chat.id, cost=cost):
        _cleanup_context(context, user_id)
        return ConversationHandler.END

    try:
        new_file = await context.bot.get_file(file_id)
        local_path = f"/tmp/bot_fsm_tmp/{uuid.uuid4()}_body.png"
        await new_file.download_to_drive(local_path)
        context.user_data['faceswap_data']['body_image_path'] = local_path
    except Exception as e:
        
        logger.error(f"Error downloading body image for FSM user {user_id}: {e}")
        await robust_reply_text(message, "❌ 下载图片失败，请重试或发送 /cancel 退出。")
        return FaceSwapState.WAIT_BODY_IMAGE

    face_path = context.user_data['faceswap_data'].pop('face_image_path', None)
    body_path = context.user_data['faceswap_data'].pop('body_image_path', None)

    if not face_path or not body_path:
        return ConversationHandler.END # Prevent double submit

    await robust_reply_text(message, f"🚀 正在提交双人换脸任务，预计消耗 {cost} 灵石，请耐心等待...")

    prompts_config = load_prompts()
    prompt = prompts_config.get("face_swap", "face swap")
    swapped_images = [body_path, face_path]  # Body first, Face second

    create_background_task(
        context,
        TaskService.process_generation_task(
            context, message.chat_id, user_id,
            update.effective_user.username or update.effective_user.full_name,
            prompt, swapped_images, task_type="face_swap", cleanup=True
        )
    )

    _cleanup_context(context, user_id)
    return ConversationHandler.END

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    msg = "🚫 流程已取消。已清空历史上传内容。"
    if update.callback_query:
        await robust_edit_text(update.callback_query.message, msg)
    else:
        await robust_reply_text(update.message, msg)
    _cleanup_context(context, user_id)
    return ConversationHandler.END

async def timeout_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id if update.effective_user else "Unknown"
    if update and update.message:
        await robust_reply_text(update.message, "⏰ 操作超时，为节省系统资源，本次流程已自动取消。您可以随时重新开始。")
    _cleanup_context(context, user_id)
    return ConversationHandler.END

async def unexpected_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text if update.message else ""
    if text and is_global_menu_command(text):
        user_id = update.effective_user.id if update.effective_user else "Unknown"
        _cleanup_context(context, user_id)
        await robust_reply_text(update.message, "🔄 已为您退出当前输入步骤（后台正在生成的任务不受影响）。\n👉 **请再次点击刚才的按钮**，即可开始新任务！")
        return ConversationHandler.END

    await robust_reply_text(update.message, "⚠️ 当前处于交互流程中。请按提示操作，或发送 /cancel 取消本次操作。")
    return None

def get_faceswap_fsm_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler('faceswap', start_faceswap),
            MessageHandler(filters.Regex(r'.*快速换脸.*'), start_faceswap),
            CallbackQueryHandler(start_faceswap, pattern='^fsm_start_faceswap$')
        ],
        states={
            FaceSwapState.WAIT_FACE_IMAGE: [
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, receive_face_image),
                MessageHandler(filters.TEXT & ~filters.COMMAND, unexpected_input)
            ],
            FaceSwapState.WAIT_BODY_IMAGE: [
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, receive_body_image),
                MessageHandler(filters.TEXT & ~filters.COMMAND, unexpected_input)
            ],
            ConversationHandler.TIMEOUT: [
                MessageHandler(filters.ALL, timeout_conversation)
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel_conversation)],
        conversation_timeout=300,
        name="faceswap_fsm",
        persistent=False
    )
