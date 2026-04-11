import os
import logging
import asyncio
import uuid
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters
)
from src.handlers.conversation_states import QuickVideoState
from src.services.permission_service import permission_service
from src.services.task_service import task_service
from src.utils import robust_reply_text, robust_edit_text, create_background_task
from src.constants import get_video_settings_keyboard, DEFAULT_RESOLUTION, DEFAULT_DURATION, RESOLUTION_COST, DURATION_MULTIPLIER
from src.constants import MODE_PERFECT_VIDEO_INSERT, MODE_DOGGY_STYLE, MODE_BLOWJOB, MODE_UNDRESS_TONGUE, MODE_CLOSEUP_BLOWJOB

logger = logging.getLogger("fsm.quick_video")

QUICK_VIDEO_MODES = {
    "🛌 动图传教士": MODE_PERFECT_VIDEO_INSERT,
    "🎬 动图后入": MODE_DOGGY_STYLE,
    "🎬 口交黑人": MODE_BLOWJOB,
    "🎬 脱衣吐舌": MODE_UNDRESS_TONGUE,
    "🎬 特写口交": MODE_CLOSEUP_BLOWJOB
}

def _cleanup_context(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    context.user_data.pop('in_conversation', None)
    fsm_data = context.user_data.pop('quick_video_data', {})
    image_path = fsm_data.get('image_path')
    if image_path and os.path.exists(image_path):
        try:
            os.remove(image_path)
        except Exception as e:
            logger.error(f"Failed to remove {image_path}: {e}")

async def start_quick_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point for 懒人动图 (单步图生视频)"""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
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
    for key, val in QUICK_VIDEO_MODES.items():
        if key in text:
            mode = val
            break
            
    if not mode:
        return ConversationHandler.END

    context.user_data['in_conversation'] = f"QUICK_VIDEO_{mode}"
    context.user_data['quick_video_data'] = {
        'mode': mode,
        'resolution': DEFAULT_RESOLUTION,
        'duration': DEFAULT_DURATION,
        'image_path': None
    }

    mode_name = text[2:] if len(text) > 2 else text
    msg = f"🎬 **已切换到【{mode_name}】模式**。\n\n请发送一张【正面清晰图片】，我将自动处理。\n\n随时可以发送 /cancel 退出流程。"
    await robust_reply_text(update.message, msg, parse_mode="Markdown")
    return QuickVideoState.WAIT_IMAGE

async def receive_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    message = update.message
    fsm_data = context.user_data['quick_video_data']

    if message.document:
        if not message.document.mime_type.startswith('image/'):
            await robust_reply_text(message, "❌ 格式错误！请发送图片。")
            return QuickVideoState.WAIT_IMAGE
        file_id = message.document.file_id
    elif message.photo:
        file_id = message.photo[-1].file_id
    else:
        await robust_reply_text(message, "❌ 无法识别。请发送图片！")
        return QuickVideoState.WAIT_IMAGE

    try:
        new_file = await context.bot.get_file(file_id)
        os.makedirs("/tmp/bot_fsm_tmp", exist_ok=True)
        local_path = f"/tmp/bot_fsm_tmp/{uuid.uuid4()}_qvid.png"
        await new_file.download_to_drive(local_path)
        fsm_data['image_path'] = local_path
    except Exception as e:
        
        logger.error(f"Error downloading image for FSM user {user_id}: {e}")
        await robust_reply_text(message, "❌ 下载图片失败，请重试或发送 /cancel 退出。")
        return QuickVideoState.WAIT_IMAGE

    # Send settings keyboard
    user_group = await permission_service.get_user_group(user_id)
    user_identity = await permission_service.get_user_identity(user_id)
    
    res = fsm_data['resolution']
    dur = fsm_data['duration']
    reply_markup = get_video_settings_keyboard(user_group, user_identity, res, dur)
    
    base_cost = RESOLUTION_COST.get(res, 6)
    multiplier = DURATION_MULTIPLIER.get(dur, 1.0)
    cost = int(base_cost * multiplier)
    
    msg_text = f"⚙️ 当前视频画质：{res} | 时长：{dur} | 消耗灵石：{cost}\n\n请在下方选择您需要的画质和时长（部分画质和时长需要高境界或VIP身份解锁）：\n\n*提示：画质越高、时长越长，消耗灵石越多。注意：1024p 和 10s 无法同时选择。*\n\n【最后一步】**点击“🚀 开始生成”** 按钮提交任务。"
    
    # Add a "Start Generation" button
    keyboard = list(reply_markup.inline_keyboard)
    keyboard.append([InlineKeyboardButton("🚀 开始生成", callback_data="qvid_start_generation")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await robust_reply_text(message, msg_text, reply_markup=reply_markup, parse_mode="Markdown")
    return QuickVideoState.WAIT_SETTINGS

async def process_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data
    
    fsm_data = context.user_data.get('quick_video_data', {})
    if not fsm_data:
        try:
            await query.answer("交互已失效或任务已提交，请重新开始", show_alert=True)
        except Exception:
            pass
        return ConversationHandler.END

    if data == "qvid_start_generation":
        await query.answer()
        return await start_generation(update, context)

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
    
    msg_text = f"⚙️ 当前视频画质：{res} | 时长：{dur} | 消耗灵石：{cost}\n\n请在下方选择您需要的画质和时长（部分画质和时长需要高境界或VIP身份解锁）：\n\n*提示：画质越高、时长越长，消耗灵石越多。注意：1024p 和 10s 无法同时选择。*\n\n【最后一步】**点击“🚀 开始生成”** 按钮提交任务。"
    
    keyboard = list(reply_markup.inline_keyboard)
    keyboard.append([InlineKeyboardButton("🚀 开始生成", callback_data="qvid_start_generation")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await robust_edit_text(query.message, msg_text, reply_markup=reply_markup, parse_mode="Markdown")
    except Exception:
        pass
    
    await query.answer()
    return QuickVideoState.WAIT_SETTINGS

async def start_generation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    user_id = query.from_user.id
    
    fsm_data = context.user_data.get('quick_video_data', {})
    if not fsm_data:
        return ConversationHandler.END
        
    image_path = fsm_data.pop('image_path', None)
    if not image_path:
        return ConversationHandler.END # Prevent double submit

    res = fsm_data['resolution']
    dur = fsm_data['duration']
    mode = fsm_data['mode']
    
    base_cost = RESOLUTION_COST.get(res, 6)
    multiplier = DURATION_MULTIPLIER.get(dur, 1.0)
    cost = int(base_cost * multiplier)

    # Need to save these globally temporarily for the old task_service methods 
    # until they are refactored to take params directly
    context.user_data['custom_video_resolution'] = res
    context.user_data['custom_video_duration'] = dur
    context.user_data['mode'] = mode

    if not await permission_service.check_quota(update, context, cost=cost):
        if image_path and os.path.exists(image_path):
            try: os.remove(image_path)
            except: pass
        _cleanup_context(context, user_id)
        return ConversationHandler.END

    await robust_edit_text(query.message, f"🚀 正在提交视频任务，预计消耗 {cost} 灵石，请耐心等待...")

    # Map to old task_service methods
    video_modes = {
        MODE_PERFECT_VIDEO_INSERT: task_service.process_perfect_video_insert_task,
        MODE_DOGGY_STYLE: task_service.process_doggy_style_task,
        MODE_BLOWJOB: task_service.process_blowjob_task,
        MODE_UNDRESS_TONGUE: task_service.process_undress_tongue_task,
        MODE_CLOSEUP_BLOWJOB: task_service.process_closeup_blowjob_task
    }

    # Execute
    if mode in video_modes:
        # Note: the old methods use update.message, so we mock it with query.message
        # and preserve effective_user to prevent crashes in the underlying service
        class MockChat:
            def __init__(self, chat_id):
                self.id = chat_id

        class MockMessage:
            def __init__(self, msg):
                self._msg = msg
                self.chat_id = msg.chat_id
                self.message_id = msg.message_id
            
            async def reply_text(self, *args, **kwargs):
                return await self._msg.reply_text(*args, **kwargs)
                
            async def edit_text(self, *args, **kwargs):
                return await self._msg.edit_text(*args, **kwargs)
                
        class MockUpdate:
            def __init__(self, query, eff_user):
                self.message = MockMessage(query.message)
                self.effective_user = eff_user
                self._chat = MockChat(query.message.chat_id)
                
            @property
            def effective_chat(self):
                return self._chat

            @property
            def effective_message(self):
                return self.message

        mock_update = MockUpdate(query, update.effective_user)
        
        create_background_task(context, video_modes[mode](mock_update, context, image_path))

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

import re

async def unexpected_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text if update.message else ""
    if text and re.match(r'^(🖼️ 懒人P图|🎬 懒人动图|🔙 返回主菜单|🛌 动图传教士|🎬 动图后入|🎬 口交黑人|🎬 脱衣吐舌|🎬 特写口交|🎨 自由P图|🌟 幻想换脸|💃 快速脱衣|🎭 快速换脸|🥵 快速自慰|🎭 随机换脸|🎬 视频换脸|🎬 自定义视频|🎬 自定义图生视频|📅 每日签到|签到|/checkin|🤝 分享赚灵石|⏳ 排队状态|排队|/queue|💰 个人中心|👤 个人中心|💎 充值灵石|/start)$', text):
        user_id = update.effective_user.id if update.effective_user else "Unknown"
        _cleanup_context(context, user_id)
        await robust_reply_text(update.message, "🔄 已为您退出当前输入步骤（后台正在生成的任务不受影响）。\n👉 **请再次点击刚才的按钮**，即可开始新任务！")
        return ConversationHandler.END

    await robust_reply_text(update.message, "⚠️ 当前处于交互流程中。请按提示操作，或发送 /cancel 取消本次操作。")
    return None

def get_quick_video_fsm_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r'.*(动图传教士|动图后入|口交黑人|脱衣吐舌|特写口交).*'), start_quick_video)
        ],
        states={
            QuickVideoState.WAIT_IMAGE: [
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, receive_image),
                MessageHandler(filters.TEXT & ~filters.COMMAND, unexpected_input)
            ],
            QuickVideoState.WAIT_SETTINGS: [
                CallbackQueryHandler(process_settings, pattern='^set_(res|dur)_|^qvid_start_generation$'),
                MessageHandler(filters.ALL & ~filters.COMMAND, unexpected_input)
            ],
            ConversationHandler.TIMEOUT: [
                MessageHandler(filters.ALL, timeout_conversation)
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel_conversation)],
        conversation_timeout=300,
        name="quick_video_fsm",
        persistent=False
    )
