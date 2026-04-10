import os
import logging
import asyncio
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters
)
from src.handlers.conversation_states import FaceVideoState
from src.services.permission_service import permission_service
from src.services.task_service import TaskService
from src.utils import robust_reply_text, robust_edit_text, create_background_task
from src.constants import RESOLUTION_COST

logger = logging.getLogger("fsm.face_video")

# --- Helpers ---
def _cleanup_context(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Clean up user data upon exit to prevent memory leaks and reset conversation locks."""
    # Remove conversation lock
    context.user_data.pop('in_conversation', None)
    
    # Clean up downloaded files to avoid disk leaks
    pending_files = context.user_data.pop('face_video_data', {})
    face_img = pending_files.get('face_image_path')
    video = pending_files.get('video_path')
    
    if face_img and os.path.exists(face_img):
        try:
            os.remove(face_img)
        except Exception as e:
            logger.error(f"Failed to remove {face_img}: {e}")
    if video and os.path.exists(video):
        try:
            os.remove(video)
        except Exception as e:
            logger.error(f"Failed to remove {video}: {e}")

# --- Entry Point ---
async def start_face_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point for Video Face Swap."""
    user_id = update.effective_user.id
    
    from src.utils import is_maintenance_mode
    if is_maintenance_mode():
        msg = "⚠️ 🛠️ **系统正在维护升级中**\n\n为了提供更好的服务，当前生图/生视频节点正在维护，暂不接受新任务。\n\n您的灵石和会员权益不受影响，请稍后再试！"
        if update.callback_query:
            await robust_edit_text(update.callback_query.message, msg, parse_mode="Markdown")
        else:
            await robust_reply_text(update.message, msg, parse_mode="Markdown")
        return ConversationHandler.END

    # 1. Concurrency Check (User Data Lock)
    if context.user_data.get('in_conversation'):
        msg = "⚠️ 您当前有未完成的交互流程，请先发送 /cancel 退出当前流程后再试。"
        if update.callback_query:
            await robust_edit_text(update.callback_query.message, msg)
        else:
            await robust_reply_text(update.message, msg)
        return ConversationHandler.END

    # 2. Lock the user context for this flow
    context.user_data['in_conversation'] = "FACE_VIDEO"
    # Initialize isolated data storage
    context.user_data['face_video_data'] = {}

    msg = "🎥 **欢迎使用视频换脸功能！**\n\n【第一步】请发送一张包含**清晰正脸**的图片（支持作为文件或图片发送）。\n\n随时可以发送 /cancel 退出流程。"
    if update.callback_query:
        await robust_edit_text(update.callback_query.message, msg, parse_mode="Markdown")
    else:
        await robust_reply_text(update.message, msg, parse_mode="Markdown")

    return FaceVideoState.WAIT_FACE_IMAGE

# --- State 1: Receive Face Image ---
async def receive_face_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """State 1: Handle uploaded face image."""
    user_id = update.effective_user.id
    message = update.message

    # Handle document vs photo
    if message.document:
        if not message.document.mime_type.startswith('image/'):
            await robust_reply_text(message, "❌ 格式错误！请发送一张图片文件 (PNG/JPG)，而不是其他文档。")
            return FaceVideoState.WAIT_FACE_IMAGE
        file_id = message.document.file_id
    elif message.photo:
        file_id = message.photo[-1].file_id
    else:
        await robust_reply_text(message, "❌ 无法识别。请发送图片！")
        return FaceVideoState.WAIT_FACE_IMAGE

    # Download file
    try:
        new_file = await context.bot.get_file(file_id)
        # Using a fixed tmp dir; ensure it exists
        os.makedirs("/tmp/bot_fsm_tmp", exist_ok=True)
        local_path = f"/tmp/bot_fsm_tmp/{file_id}_face.png"
        await new_file.download_to_drive(local_path)
        
        # Save to FSM isolated data
        context.user_data['face_video_data']['face_image_path'] = local_path
    except Exception as e:
        logger.error(f"Error downloading face image for FSM user {user_id}: {e}")
        await robust_reply_text(message, "❌ 下载图片失败，请重试或发送 /cancel 退出。")
        return FaceVideoState.WAIT_FACE_IMAGE

    await robust_reply_text(
        message,
        "✅ **人脸图片已收到！**\n\n【第二步】请发送一个您想替换人脸的**目标视频** (不超过 20MB)。\n\n随时可以发送 /cancel 退出流程。",
        parse_mode="Markdown"
    )
    return FaceVideoState.WAIT_VIDEO

# --- State 2: Receive Video ---
async def receive_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """State 2: Handle uploaded video and prompt for resolution."""
    user_id = update.effective_user.id
    message = update.message

    if message.document:
        if not message.document.mime_type.startswith('video/'):
            await robust_reply_text(message, "❌ 格式错误！请发送视频文件 (.mp4, .mov, .avi)。")
            return FaceVideoState.WAIT_VIDEO
        file_id = message.document.file_id
    elif message.video:
        file_id = message.video.file_id
    else:
        await robust_reply_text(message, "❌ 无法识别。请发送视频文件！")
        return FaceVideoState.WAIT_VIDEO

    # Download file
    try:
        new_file = await context.bot.get_file(file_id)
        local_path = f"/tmp/bot_fsm_tmp/{file_id}_video.mp4"
        await new_file.download_to_drive(local_path)
        
        context.user_data['face_video_data']['video_path'] = local_path
    except Exception as e:
        logger.error(f"Error downloading video for FSM user {user_id}: {e}")
        await robust_reply_text(message, "❌ 下载视频失败，可能是文件过大，请重试或发送 /cancel 退出。")
        return FaceVideoState.WAIT_VIDEO

    # Present Resolution Selection
    keyboard = [
        [
            InlineKeyboardButton(f"高清 720p ({RESOLUTION_COST.get('720p', 18)} 灵石)", callback_data="fsm_fv_res_720"),
            InlineKeyboardButton(f"超清 1024p ({RESOLUTION_COST.get('1024p', 36)} 灵石)", callback_data="fsm_fv_res_1024")
        ],
        [
            InlineKeyboardButton("❌ 取消", callback_data="fsm_fv_cancel")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await robust_reply_text(
        message,
        "✅ **视频已收到！**\n\n【第三步】请选择要生成的画质。高画质会消耗更多灵石并增加排队时间。",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    return FaceVideoState.SELECT_RESOLUTION

# --- State 3: Resolution Selected ---
async def process_resolution_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """State 3: User selected resolution, start task execution."""
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data

    await query.answer()

    if data == "fsm_fv_cancel":
        await robust_edit_text(query.message, "🚫 您已取消视频换脸操作。")
        _cleanup_context(context, user_id)
        return ConversationHandler.END

    # Parse resolution
    res_str = data.split("_")[-1]
    resolution = int(res_str)
    cost = RESOLUTION_COST.get(f"{res_str}p", 20)
    duration = 121  # Assuming a max standard duration

    # Validate Priority & Balance
    priority = await permission_service.calculate_user_priority(user_id)
    if priority <= 0:
        await robust_edit_text(query.message, "⚠️ 您的排队优先级已耗尽（或修为不足），今日已无法再凝聚灵力，请明日再来！")
        _cleanup_context(context, user_id)
        return ConversationHandler.END

    fsm_data = context.user_data.get('face_video_data', {})
    if not fsm_data:
        try:
            await query.answer("交互已失效或任务已提交，请重新开始", show_alert=True)
        except Exception:
            pass
        return ConversationHandler.END

    face_path = fsm_data.pop('face_image_path', None)
    video_path = fsm_data.pop('video_path', None)

    if not face_path or not video_path:
        return ConversationHandler.END # Prevent double submit

    # Update message
    await robust_edit_text(query.message, f"🚀 正在提交视频换脸任务 ({resolution}p)，预计消耗 {cost} 灵石，请耐心等待...")

    # Spawn task via TaskService (assuming it cleans up files afterwards)
    create_background_task(
        context,
        TaskService.process_face_video_task(
            context, query.message.chat_id, user_id,
            query.from_user.username or query.from_user.full_name,
            face_path, video_path, resolution, duration=duration, cost=cost,
            message_id=query.message.message_id,
            cleanup=True  # TaskService will delete the files
        )
    )

    # Conversation finished successfully!
    _cleanup_context(context, user_id)
    return ConversationHandler.END

# --- Fallbacks & Timeout ---
async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User invoked /cancel during the FSM."""
    user_id = update.effective_user.id
    msg = "🚫 流程已取消。已清空历史上传内容。"
    
    if update.callback_query:
        await robust_edit_text(update.callback_query.message, msg)
    else:
        await robust_reply_text(update.message, msg)
        
    _cleanup_context(context, user_id)
    return ConversationHandler.END

async def timeout_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Triggered when conversation times out (e.g. user took too long)."""
    # Note: Depending on PTB version, timeout might be triggered via different mechanism.
    # But usually it calls the TIMEOUT fallback.
    user_id = update.effective_user.id if update.effective_user else "Unknown"
    logger.info(f"FSM timeout for user {user_id}")
    
    if update and update.message:
        await robust_reply_text(update.message, "⏰ 操作超时，为节省系统资源，本次流程已自动取消。您可以随时重新开始。")
        
    _cleanup_context(context, user_id)
    return ConversationHandler.END

import re

async def unexpected_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text if update.message else ""
    if text and re.match(r'^(🖼️ 懒人P图|🎬 懒人动图|🔙 返回主菜单|🛌 动图传教士|🎬 动图后入|🎬 口交黑人|🎬 脱衣吐舌|🎬 特写口交|🎨 自由P图|🌟 幻想换脸|💃 快速脱衣|🎭 快速换脸|🥵 快速自慰|🎭 随机换脸|🎬 视频换脸|🎬 自定义视频|🎬 自定义图生视频|📅 每日签到|签到|/checkin|🤝 分享赚灵石|⏳ 排队状态|排队|/queue|💰 个人中心|👤 个人中心|💎 充值灵石|/start)$', text):
        user_id = update.effective_user.id if update.effective_user else "Unknown"
        _cleanup_context(context, user_id)
        await robust_reply_text(update.message, "🔄 已为您自动取消未完成的流程。\n👉 **请再次点击刚才的按钮**，即可开始新任务！")
        return ConversationHandler.END

    await robust_reply_text(update.message, "⚠️ 当前处于交互流程中。请按提示操作，或发送 /cancel 取消本次操作。")
    return None # Return None keeps the state unchanged in PTB

# --- FSM Factory ---
def get_face_video_fsm_handler() -> ConversationHandler:
    """Factory to build the Face Video ConversationHandler."""
    return ConversationHandler(
        entry_points=[
            CommandHandler('video_swap', start_face_video),
            MessageHandler(filters.Regex(r'.*视频换脸.*'), start_face_video),
            CallbackQueryHandler(start_face_video, pattern='^fsm_start_face_video$')
        ],
        states={
            FaceVideoState.WAIT_FACE_IMAGE: [
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, receive_face_image),
                MessageHandler(filters.TEXT & ~filters.COMMAND, unexpected_input)
            ],
            FaceVideoState.WAIT_VIDEO: [
                MessageHandler(filters.VIDEO | filters.Document.VIDEO, receive_video),
                MessageHandler(filters.TEXT & ~filters.COMMAND, unexpected_input)
            ],
            FaceVideoState.SELECT_RESOLUTION: [
                CallbackQueryHandler(process_resolution_selection, pattern='^fsm_fv_res_'),
                CallbackQueryHandler(process_resolution_selection, pattern='^fsm_fv_cancel$')
            ],
            # PTB uses ConversationHandler.TIMEOUT internally
            ConversationHandler.TIMEOUT: [
                MessageHandler(filters.ALL, timeout_conversation)
            ]
        },
        fallbacks=[
            CommandHandler('cancel', cancel_conversation)
        ],
        conversation_timeout=300, # 5 minutes timeout to prevent dangling locks
        name="face_video_fsm",
        persistent=False # Assuming no FSM persistence in DB for now
    )
