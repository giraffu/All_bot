from src.handlers.prompt_router import is_global_menu_command
import os
import re
import uuid
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)
from src.constants import (
    TMP_DIR,
    TASK_COSTS,
    MODE_NAME_MAP,
    MAIN_MENU_KEYBOARD,
    MODE_FACE_VIDEO_STEP1,
    MODE_FACE_VIDEO_STEP2,
    MODE_FACESWAP_STEP1,
    MODE_I2I_PRO,
    MODE_EDIT,
    MODE_CUSTOM_VIDEO,
    MODE_VIDEO_LORA
)
from src.utils import (
    robust_reply_text,
    robust_edit_text,
    is_maintenance_mode
)
from src.services.permission_service import permission_service
from src.services.task_service import task_service

logger = logging.getLogger(__name__)

# Single state for waiting for user's face/reference image
WAIT_REFERENCE_IMAGE = 1

def _cleanup_context(context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop('in_conversation', None)
    context.user_data.pop('gallery_apply_data', None)

async def start_gallery_apply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point from the callback query 'gallery_apply_{post_id}'"""
    query = update.callback_query
    if query:
        try:
            await query.answer(text="⏳ 任务初始化中...", cache_time=2)
        except Exception:
            pass

    if is_maintenance_mode():
        msg = "⚠️ 🛠️ **系统正在维护升级中**\n\n暂不接受新任务，请稍后再试！"
        await robust_edit_text(update.callback_query.message, msg, parse_mode="Markdown")
        return ConversationHandler.END

    if context.user_data.get('in_conversation'):
        msg = "⚠️ 您当前有未完成的交互流程，请先发送 /cancel 退出当前流程后再试。"
        await robust_reply_text(update.callback_query.message, msg)
        return ConversationHandler.END

    query = update.callback_query
    data = query.data
    post_id = int(data.replace("gallery_apply_", ""))

    from sqlalchemy import select
    from src.database.core import AsyncSessionLocal
    from src.database.models import GalleryPost, History, UserInteraction
    from src.core.user_core import get_or_create_user_by_telegram

    internal_user, _ = await get_or_create_user_by_telegram(query.from_user.id)

    async with AsyncSessionLocal() as session:
        post = (await session.execute(select(GalleryPost).where(GalleryPost.id == post_id))).scalar_one_or_none()
        if not post:
            await query.answer("❌ 帖子已失效", show_alert=True)
            return ConversationHandler.END
            
        history = (await session.execute(select(History).where(History.task_id == post.task_id))).scalars().first()
        if not history:
            await query.answer("❌ 无法获取原任务参数", show_alert=True)
            return ConversationHandler.END

        # Extract attributes before commit/rollback to avoid DetachedInstanceError
        task_type = history.type
        prompt = history.prompt or ""
        input_file = history.input_file or ""
        post_media_type = post.media_type
        post_width = post.width
        post_height = post.height
        post_duration = post.duration

        # Record interaction
        interaction = UserInteraction(user_id=internal_user.id, post_id=post.id, action_type="apply")
        session.add(interaction)
        post.applied_count += 1
        
        from sqlalchemy.exc import IntegrityError
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            # 已经记录过应用，静默忽略重复计数
            pass
            
    # Security check: Only allow specific task types for gallery application
    from src.constants import MODE_IMG2IMG_LORA, MODE_LTX_VIDEO
    allowed_types = [MODE_I2I_PRO, MODE_EDIT, MODE_CUSTOM_VIDEO, MODE_VIDEO_LORA, MODE_IMG2IMG_LORA, MODE_LTX_VIDEO]
    if task_type not in allowed_types:
        await query.answer("❌ 此模板类型不支持一键应用", show_alert=True)
        return ConversationHandler.END
    
    # Extract resolution and duration if it's a video
    res_str = "512p"
    dur_str = "5s"
    from src.constants import RESOLUTION_COST, DURATION_MULTIPLIER, RESOLUTION_PERMISSIONS, DURATION_PERMISSIONS, LTX_RESOLUTION_COST, LTX_DURATION_MULTIPLIER
    
    if task_type in (MODE_EDIT, "edit", MODE_IMG2IMG_LORA):
        # Image tasks that don't need double cost unless 2 images are provided later
        cost = 2
    else:
        cost = TASK_COSTS.get(task_type, 2)
    
    if post_media_type == 'video':
        if task_type == MODE_LTX_VIDEO:
            match = re.search(r"\[(.*?)\|(.*?)\]\s*(.*)", prompt)
            if match:
                res_str = match.group(1).strip()
                dur_str = match.group(2).strip()
                prompt = match.group(3).strip()
            else:
                res_str = "1280x704"
                dur_str = "5s"
            
            user_identity = await permission_service.get_user_identity(internal_user.id)
            downgraded = False
            
            if user_identity in ["凡人", "外门弟子"] and dur_str == "20s":
                dur_str = "5s"
                downgraded = True
            
            base_cost = LTX_RESOLUTION_COST.get(res_str, 10)
            multiplier = LTX_DURATION_MULTIPLIER.get(dur_str, 1.0)
            cost = int(base_cost * multiplier)
            
            if downgraded:
                await query.answer(f"⚠️ 由于您的权限不足或系统限制，已将该模板自动降级为 {res_str} + {dur_str} 进行生成", show_alert=True)
            else:
                await query.answer(text="⏳ 任务初始化中...", cache_time=2)
        else:
            # Reconstruct resolution string
            if post_width and post_height:
                min_dim = min(post_width, post_height)
                if min_dim > 720:
                    res_str = "1024p"
                elif min_dim > 512:
                    res_str = "720p"
                else:
                    res_str = "512p"
            
            # Reconstruct duration string
            if post_duration:
                if post_duration > 9:
                    dur_str = "10s"
                elif post_duration > 6:
                    dur_str = "8s"
                else:
                    dur_str = "5s"
                    
            # Permission check & Auto-downgrade
            user_group = await permission_service.get_user_group(internal_user.id)
            user_identity = await permission_service.get_user_identity(internal_user.id)
            
            allowed_res = set(RESOLUTION_PERMISSIONS.get(user_group, ["512p"]) + RESOLUTION_PERMISSIONS.get(user_identity, ["512p"]))
            allowed_dur = set(DURATION_PERMISSIONS.get(user_group, ["5s"]) + DURATION_PERMISSIONS.get(user_identity, ["5s"]))
            
            downgraded = False
            if res_str not in allowed_res:
                res_str = "720p" if "720p" in allowed_res else "512p"
                downgraded = True
                
            if dur_str not in allowed_dur:
                dur_str = "8s" if "8s" in allowed_dur else "5s"
                downgraded = True
                
            # Global restriction: 1024p + 10s is not allowed together
            if res_str == "1024p" and dur_str == "10s":
                dur_str = "8s"
                downgraded = True
            
            base_cost = RESOLUTION_COST.get(res_str, 6)
            multiplier = DURATION_MULTIPLIER.get(dur_str, 1.0)
            cost = int(base_cost * multiplier)
            
            if downgraded:
                await query.answer(f"⚠️ 由于您的权限不足或系统限制，已将该模板自动降级为 {res_str} + {dur_str} 进行生成", show_alert=True)
            else:
                await query.answer(text="⏳ 任务初始化中...", cache_time=2)
    else:
        await query.answer(text="⏳ 任务初始化中...", cache_time=2)

    # Extract LoRA from prompt if any
    lora_name = None
    match = re.search(r"\[模型:\s*(.*?)\]\s*(.*)", prompt, re.DOTALL)
    if match:
        lora_name = match.group(1).strip()
        prompt = match.group(2).strip()

    context.user_data['in_conversation'] = "GALLERY_APPLY"
    context.user_data['gallery_apply_data'] = {
        'task_type': task_type,
        'prompt': prompt,
        'input_file': input_file,
        'lora_name': lora_name,
        'cost': cost,
        'res_str': res_str,
        'dur_str': dur_str,
        'is_video': post_media_type == 'video'
    }

    import html
    mode_name = MODE_NAME_MAP.get(task_type, task_type)
    msg = (
        f"🪄 <b>一键应用模板</b>：【{html.escape(mode_name)}】\n\n"
        f"原作者配置已加载。扣费标准与原模板一致 (消耗 {cost} 灵石)。\n"
        f"💡 <i>提示：应用模版的效果受初始图片影响，请尽量提供清晰、高质量的图片哦！</i>\n\n"
        f"👇 <b>请直接发送您的参考图片/人脸照片开始生成！</b>"
    )
    
    await robust_reply_text(query.message, msg, parse_mode="HTML")

    return WAIT_REFERENCE_IMAGE

async def receive_reference_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    data = context.user_data.get('gallery_apply_data')
    if not data:
        _cleanup_context(context)
        return ConversationHandler.END

    msg = update.message
    if not msg.photo and not msg.document:
        await robust_reply_text(msg, "⚠️ 请发送有效的图片文件！")
        return WAIT_REFERENCE_IMAGE

    file_id = None
    if msg.photo:
        file_id = msg.photo[-1].file_id
    elif msg.document and msg.document.mime_type and msg.document.mime_type.startswith('image/'):
        file_id = msg.document.file_id
    else:
        await robust_reply_text(msg, "⚠️ 仅支持图片格式。")
        return WAIT_REFERENCE_IMAGE

    try:
        file = await context.bot.get_file(file_id)
        file_ext = ".png"
        local_filename = f"gallery_apply_{uuid.uuid4().hex}{file_ext}"
        local_path = os.path.join(TMP_DIR, local_filename)
        await file.download_to_drive(local_path)
    except Exception as e:
        logger.error(f"Failed to download image: {e}")
        await robust_reply_text(msg, "❌ 图片下载失败，请重试。")
        return WAIT_REFERENCE_IMAGE

    task_type = data['task_type']
    is_video = data['is_video']
    prompt = data['prompt']
    cost = data['cost']
    lora_name = data['lora_name']
    res_str = data['res_str']
    dur_str = data['dur_str']
    
    # Original template files
    # History.input_file might contain multiple files separated by '|'.
    # Usually the first one is the main template.
    template_files = data['input_file'].split('|') if data['input_file'] else []
    
    # Prepare parameters for task_service
    # If task_type is face_video or face_swap, the template is the body/video.
    # The newly uploaded image is the face.
    
    chat_id = msg.chat_id
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.full_name

    # We must reset conversation state BEFORE task runs, because task_service handles it async
    _cleanup_context(context)

    # Inject resolution and duration back into context so process_generation_task reads them
    from src.constants import MODE_LTX_VIDEO
    if is_video:
        if task_type == MODE_LTX_VIDEO:
            context.user_data['ltx_video_resolution'] = res_str
            context.user_data['ltx_video_duration'] = dur_str
        else:
            context.user_data['custom_video_resolution'] = res_str
            context.user_data['custom_video_duration'] = dur_str

    # Use default menu keyboard after finishing FSM
    reply_markup = ReplyKeyboardMarkup(MAIN_MENU_KEYBOARD, resize_keyboard=True)
    sent_msg = await robust_reply_text(msg, "✅ 收到参考图，开始生成...", reply_markup=reply_markup)

    # General image/video task (like video_lora, edit_image, etc)
    # Often the template is just prepended to images or replaced.
    # If it's an I2V task, the template is the image. But here the user provides a NEW image.
    # So we just use the NEW image and the OLD prompt/lora.
    from src.handlers.fsm.edit_image_fsm import get_lora_default_strength
    lora_strength = get_lora_default_strength(lora_name)

    if task_type == MODE_I2I_PRO:
        from src.utils import create_background_task
        create_background_task(
            context,
            task_service.process_i2i_pro_task(
                context,
                chat_id,
                user_id,
                username,
                prompt,
                [local_path],
                allow_contribute=False
            )
        )
    elif task_type == MODE_LTX_VIDEO:
        from src.utils import create_background_task
        create_background_task(
            context,
            task_service.process_ltx_video_task(
                update=update,
                context=context,
                prompt=prompt,
                image_path=local_path,
                allow_contribute=False
            )
        )
    else:
        from src.utils import create_background_task
        create_background_task(
            context,
            task_service.process_generation_task(
                context=context,
                chat_id=chat_id,
                user_id=user_id,
                username=username,
                prompt=prompt,
                images=[local_path],
                is_video=is_video,
                status_msg_id=sent_msg.message_id,
                task_type=task_type,
                lora_name=lora_name,
                lora_strength=lora_strength,
                allow_contribute=False
            )
        )

    return ConversationHandler.END

async def unexpected_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text if update.message else ""
    if text and is_global_menu_command(text):
        _cleanup_context(context)
        await robust_reply_text(update.message, "🔄 已为您退出一键应用流程。\n👉 **请再次点击刚才的按钮**，即可开始新功能！")
        return ConversationHandler.END
        
    await robust_reply_text(update.message, "⚠️ 请发送一张图片，或发送 /cancel 退出。")
    return WAIT_REFERENCE_IMAGE

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    _cleanup_context(context)
    reply_markup = ReplyKeyboardMarkup(MAIN_MENU_KEYBOARD, resize_keyboard=True)
    await robust_reply_text(update.message, "✅ 已取消一键应用操作。", reply_markup=reply_markup)
    return ConversationHandler.END

def get_gallery_apply_fsm_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_gallery_apply, pattern=r'^gallery_apply_\d+$')
        ],
        states={
            WAIT_REFERENCE_IMAGE: [
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, receive_reference_image),
                MessageHandler(filters.TEXT & ~filters.COMMAND, unexpected_input)
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        allow_reentry=True
    )
