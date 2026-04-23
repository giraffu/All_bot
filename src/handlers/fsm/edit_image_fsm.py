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
from src.handlers.conversation_states import EditImageState
from src.services.permission_service import permission_service
from src.services.task_service import TaskService
from src.utils import robust_reply_text, robust_edit_text, create_background_task
from src.constants import TASK_COSTS, MODE_EDIT, MODE_I2I_PRO

logger = logging.getLogger("fsm.edit_image")

def _cleanup_context(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    context.user_data.pop('in_conversation', None)
    pending_files = context.user_data.pop('edit_image_data', {})
    images = pending_files.get('images', [])
    for path in images:
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except Exception as e:
                logger.error(f"Failed to remove {path}: {e}")

async def start_edit_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point for 自由P图 and 幻想换脸"""
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

    mode = MODE_EDIT if "自由P图" in text else MODE_I2I_PRO
    cost = TASK_COSTS.get(mode, 2)

    context.user_data['in_conversation'] = "EDIT_IMAGE"
    context.user_data['edit_image_data'] = {
        'mode': mode,
        'images': [],
        'cost': cost
    }

    if mode == MODE_I2I_PRO:
        msg = f"🌟 **已进入【幻想换脸】模式** (消耗 {cost} 灵石)。\n\n【第一步】请发送 1 张您的参考图片。\n\n随时可以发送 /cancel 退出流程。"
    else:
        msg = f"🎨 **已进入【自由P图】模式** (消耗 {cost} 灵石)。\n\n【第一步】请发送您的参考图片。\n\n随时可以发送 /cancel 退出流程。"

    await robust_reply_text(update.message, msg, parse_mode="Markdown")
    return EditImageState.WAIT_REFERENCE_IMAGES

async def receive_reference_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    message = update.message
    fsm_data = context.user_data['edit_image_data']

    if message.document:
        if not message.document.mime_type.startswith('image/'):
            await robust_reply_text(message, "❌ 格式错误！请发送图片。")
            return EditImageState.WAIT_REFERENCE_IMAGES
        file_id = message.document.file_id
    elif message.photo:
        file_id = message.photo[-1].file_id
    else:
        await robust_reply_text(message, "❌ 无法识别。请发送图片！")
        return EditImageState.WAIT_REFERENCE_IMAGES

    try:
        new_file = await context.bot.get_file(file_id)
        os.makedirs("/tmp/bot_fsm_tmp", exist_ok=True)
        local_path = f"/tmp/bot_fsm_tmp/{uuid.uuid4()}_ref.png"
        await new_file.download_to_drive(local_path)
        fsm_data['images'].append(local_path)
    except Exception as e:
        
        logger.error(f"Error downloading image for FSM user {user_id}: {e}")
        await robust_reply_text(message, "❌ 下载图片失败，请重试或发送 /cancel 退出。")
        return EditImageState.WAIT_REFERENCE_IMAGES

    if fsm_data['mode'] == MODE_I2I_PRO:
        msg = "✅ **已收到 1 张参考图。**\n\n【第二步】请直接发送**提示词 (Text)** 开始生成。\n\n💡 **提示词要求**：\n描述幻想的人物和场景，后续会将参考图中的人物换脸到幻想的场景人物中。"
    else:
        num_images = len(fsm_data['images'])
        if num_images == 1:
            msg = f"✅ **已收到 1 张参考图。**\n\n【第二步】请直接发送**提示词 (Text)** 开始生成。\n（如果是双图融合，您可以继续发送第2张图片，双图融合将消耗 6 灵石）"
        else:
            fsm_data['cost'] = 6
            msg = f"✅ **已收到 2 张参考图。**\n\n【第二步】请直接发送**提示词 (Text)** 开始生成。\n（双图融合将消耗 6 灵石，多余的图片将不生效）"

    await robust_reply_text(message, msg, parse_mode="Markdown")
    
    # 允许接收多个图片（对于自由P图），但也允许接收文字进入下一步
    return EditImageState.WAIT_PROMPT

async def receive_additional_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """如果在 WAIT_PROMPT 状态下继续发图，就把图追加进去（仅自由P图）"""
    message = update.message
    fsm_data = context.user_data['edit_image_data']
    
    if fsm_data['mode'] == MODE_I2I_PRO:
        await robust_reply_text(message, "⚠️ 幻想换脸模式只需要 1 张图片，请直接发送文字提示词。")
        return EditImageState.WAIT_PROMPT

    if fsm_data['mode'] == MODE_EDIT and len(fsm_data['images']) >= 2:
        await robust_reply_text(message, "⚠️ 自由P图最多只支持 2 张图片融合，多余的图片将不生效，请直接发送文字提示词开始生成。")
        return EditImageState.WAIT_PROMPT

    return await receive_reference_image(update, context)

async def receive_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    message = update.message
    prompt = message.text.strip()
    
    if re.match(r'^(🖼️ 懒人P图|🎬 懒人动图|🔙 返回主菜单|🛌 动图传教士|🎬 动图后入|🎬 口交黑人|🎬 脱衣吐舌|🎬 特写口交|🎨 自由P图|🌟 幻想换脸|💃 快速脱衣|🎭 快速换脸|🥵 快速自慰|🎭 随机换脸|🎬 视频换脸|🎬 自定义视频|🎬 自定义图生视频|🎬 图生视频\(附加模型\)|🎬 高级图生视频|📅 每日签到|签到|/checkin|🤝 分享赚灵石|⏳ 排队状态|排队|/queue|💰 个人中心|👤 个人中心|💎 充值灵石|/start|🏆 发现/排行榜|一键应用该模板)$', prompt):
        return await unexpected_input(update, context)

    fsm_data = context.user_data.get('edit_image_data')
    if not fsm_data:
        await robust_reply_text(message, "⚠️ 任务已提交或已过期，请勿重复操作。")
        return ConversationHandler.END

    cost = fsm_data['cost']
    mode = fsm_data['mode']

    if not await permission_service.check_quota(update, context, cost=cost):
        _cleanup_context(context, user_id)
        return ConversationHandler.END

    images = list(fsm_data['images'])
    
    if not images:
        return ConversationHandler.END # Prevent double submit

    # 转移文件所有权给 TaskService
    fsm_data['images'] = [] 

    await robust_reply_text(message, f"🚀 正在提交生成任务，预计消耗 {cost} 灵石，请耐心等待...")

    if mode == MODE_I2I_PRO:
        # Mock Update to support legacy process_i2i_pro_task
        # Mock Update is no longer needed because process_i2i_pro_task doesn't take update
        create_background_task(
            context,
            TaskService.process_i2i_pro_task(
                context, message.chat_id, user_id, 
                update.effective_user.username or update.effective_user.full_name,
                prompt, images
            )
        )
    else:
        create_background_task(
            context,
            TaskService.process_generation_task(
                context, message.chat_id, user_id,
                update.effective_user.username or update.effective_user.full_name,
                prompt, images, is_video=False, task_type=mode, cleanup=True
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
    if text and re.match(r'^(🖼️ 懒人P图|🎬 懒人动图|🔙 返回主菜单|🛌 动图传教士|🎬 动图后入|🎬 口交黑人|🎬 脱衣吐舌|🎬 特写口交|🎨 自由P图|🌟 幻想换脸|💃 快速脱衣|🎭 快速换脸|🥵 快速自慰|🎭 随机换脸|🎬 视频换脸|🎬 自定义视频|🎬 自定义图生视频|🎬 图生视频\(附加模型\)|🎬 高级图生视频|📅 每日签到|签到|/checkin|🤝 分享赚灵石|⏳ 排队状态|排队|/queue|💰 个人中心|👤 个人中心|💎 充值灵石|/start|🏆 发现/排行榜|一键应用该模板)$', text):
        user_id = update.effective_user.id if update.effective_user else "Unknown"
        _cleanup_context(context, user_id)
        await robust_reply_text(update.message, "🔄 已为您退出当前输入步骤（后台正在生成的任务不受影响）。\n👉 **请再次点击刚才的按钮**，即可开始新任务！")
        return ConversationHandler.END

    await robust_reply_text(update.message, "⚠️ 当前处于交互流程中。请按提示操作，或发送 /cancel 取消本次操作。")
    return None

def get_edit_image_fsm_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r'.*(自由P图|幻想换脸).*'), start_edit_image)
        ],
        states={
            EditImageState.WAIT_REFERENCE_IMAGES: [
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, receive_reference_image),
                MessageHandler(filters.TEXT & ~filters.COMMAND, unexpected_input)
            ],
            EditImageState.WAIT_PROMPT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_prompt),
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, receive_additional_image),
            ],
            ConversationHandler.TIMEOUT: [
                MessageHandler(filters.ALL, timeout_conversation)
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel_conversation)],
        conversation_timeout=300,
        name="edit_image_fsm",
        persistent=False
    )
