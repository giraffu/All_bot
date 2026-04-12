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
from src.handlers.conversation_states import CustomVideoState
from src.services.permission_service import permission_service
from src.services.task_service import TaskService
from src.utils import robust_reply_text, robust_edit_text, create_background_task
from src.constants import get_video_settings_keyboard, DEFAULT_RESOLUTION, DEFAULT_DURATION, RESOLUTION_COST, DURATION_MULTIPLIER

logger = logging.getLogger("fsm.custom_video")

def _cleanup_context(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    context.user_data.pop('in_conversation', None)
    pending_files = context.user_data.pop('custom_video_data', {})
    path = pending_files.get('image_path')
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except Exception as e:
            logger.error(f"Failed to remove {path}: {e}")

async def start_custom_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point for 自定义图生视频"""
    user_id = update.effective_user.id
    
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

    context.user_data['in_conversation'] = "CUSTOM_VIDEO"
    context.user_data['custom_video_data'] = {
        'resolution': DEFAULT_RESOLUTION,
        'duration': DEFAULT_DURATION,
        'image_path': None
    }

    msg = "🎬 **已切换到【自定义图生视频】模式。**\n\n【第一步】请发送一张【起始图片】。\n(注意：该模式生成视频，请确保后续提示词动作逻辑合理)\n\n随时可以发送 /cancel 退出流程。"
    await robust_reply_text(update.message, msg, parse_mode="Markdown")
    return CustomVideoState.WAIT_IMAGE

async def receive_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    message = update.message
    fsm_data = context.user_data['custom_video_data']

    if message.document:
        if not message.document.mime_type.startswith('image/'):
            await robust_reply_text(message, "❌ 格式错误！请发送图片。")
            return CustomVideoState.WAIT_IMAGE
        file_id = message.document.file_id
    elif message.photo:
        file_id = message.photo[-1].file_id
    else:
        await robust_reply_text(message, "❌ 无法识别。请发送图片！")
        return CustomVideoState.WAIT_IMAGE

    try:
        new_file = await context.bot.get_file(file_id)
        os.makedirs("/tmp/bot_fsm_tmp", exist_ok=True)
        local_path = f"/tmp/bot_fsm_tmp/{uuid.uuid4()}_custom_vid.png"
        await new_file.download_to_drive(local_path)
        fsm_data['image_path'] = local_path
    except Exception as e:
        
        logger.error(f"Error downloading image for FSM user {user_id}: {e}")
        await robust_reply_text(message, "❌ 下载图片失败，请重试或发送 /cancel 退出。")
        return CustomVideoState.WAIT_IMAGE

    # Send settings keyboard
    user_group = await permission_service.get_user_group(user_id)
    user_identity = await permission_service.get_user_identity(user_id)
    
    res = fsm_data['resolution']
    dur = fsm_data['duration']
    reply_markup = get_video_settings_keyboard(user_group, user_identity, res, dur)
    
    base_cost = RESOLUTION_COST.get(res, 6)
    multiplier = DURATION_MULTIPLIER.get(dur, 1.0)
    cost = int(base_cost * multiplier)
    
    msg_text = f"⚙️ 当前自定义视频画质：{res} | 时长：{dur} | 消耗灵石：{cost}\n\n请在下方选择您需要的画质和时长（部分画质和时长需要高境界或VIP身份解锁）：\n\n*提示：画质越高、时长越长，消耗灵石越多。注意：1024p 和 10s 无法同时选择。*\n\n【第二步】**请直接发送提示词 (Text)** 开始生成。"
    
    await robust_reply_text(message, msg_text, reply_markup=reply_markup, parse_mode="Markdown")
    return CustomVideoState.WAIT_SETTINGS_AND_PROMPT

async def process_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle settings change via inline keyboard"""
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data
    
    fsm_data = context.user_data.get('custom_video_data', {})
    if not fsm_data:
        try:
            await query.answer("交互已失效或任务已提交，请重新开始", show_alert=True)
        except Exception:
            pass
        return ConversationHandler.END

    if data.startswith("set_res_"):
        fsm_data['resolution'] = data.split("_")[2]
    elif data.startswith("set_dur_"):
        fsm_data['duration'] = data.split("_")[2]

    res = fsm_data['resolution']
    dur = fsm_data['duration']
    
    user_group = await permission_service.get_user_group(user_id)
    user_identity = await permission_service.get_user_identity(user_id)
    reply_markup = get_video_settings_keyboard(user_group, user_identity, res, dur)
    
    base_cost = RESOLUTION_COST.get(res, 6)
    multiplier = DURATION_MULTIPLIER.get(dur, 1.0)
    cost = int(base_cost * multiplier)
    
    msg_text = f"⚙️ 当前自定义视频画质：{res} | 时长：{dur} | 消耗灵石：{cost}\n\n请在下方选择您需要的画质和时长（部分画质和时长需要高境界或VIP身份解锁）：\n\n*提示：画质越高、时长越长，消耗灵石越多。注意：1024p 和 10s 无法同时选择。*\n\n【第二步】**请直接发送提示词 (Text)** 开始生成。"
    
    try:
        await robust_edit_text(query.message, msg_text, reply_markup=reply_markup, parse_mode="Markdown")
    except Exception:
        pass
    
    await query.answer()
    return CustomVideoState.WAIT_SETTINGS_AND_PROMPT

async def receive_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    message = update.message
    prompt = message.text.strip()
    
    fsm_data = context.user_data['custom_video_data']
    res = fsm_data['resolution']
    dur = fsm_data['duration']
    
    base_cost = RESOLUTION_COST.get(res, 6)
    multiplier = DURATION_MULTIPLIER.get(dur, 1.0)
    cost = int(base_cost * multiplier)

    if not await permission_service.check_quota(update, context, cost=cost):
        _cleanup_context(context, user_id)
        return ConversationHandler.END

    image_path = fsm_data.pop('image_path', None)
    if not image_path:
        return ConversationHandler.END

    await robust_reply_text(message, f"🚀 正在提交自定义视频任务，预计消耗 {cost} 灵石，请耐心等待...")

    # Use TaskService to process.
    # Note: process_custom_video_task expects (update, context, image_path, prompt, cleanup)
    # The resolution and duration are fetched from context.user_data inside the task service,
    # so we must set them globally for the task service to read.
    context.user_data['custom_video_resolution'] = res
    context.user_data['custom_video_duration'] = dur
    
    create_background_task(
        context,
        TaskService.process_custom_video_task(
            update=update,
            context=context,
            prompt=prompt,
            image_path=image_path,
            cleanup=True
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

def get_custom_video_fsm_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler('custom_video', start_custom_video),
            MessageHandler(filters.Regex(r'.*自定义图生视频.*'), start_custom_video),
            CallbackQueryHandler(start_custom_video, pattern='^fsm_start_custom_video$')
        ],
        states={
            CustomVideoState.WAIT_IMAGE: [
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, receive_image),
                MessageHandler(filters.TEXT & ~filters.COMMAND, unexpected_input)
            ],
            CustomVideoState.WAIT_SETTINGS_AND_PROMPT: [
                CallbackQueryHandler(process_settings, pattern='^set_(res|dur)_'),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_prompt),
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, unexpected_input),
            ],
            ConversationHandler.TIMEOUT: [
                MessageHandler(filters.ALL, timeout_conversation)
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel_conversation)],
        conversation_timeout=300,
        name="custom_video_fsm",
        persistent=False
    )
