import os
import logging
import asyncio
import uuid
import random
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
from src.handlers.conversation_states import QuickImageState
from src.services.permission_service import permission_service
from src.services.task_service import TaskService
from src.utils import robust_reply_text, robust_edit_text, load_prompts, create_background_task
from src.constants import TASK_COSTS, MODE_UNDRESS, MODE_MASTURBATION, MODE_RANDOM_FACESWAP
from config import ENABLE_PUBLIC_SHARE

logger = logging.getLogger("fsm.quick_image")

# Map button text to mode
QUICK_MODES = {
    "💃 快速脱衣": MODE_UNDRESS,
    "🥵 快速自慰": MODE_MASTURBATION,
    "🎭 随机换脸": MODE_RANDOM_FACESWAP
}

def _cleanup_context(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    context.user_data.pop('in_conversation', None)
    fsm_data = context.user_data.pop('quick_image_data', {})
    image_path = fsm_data.get('image_path')
    if image_path and os.path.exists(image_path):
        try:
            os.remove(image_path)
        except Exception as e:
            logger.error(f"Failed to remove {image_path}: {e}")

async def start_quick_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point for 懒人P图 (单步图生图)"""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    logger.info(f"start_quick_image triggered by user {user_id}, text: {text.encode('utf-8')}")
    
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
        await robust_reply_text(update.message, msg)
        return ConversationHandler.END

    mode = None
    for key, val in QUICK_MODES.items():
        if key in text:
            mode = val
            break

    if not mode:
        return ConversationHandler.END

    cost = TASK_COSTS.get(mode, 2)

    context.user_data['in_conversation'] = f"QUICK_IMAGE_{mode}"
    context.user_data['quick_image_data'] = {
        'mode': mode,
        'cost': cost,
        'image_path': None
    }

    if mode == MODE_UNDRESS:
        msg = f"💃 **已切换到【快速脱衣】模式** (消耗 {cost} 灵石)。\n\n请发送一张包含人物的图片，我将自动处理。\n\n随时可以发送 /cancel 退出流程。"
    elif mode == MODE_MASTURBATION:
        msg = f"🥵 **已切换到【快速自慰】模式** (消耗 {cost} 灵石)。\n\n请发送一张包含人物的图片，我将自动处理。\n\n随时可以发送 /cancel 退出流程。"
    elif mode == MODE_RANDOM_FACESWAP:
        msg = f"🎭 **已切换到【随机换脸】模式** (消耗 {cost} 灵石)。\n\n请发送一张【正脸】图片，我将自动匹配模板处理。\n\n随时可以发送 /cancel 退出流程。"

    await robust_reply_text(update.message, msg, parse_mode="Markdown")
    return QuickImageState.WAIT_IMAGE

async def receive_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    message = update.message
    fsm_data = context.user_data['quick_image_data']
    mode = fsm_data['mode']
    cost = fsm_data['cost']

    if message.document:
        if not message.document.mime_type.startswith('image/'):
            await robust_reply_text(message, "❌ 格式错误！请发送图片。")
            return QuickImageState.WAIT_IMAGE
        file_id = message.document.file_id
    elif message.photo:
        file_id = message.photo[-1].file_id
    else:
        await robust_reply_text(message, "❌ 无法识别。请发送图片！")
        return QuickImageState.WAIT_IMAGE

    # Check Priority & Quota
    priority = await permission_service.calculate_user_priority(user_id)
    if priority <= 0:
        await robust_reply_text(message, "⚠️ 您的排队优先级已耗尽（或修为不足），今日已无法再凝聚灵力，请明日再来！")
        _cleanup_context(context, user_id)
        return ConversationHandler.END

    if not await permission_service.check_quota(update, context, cost=cost):
        _cleanup_context(context, user_id)
        return ConversationHandler.END

    try:
        new_file = await context.bot.get_file(file_id)
        os.makedirs("/tmp/bot_fsm_tmp", exist_ok=True)
        local_path = f"/tmp/bot_fsm_tmp/{uuid.uuid4()}_quick.png"
        await new_file.download_to_drive(local_path)
        fsm_data['image_path'] = local_path
    except Exception as e:
        
        logger.error(f"Error downloading image for FSM user {user_id}: {e}")
        await robust_reply_text(message, "❌ 下载图片失败，请重试或发送 /cancel 退出。")
        return QuickImageState.WAIT_IMAGE

    image_path = fsm_data.pop('image_path', None)
    if not image_path:
        return ConversationHandler.END # Prevent double submit

    await robust_reply_text(message, f"🚀 正在提交生成任务，预计消耗 {cost} 灵石，请耐心等待...")

    prompts_config = load_prompts()
    
    if mode == MODE_RANDOM_FACESWAP:
        from config import MINIO_TEMPLATE_BUCKET
        from src.services.storage import storage
        try:
            template_files = storage.list_objects("quick_face/", bucket=MINIO_TEMPLATE_BUCKET)
            template_files = [f for f in template_files if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))]
            if not template_files:
                await robust_reply_text(message, "❌ 系统错误：未找到身体模板。请联系管理员添加图片。")
                _cleanup_context(context, user_id)
                return ConversationHandler.END
            
            random_template = random.choice(template_files)
            template_path = f"template:{random_template}"
            prompt = prompts_config.get("face_swap", "face swap")
            swapped_images = [template_path, image_path]
            
            # Setup "Again" keyboard
            keyboard = [
                [InlineKeyboardButton("🔄 再来一张", callback_data="random_faceswap_again")],
                [
                    InlineKeyboardButton("👍", callback_data="rate_like"),
                    InlineKeyboardButton("👎", callback_data="rate_dislike")
                ]
            ]
            if ENABLE_PUBLIC_SHARE:
                keyboard[0].insert(0, InlineKeyboardButton("🌐 公开", callback_data="public_share_request"))
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Save face image path globally for "Again" button (outside FSM)
            context.user_data['last_face_image'] = image_path
            
            create_background_task(
                context,
                TaskService.process_generation_task(
                    context, message.chat_id, user_id, 
                    update.effective_user.username or update.effective_user.full_name, 
                    prompt, swapped_images, task_type="face_swap",
                    reply_markup=reply_markup,
                    cleanup=False # Kept for "Again"
                )
            )
        except Exception as e:
            logger.error(f"Error in random faceswap FSM: {e}", exc_info=True)
            await robust_reply_text(message, f"❌ 系统错误：{str(e)}")
            
    else:
        # Undress or Masturbation
        prompt = prompts_config.get(mode, mode)
        create_background_task(
            context,
            TaskService.process_generation_task(
                context, message.chat_id, user_id,
                update.effective_user.username or update.effective_user.full_name,
                prompt, [image_path], task_type=mode, cleanup=True
            )
        )

    _cleanup_context(context, user_id)
    return ConversationHandler.END

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    msg = "🚫 流程已取消。已清空历史上传内容。"
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
    if text and re.match(r'^(🖼️ 懒人P图|🎬 懒人动图|🔙 返回主菜单|🛌 动图传教士|🎬 动图后入|🎬 口交黑人|🎬 脱衣吐舌|🎬 特写口交|🎨 自由P图|🌟 幻想换脸|💃 快速脱衣|🎭 快速换脸|🥵 快速自慰|🎭 随机换脸|🎬 视频换脸|🎬 自定义视频|🎬 自定义图生视频|📅 每日签到|签到|/checkin|🤝 分享赚灵石|⏳ 排队状态|排队|/queue|💰 个人中心|👤 个人中心|💎 充值灵石|/start)$', text):
        user_id = update.effective_user.id if update.effective_user else "Unknown"
        _cleanup_context(context, user_id)
        await robust_reply_text(update.message, "🔄 已为您退出当前输入步骤（后台正在生成的任务不受影响）。\n👉 **请再次点击刚才的按钮**，即可开始新任务！")
        return ConversationHandler.END

    await robust_reply_text(update.message, "⚠️ 当前处于交互流程中。请按提示操作，或发送 /cancel 取消本次操作。")
    return None

def get_quick_image_fsm_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r'.*(快速脱衣|快速自慰|随机换脸).*'), start_quick_image)
        ],
        states={
            QuickImageState.WAIT_IMAGE: [
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, receive_image),
                MessageHandler(filters.TEXT & ~filters.COMMAND, unexpected_input)
            ],
            ConversationHandler.TIMEOUT: [
                MessageHandler(filters.ALL, timeout_conversation)
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel_conversation)],
        conversation_timeout=300,
        name="quick_image_fsm",
        persistent=False
    )
