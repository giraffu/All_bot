import logging
import os
import uuid

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from src.constants import (
    LTX_DURATION_MULTIPLIER,
    LTX_RESOLUTION_COST,
    get_ltx_video_settings_keyboard,
)
from src.handlers.conversation_states import LtxVideoState
from src.handlers.prompt_router import is_global_menu_command
from src.services.permission_service import permission_service
from src.services.task_service import TaskService
from src.utils import (
    create_background_task,
    robust_edit_text,
    robust_reply_text,
)
import contextlib

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
    query = update.callback_query
    if query:
        with contextlib.suppress(Exception):
            await query.answer(text="⏳ 任务初始化中...", cache_time=2)
    
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
    
    msg_text = f"""⚙️ 当前高级视频画质：{res} | 时长：{dur} | 消耗灵石：{cost}

请在下方选择您需要的时长：
*提示：时长越长，消耗灵石越多。*

【第二步】**请直接发送提示词 (Text)** 开始生成。
💡 **提示词撰写指南**：
1. 格式：`[风格], [动作], [具体描述]`
2. **可选风格** (选填)：`3D`, `Real Video`, `Amateur`
3. **特定动作触发词** (如需特定动作，请**务必**在开头添加对应英文)：
   - 传教士(女下男上)：`m15510n4ry`
   - 口交：`bl0wj0b`
   - 双人口交：`d0ubl3_bj`
   - 反向女上位：`c0wg1rl`
   - 后入/狗狗式：`d0gg1e`
4. **具体描述**：详细描述人物特征、穿着、动作细节和背景环境。
*(例如：Real Video, m15510n4ry, A close-up view of a single petite woman...)*"""
    
    await robust_reply_text(message, msg_text, reply_markup=reply_markup, parse_mode="Markdown")
    return LtxVideoState.WAIT_SETTINGS_AND_PROMPT

async def process_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle settings change via inline keyboard"""
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data
    
    fsm_data = context.user_data.get('ltx_video_data', {})
    if not fsm_data:
        with contextlib.suppress(Exception):
            await query.answer("交互已失效或任务已提交，请重新开始", show_alert=True)
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
    
    msg_text = f"""⚙️ 当前高级视频画质：{res} | 时长：{dur} | 消耗灵石：{cost}

请在下方选择您需要的时长：
*提示：时长越长，消耗灵石越多。*

【第二步】**请直接发送纯英文提示词 (Text)** 开始生成。
💡 **提示词撰写指南**：
1. 格式：`[风格], [动作], [具体描述]`
2. **可选风格** (选填)：`3D`, `Real Video`, `Amateur`
3. **特定动作触发词** (如需特定动作，请**务必**在开头添加对应英文)：
   - 传教士(女下男上)：`m15510n4ry`
   - 口交：`bl0wj0b`
   - 双人口交：`d0ubl3_bj`
   - 反向女上位：`c0wg1rl`
   - 后入/狗狗式：`d0gg1e`
4. **具体描述**：详细描述人物特征、穿着、动作细节和背景环境。
*(例如：Real Video, m15510n4ry, A close-up view of a single petite woman...)*"""
    
    with contextlib.suppress(Exception):
        await robust_edit_text(query.message, msg_text, reply_markup=reply_markup, parse_mode="Markdown")
    
    await query.answer(text="⏳ 任务初始化中...", cache_time=2)
    return LtxVideoState.WAIT_SETTINGS_AND_PROMPT

async def receive_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message
    prompt = message.text.strip()
    
    if is_global_menu_command(prompt):
        return await unexpected_input(update, context)

    fsm_data = context.user_data.get('ltx_video_data')
    if not fsm_data:
        await robust_reply_text(message, "⚠️ 任务已提交或已过期，请勿重复操作。")
        return ConversationHandler.END

    fsm_data['prompt'] = prompt

    reply_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ 确定生成", callback_data="confirm_ltx_video")]
    ])
    msg_text = (
        f"📝 **您的提示词**:\n`{prompt}`\n\n"
        "确认无误后请点击【确定生成】。"
    )
    
    await robust_reply_text(message, msg_text, reply_markup=reply_markup, parse_mode="Markdown")
    return LtxVideoState.WAIT_CONFIRMATION



async def confirm_generation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    user_id = query.from_user.id
    
    fsm_data = context.user_data.get('ltx_video_data')
    if not fsm_data:
        with contextlib.suppress(Exception):
            await query.answer("⚠️ 任务已提交或已过期，请勿重复操作。", show_alert=True)
        return ConversationHandler.END

    res = fsm_data['resolution']
    dur = fsm_data['duration']
    prompt = fsm_data.get('prompt', '')
    
    base_cost = LTX_RESOLUTION_COST.get(res, 10)
    multiplier = LTX_DURATION_MULTIPLIER.get(dur, 1.0)
    cost = int(base_cost * multiplier)

    if not update.effective_user: return ConversationHandler.END
    user = update.effective_user
    if not await permission_service.check_quota(user.id, user.username, user.full_name, context.bot, update.effective_chat.id, cost=cost):
        _cleanup_context(context, user_id)
        return ConversationHandler.END

    image_path = fsm_data.pop('image_path', None)
    if not image_path:
        return ConversationHandler.END

    with contextlib.suppress(Exception):
        await robust_edit_text(query.message, f"🚀 正在提交高级视频任务，预计消耗 {cost} 灵石，请耐心等待...")

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
    await query.answer(text="⏳ 任务初始化中...", cache_time=2)
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
    if text and is_global_menu_command(text):
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
