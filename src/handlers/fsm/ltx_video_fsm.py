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
from src.handlers.conversation_states import LtxVideoState
from src.services.permission_service import permission_service
from src.services.task_service import TaskService
from src.utils import robust_reply_text, robust_edit_text, create_background_task
from src.constants import get_ltx_video_settings_keyboard, LTX_RESOLUTION_COST, LTX_DURATION_MULTIPLIER

logger = logging.getLogger("fsm.ltx_video")

def _cleanup_context(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    context.user_data.pop('in_conversation', None)
    pending_files = context.user_data.pop('ltx_video_data', {})
    path = pending_files.get('image_path')
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except Exception as e:
            logger.error(f"Failed to remove {path}: {e}")

async def start_ltx_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point for 高级图生视频"""
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

    context.user_data['in_conversation'] = "LTX_VIDEO"
    context.user_data['ltx_video_data'] = {
        'resolution': "1280x704",
        'duration': "5s",
        'image_path': None
    }

    msg = "🎬 **已切换到【高级图生视频】模式。**\n\n【第一步】请发送一张【起始图片】。\n(注意：为避免画面被裁剪，建议上传比例接近 9:16 的竖屏图片)\n\n随时可以发送 /cancel 退出流程。"
    await robust_reply_text(update.message, msg, parse_mode="Markdown")
    return LtxVideoState.WAIT_IMAGE

async def receive_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    message = update.message
    fsm_data = context.user_data['ltx_video_data']

    if message.document:
        if not message.document.mime_type.startswith('image/'):
            await robust_reply_text(message, "❌ 格式错误！请发送图片。")
            return LtxVideoState.WAIT_IMAGE
        file_id = message.document.file_id
    elif message.photo:
        file_id = message.photo[-1].file_id
    else:
        await robust_reply_text(message, "❌ 无法识别。请发送图片！")
        return LtxVideoState.WAIT_IMAGE

    try:
        new_file = await context.bot.get_file(file_id)
        os.makedirs("/tmp/bot_fsm_tmp", exist_ok=True)
        local_path = f"/tmp/bot_fsm_tmp/{uuid.uuid4()}_ltx_vid.png"
        await new_file.download_to_drive(local_path)
        fsm_data['image_path'] = local_path
    except Exception as e:
        
        logger.error(f"Error downloading image for FSM user {user_id}: {e}")
        await robust_reply_text(message, "❌ 下载图片失败，请重试或发送 /cancel 退出。")
        return LtxVideoState.WAIT_IMAGE

    # Send settings keyboard
    from src.core.user_core import get_or_create_user_by_telegram
    internal_user, _ = await get_or_create_user_by_telegram(user_id)
    internal_user_id = internal_user.id
    
    user_group = await permission_service.get_user_group(internal_user_id)
    user_identity = await permission_service.get_user_identity(internal_user_id)
    
    res = fsm_data['resolution']
    dur = fsm_data['duration']
    reply_markup = get_ltx_video_settings_keyboard(user_group, user_identity, res, dur)
    
    base_cost = LTX_RESOLUTION_COST.get(res, 10)
    multiplier = LTX_DURATION_MULTIPLIER.get(dur, 1.0)
    cost = int(base_cost * multiplier)
    
    msg_text = f"⚙️ 当前高级视频画质：{res} | 时长：{dur} | 消耗灵石：{cost}\n\n请在下方选择您需要的时长：\n\n*提示：时长越长，消耗灵石越多。*\n\n【第二步】**请直接发送提示词 (Text)** 开始生成。（建议以动作描述为主）"
    
    await robust_reply_text(message, msg_text, reply_markup=reply_markup, parse_mode="Markdown")
    return LtxVideoState.WAIT_SETTINGS_AND_PROMPT

async def process_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle settings change via inline keyboard"""
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data
    
    fsm_data = context.user_data.get('ltx_video_data', {})
    if not fsm_data:
        try:
            await query.answer("交互已失效或任务已提交，请重新开始", show_alert=True)
        except Exception:
            pass
        return ConversationHandler.END

    if data.startswith("set_ltxres_"):
        fsm_data['resolution'] = data.split("_")[2]
    elif data.startswith("set_ltxdur_"):
        fsm_data['duration'] = data.split("_")[2]

    res = fsm_data['resolution']
    dur = fsm_data['duration']
    
    from src.core.user_core import get_or_create_user_by_telegram
    internal_user, _ = await get_or_create_user_by_telegram(user_id)
    internal_user_id = internal_user.id
    
    user_group = await permission_service.get_user_group(internal_user_id)
    user_identity = await permission_service.get_user_identity(internal_user_id)
    reply_markup = get_ltx_video_settings_keyboard(user_group, user_identity, res, dur)
    
    base_cost = LTX_RESOLUTION_COST.get(res, 10)
    multiplier = LTX_DURATION_MULTIPLIER.get(dur, 1.0)
    cost = int(base_cost * multiplier)
    
    msg_text = f"⚙️ 当前高级视频画质：{res} | 时长：{dur} | 消耗灵石：{cost}\n\n请在下方选择您需要的时长：\n\n*提示：时长越长，消耗灵石越多。*\n\n【第二步】**请直接发送提示词 (Text)** 开始生成。（建议以动作描述为主）"
    
    try:
        await robust_edit_text(query.message, msg_text, reply_markup=reply_markup, parse_mode="Markdown")
    except Exception:
        pass
    
    await query.answer()
    return LtxVideoState.WAIT_SETTINGS_AND_PROMPT

async def receive_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    message = update.message
    prompt = message.text.strip()
    
    if re.match(r'^(🖼️ 懒人P图|🎬 懒人动图|🔙 返回主菜单|🛌 动图传教士|🎬 动图后入|🎬 口交黑人|🎬 脱衣吐舌|🎬 特写口交|🎨 自由P图|🌟 幻想换脸|💃 快速脱衣|🎭 快速换脸|🥵 快速自慰|🎭 随机换脸|🎬 视频换脸|🎬 自定义视频|🎬 自定义图生视频|🎬 图生视频\(附加模型\)|🎬 高级图生视频|📅 每日签到|签到|/checkin|🤝 分享赚灵石|⏳ 排队状态|排队|/queue|💰 个人中心|👤 个人中心|💎 充值灵石|/start|🏆 发现/排行榜|一键应用该模板)$', prompt):
        return await unexpected_input(update, context)

    fsm_data = context.user_data.get('ltx_video_data')
    if not fsm_data:
        await robust_reply_text(message, "⚠️ 任务已提交或已过期，请勿重复操作。")
        return ConversationHandler.END

    fsm_data['prompt'] = prompt

    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("✅ 确定生成", callback_data="confirm_ltx_video")]])
    msg_text = (
        "📝 **提示词已记录**\n\n"
        "💡 提示词最好用英文的，描写好初始图片的人物特征，背景环境，然后描述动作，镜头的移动，描述人物说的话。\n\n"
        "请确认无误后点击下方按钮开始生成："
    )
    
    await robust_reply_text(message, msg_text, reply_markup=reply_markup, parse_mode="Markdown")
    return LtxVideoState.WAIT_CONFIRMATION

async def confirm_generation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    user_id = query.from_user.id
    
    fsm_data = context.user_data.get('ltx_video_data')
    if not fsm_data:
        try:
            await query.answer("⚠️ 任务已提交或已过期，请勿重复操作。", show_alert=True)
        except Exception:
            pass
        return ConversationHandler.END

    res = fsm_data['resolution']
    dur = fsm_data['duration']
    prompt = fsm_data.get('prompt', '')
    
    base_cost = LTX_RESOLUTION_COST.get(res, 10)
    multiplier = LTX_DURATION_MULTIPLIER.get(dur, 1.0)
    cost = int(base_cost * multiplier)

    if not await permission_service.check_quota(update, context, cost=cost):
        _cleanup_context(context, user_id)
        return ConversationHandler.END

    image_path = fsm_data.pop('image_path', None)
    if not image_path:
        return ConversationHandler.END

    try:
        await robust_edit_text(query.message, f"🚀 正在提交高级视频任务，预计消耗 {cost} 灵石，请耐心等待...")
    except Exception:
        pass

    # Use TaskService to process.
    context.user_data['ltx_video_resolution'] = res
    context.user_data['ltx_video_duration'] = dur
    
    create_background_task(
        context,
        TaskService.process_ltx_video_task(
            update=update,
            context=context,
            prompt=prompt,
            image_path=image_path,
            cleanup=True
        )
    )

    _cleanup_context(context, user_id)
    await query.answer()
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

def get_ltx_video_fsm_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler('ltx_video', start_ltx_video),
            MessageHandler(filters.Regex(r'.*高级图生视频.*'), start_ltx_video),
            CallbackQueryHandler(start_ltx_video, pattern='^fsm_start_ltx_video$')
        ],
        states={
            LtxVideoState.WAIT_IMAGE: [
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, receive_image),
                MessageHandler(filters.TEXT & ~filters.COMMAND, unexpected_input)
            ],
            LtxVideoState.WAIT_SETTINGS_AND_PROMPT: [
                CallbackQueryHandler(process_settings, pattern='^set_ltx(res|dur)_'),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_prompt),
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, unexpected_input),
            ],
            LtxVideoState.WAIT_CONFIRMATION: [
                CallbackQueryHandler(confirm_generation, pattern='^confirm_ltx_video$'),
                MessageHandler(filters.TEXT & ~filters.COMMAND, unexpected_input),
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, unexpected_input),
            ],
            ConversationHandler.TIMEOUT: [
                MessageHandler(filters.ALL, timeout_conversation)
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel_conversation)],
        conversation_timeout=300,
        name="ltx_video_fsm",
        persistent=False
    )
