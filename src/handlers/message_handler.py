import os
import uuid
import random
import time
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import ContextTypes

from config import CHANNEL_INVITE_LINK, ENABLE_PUBLIC_SHARE, REFUGE_GROUP_ID, REFUGE_INVITE_LINK
from src.services.permission_service import permission_service
from src.services.image_service import image_service
from src.services.task_service import task_service
from src.logger import UserLogger
from src.utils import robust_reply_text, load_prompts
from src.constants import (
    TMP_DIR, TEMPLATE_DIR_PENETRATION, TEMPLATE_DIR_QUICK_FACE, TEMPLATE_DIR_VIDEO_NICE, TEMP_TEMPLATE_DIR,
    MODE_EDIT, MODE_UNDRESS, MODE_MASTURBATION,
    MODE_FACESWAP_STEP1, MODE_FACESWAP_STEP2, MODE_RANDOM_FACESWAP,
    MODE_FACE_VIDEO_STEP1, MODE_FACE_VIDEO_STEP2,
    MODE_TEMPLATE_CONTRIBUTE, MODE_NONE, MODE_CUSTOM_VIDEO, MODE_PERFECT_VIDEO_INSERT,
    MODE_DOGGY_STYLE, MODE_BLOWJOB, MODE_UNDRESS_TONGUE, MODE_CLOSEUP_BLOWJOB, MODE_I2I_PRO
)
from src.handlers.utils import _is_mentioned, with_db_logging_context

# Re-exporting for compatibility if needed, but preferred to import from constants/utils
process_generation_task = task_service.process_generation_task

os.makedirs(TMP_DIR, exist_ok=True)
os.makedirs(TEMPLATE_DIR_PENETRATION, exist_ok=True)
os.makedirs(TEMPLATE_DIR_QUICK_FACE, exist_ok=True)
os.makedirs(TEMPLATE_DIR_VIDEO_NICE, exist_ok=True)
os.makedirs(TEMP_TEMPLATE_DIR, exist_ok=True)

logger = logging.getLogger(__name__)

@with_db_logging_context
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main photo handler entry point"""
    if not _is_mentioned(update, context):
        return

    if not await permission_service.check_access(update, context):
        return

    msg = update.message
    user = update.effective_user
    username = user.username or user.full_name
    user_logger = UserLogger(user.id, username)

    mode = context.user_data.get('mode', MODE_NONE)
    
    # Check maintenance mode for generation tasks
    from src.utils import is_maintenance_mode
    if is_maintenance_mode() and mode not in [MODE_NONE, MODE_TEMPLATE_CONTRIBUTE]:
        await robust_reply_text(msg, "⚠️ 服务器即将运维，暂停生成服务中")
        return

    user_logger.log_interaction(f"Sent photo (Mode: {mode})", type="File Interaction")

    try:
        # 0. Idle State Check
        if mode == MODE_NONE:
            return await _handle_photo_idle(update, context)

        # 0.1 Template Contribution Check (Avoid double download)
        if mode == MODE_TEMPLATE_CONTRIBUTE:
            return await _handle_template_contribution(update, context)

        # 0.1.5 Check Priority for Generation Tasks
        if mode not in [MODE_NONE, MODE_TEMPLATE_CONTRIBUTE]:
            priority = await permission_service.calculate_user_priority(user.id)
            if priority <= 0:
                await robust_reply_text(msg, "⚠️ 道友，您的排队优先级已耗尽（或修为不足），今日已无法再凝聚灵力，请明日再来或提升修为！")
                return

        # 0.2 Debounce media groups for one-click modes
        one_click_modes = [MODE_UNDRESS, MODE_MASTURBATION, MODE_PERFECT_VIDEO_INSERT, MODE_DOGGY_STYLE, MODE_BLOWJOB, MODE_UNDRESS_TONGUE, MODE_CLOSEUP_BLOWJOB, MODE_RANDOM_FACESWAP, MODE_FACE_VIDEO_STEP1, MODE_FACESWAP_STEP1]
        if mode in one_click_modes and msg.media_group_id:
            if await _debounce_media_group(update, context, mode, msg.media_group_id):
                return

        # 0.3 Pre-check invalid photo uploads for specific modes
        if mode == MODE_FACE_VIDEO_STEP2:
            await robust_reply_text(msg, "❌ 请发送视频而不是图片，请发送身体视频。")
            return

        # 1. Save Photo
        if 'pending_images' not in context.user_data:
            context.user_data['pending_images'] = []
        
        photo = msg.photo[-1]
        file = await photo.get_file()
        local_path = os.path.join(TMP_DIR, f"{uuid.uuid4()}.png")
        await file.download_to_drive(local_path)
        
        abs_path = os.path.abspath(local_path)
        user_logger.logger.info(f"[User:{user.id}({username})] Temp image saved: {abs_path}")
        context.user_data['pending_images'].append(local_path)

        # 2. Dispatch by Mode
        quick_modes = {
            MODE_UNDRESS: "undress",
            MODE_MASTURBATION: "masturbation"
        }
        
        video_modes = {
            MODE_PERFECT_VIDEO_INSERT: task_service.process_perfect_video_insert_task,
            MODE_DOGGY_STYLE: task_service.process_doggy_style_task,
            MODE_BLOWJOB: task_service.process_blowjob_task,
            MODE_UNDRESS_TONGUE: task_service.process_undress_tongue_task,
            MODE_CLOSEUP_BLOWJOB: task_service.process_closeup_blowjob_task
        }
        
        if mode in quick_modes:
            await _handle_quick_task(update, context, local_path)
            context.user_data['pending_images'] = []
        elif mode in [MODE_FACESWAP_STEP1, MODE_FACESWAP_STEP2]:
            await _handle_photo_faceswap(update, context)
        elif mode in [MODE_FACE_VIDEO_STEP1, MODE_FACE_VIDEO_STEP2]:
            await _handle_photo_face_video(update, context)
        elif mode == MODE_RANDOM_FACESWAP:
            await _handle_photo_random_faceswap(update, context)
        elif mode == MODE_CUSTOM_VIDEO:
            await _handle_custom_video_setup(update, context, msg, user.id, is_document=False)
        elif mode in video_modes:
            await video_modes[mode](update, context, local_path)
            context.user_data['pending_images'] = []
        else:
            await _handle_photo_edit(update, context)
            
    except Exception as e:
        logger.error(f"Error in handle_photo for user {user.id}: {e}", exc_info=True)
        await robust_reply_text(msg, f"❌ 图片处理错误：{str(e)}")

@with_db_logging_context
async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle video uploads"""
    if not _is_mentioned(update, context):
        return

    if not await permission_service.check_access(update, context):
        return

    mode = context.user_data.get('mode', MODE_NONE)
    if mode == MODE_TEMPLATE_CONTRIBUTE:
        return await _handle_template_contribution(update, context)
    
    # Check maintenance mode for generation tasks
    from src.utils import is_maintenance_mode
    if is_maintenance_mode() and mode not in [MODE_NONE, MODE_TEMPLATE_CONTRIBUTE]:
        await robust_reply_text(update.message, "⚠️ 服务器即将运维，暂停生成服务中")
        return
    
    if mode == MODE_FACE_VIDEO_STEP2:
        await _handle_video_face_video(update, context, update.message.video, is_document=False)
        return
    elif mode == MODE_FACE_VIDEO_STEP1:
        await robust_reply_text(update.message, "❌ 请先发送【人脸图片】，不要发送视频。")
        return
    
    # Other video handling can go here if needed
    await robust_reply_text(update.message, "⚠️ 当前模式不支持视频处理。")

@with_db_logging_context
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle document uploads (images or videos as files)"""
    if not _is_mentioned(update, context):
        return

    if not await permission_service.check_access(update, context):
        return

    msg = update.message
    user = update.effective_user
    username = user.username or user.full_name
    user_logger = UserLogger(user.id, username)

    mode = context.user_data.get('mode', MODE_NONE)

    # Check maintenance mode for generation tasks
    from src.utils import is_maintenance_mode
    if is_maintenance_mode() and mode not in [MODE_NONE, MODE_TEMPLATE_CONTRIBUTE]:
        await robust_reply_text(msg, "⚠️ 服务器即将运维，暂停生成服务中")
        return

    user_logger.log_interaction(f"Sent document (Mode: {mode})", type="File Interaction")

    try:
        # 0. Idle State Check
        if mode == MODE_NONE:
            return await _handle_photo_idle(update, context)

        # 0.1 Template Contribution Check
        if mode == MODE_TEMPLATE_CONTRIBUTE:
            return await _handle_template_contribution(update, context)

        # 0.1.5 Check Priority for Generation Tasks
        if mode not in [MODE_NONE, MODE_TEMPLATE_CONTRIBUTE]:
            priority = await permission_service.calculate_user_priority(user.id)
            if priority <= 0:
                await robust_reply_text(msg, "⚠️ 道友，您的排队优先级已耗尽（或修为不足），今日已无法再凝聚灵力，请明日再来或提升修为！")
                return

        # 0.2 Debounce media groups for one-click modes
        one_click_modes = [MODE_UNDRESS, MODE_MASTURBATION, MODE_PERFECT_VIDEO_INSERT, MODE_DOGGY_STYLE, MODE_BLOWJOB, MODE_UNDRESS_TONGUE, MODE_CLOSEUP_BLOWJOB, MODE_RANDOM_FACESWAP]
        if mode in one_click_modes and msg.media_group_id:
            if await _debounce_media_group(update, context, mode, msg.media_group_id):
                return

        # 1. Save Document
        if 'pending_images' not in context.user_data:
            context.user_data['pending_images'] = []
        
        doc = msg.document
        file_ext = os.path.splitext(doc.file_name or "file")[1].lower()
        
        file = await doc.get_file()
        local_path = os.path.join(TMP_DIR, f"{uuid.uuid4()}{file_ext}")
        await file.download_to_drive(local_path)
        
        abs_path = os.path.abspath(local_path)
        user_logger.logger.info(f"[User:{user.id}({username})] Temp document saved: {abs_path}")
        context.user_data['pending_images'].append(local_path)

        # 2. Dispatch by Mode
        quick_modes = {
            MODE_UNDRESS: "undress",
            MODE_MASTURBATION: "masturbation"
        }
        
        video_modes = {
            MODE_PERFECT_VIDEO_INSERT: task_service.process_perfect_video_insert_task,
            MODE_DOGGY_STYLE: task_service.process_doggy_style_task,
            MODE_BLOWJOB: task_service.process_blowjob_task,
            MODE_UNDRESS_TONGUE: task_service.process_undress_tongue_task,
            MODE_CLOSEUP_BLOWJOB: task_service.process_closeup_blowjob_task
        }
        
        if mode in quick_modes:
            await _handle_quick_task(update, context, local_path)
            context.user_data['pending_images'] = []
        elif mode in [MODE_FACESWAP_STEP1, MODE_FACESWAP_STEP2]:
            await _handle_photo_faceswap(update, context)
        elif mode in [MODE_FACE_VIDEO_STEP1, MODE_FACE_VIDEO_STEP2]:
            # if document is video, it might be step 2
            if file_ext in ['.mp4', '.mov', '.avi'] and mode == MODE_FACE_VIDEO_STEP2:
                await _handle_video_face_video(update, context, doc, is_document=True)
            elif file_ext in ['.png', '.jpg', '.jpeg', '.webp'] and mode == MODE_FACE_VIDEO_STEP1:
                await _handle_photo_face_video(update, context)
            else:
                await robust_reply_text(msg, "❌ 格式或顺序错误。第一步请发送图片，第二步请发送视频。")
        elif mode == MODE_RANDOM_FACESWAP:
            await _handle_photo_random_faceswap(update, context)
        elif mode == MODE_CUSTOM_VIDEO:
            await _handle_custom_video_setup(update, context, msg, user.id, is_document=True)
        elif mode in video_modes:
            await video_modes[mode](update, context, local_path)
            context.user_data['pending_images'] = []
        else:
            await _handle_photo_edit(update, context)
            
    except Exception as e:
        logger.error(f"Error in handle_document for user {user.id}: {e}", exc_info=True)
        await robust_reply_text(msg, f"❌ 文件处理错误：{str(e)}")

async def _debounce_media_group(update: Update, context: ContextTypes.DEFAULT_TYPE, mode: str, media_group_id: str) -> bool:
    """Helper to debounce multiple images sent in a single media group."""
    processed_groups = context.user_data.get('processed_media_groups', set())
    if media_group_id in processed_groups:
        logger.info(f"Ignoring additional image from media group {media_group_id} for mode {mode}")
        notified_groups = context.user_data.get('notified_media_groups', set())
        if media_group_id not in notified_groups:
            await robust_reply_text(update.message, "⚠️ 提醒：为了防止刷屏，系统仅处理您的**第一张图**，其余图片已被忽略。", parse_mode='Markdown')
            notified_groups.add(media_group_id)
            context.user_data['notified_media_groups'] = notified_groups
        return True
    
    processed_groups.add(media_group_id)
    context.user_data['processed_media_groups'] = processed_groups
    return False

async def _handle_photo_idle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle photo when no mode is selected"""
    now = time.time()
    last_reminder = context.user_data.get('last_reminder_time', 0)
    if now - last_reminder < 3.0:
        return
        
    keyboard = [
        ["💎 充值灵石", "📅 每日签到", "💰 个人中心"],
        ["🤝 分享赚灵石", "⏳ 排队状态"],
        ["🖼️ 懒人P图", "🎬 懒人动图", "🎬 视频换脸"],
        ["🌟 幻想换脸", "✨ 🎨 自由P图 🎨 ✨", "🎬 自定义图生视频"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await robust_reply_text(
        update.message, 
        "⚠️ **请先选择功能模式**\n\n点击下方菜单选择您想要的功能 👇", 
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    context.user_data['last_reminder_time'] = now

async def _handle_quick_task(update: Update, context: ContextTypes.DEFAULT_TYPE, image_path: str):
    """Handle single image immediate processing for quick modes"""
    mode = context.user_data.get('mode')
    msg = update.message
    chat_id = msg.chat_id
    user = update.effective_user
    username = user.username or user.full_name
    
    # Check credits (Cost = 2)
    cost = 2
    if not await permission_service.check_quota(update, context, cost=cost):
        # Cleanup file if quota check fails
        if os.path.exists(image_path):
            try:
                os.remove(image_path)
            except Exception:
                pass
        return

    prompts_config = load_prompts()
    prompt = ""
    task_type = "image"
    final_images = [image_path]

    try:
        if mode == MODE_UNDRESS:
            prompt = prompts_config.get("undress", "undress")
            task_type = "undress"
            
        elif mode == MODE_MASTURBATION:
            prompt = prompts_config.get("masturbation", "masturbation")
            task_type = "masturbation"
            
        # Process task
        await task_service.process_generation_task(
            context, chat_id, user.id, username, 
            prompt, final_images, 
            task_type=task_type
        )
        
    except Exception as e:
        logger.error(f"Error in quick task for user {user.id}: {e}", exc_info=True)
        await robust_reply_text(msg, f"❌ 处理出错：{str(e)}")
        if os.path.exists(image_path):
            try:
                os.remove(image_path)
            except Exception:
                pass

async def _handle_photo_faceswap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle FaceSwap multi-step logic"""
    mode = context.user_data.get('mode')
    msg = update.message
    images = context.user_data['pending_images']
    prompts_config = load_prompts()

    if mode == MODE_FACESWAP_STEP1:
        context.user_data['mode'] = MODE_FACESWAP_STEP2
        await robust_reply_text(msg, "👤 收到人脸图片，请发送身体图片。")
    elif mode == MODE_FACESWAP_STEP2:
        from src.constants import TASK_COSTS
        cost = TASK_COSTS.get(MODE_FACESWAP_STEP1, 1)
        if not await permission_service.check_quota(update, context, cost=cost):
            context.user_data['pending_images'] = []
            context.user_data['mode'] = MODE_FACESWAP_STEP1
            return

        if len(images) < 2:
            await robust_reply_text(msg, "❌ 需要两张图片（人脸+身体），请重新开始。")
            context.user_data['mode'] = MODE_FACESWAP_STEP1
            context.user_data['pending_images'] = []
            return

        context.user_data['pending_images'] = []
        context.user_data['mode'] = MODE_FACESWAP_STEP1
        prompt = prompts_config.get("face_swap", "face swap")
        swapped_images = [images[1], images[0]] # Body first, Face second
        
        await task_service.process_generation_task(
            context, msg.chat_id, update.effective_user.id, 
            update.effective_user.username or update.effective_user.full_name, 
            prompt, swapped_images, task_type="face_swap"
        )

async def _handle_photo_face_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Face Video multi-step logic (Step 1: Face Photo)"""
    await robust_reply_text(update.message, "⚠️ 视频换脸功能由于底层节点升级暂时维护中，请使用其他功能。")
    context.user_data['mode'] = "none"
    context.user_data['pending_images'] = []
    return

    mode = context.user_data.get('mode')
    msg = update.message
    images = context.user_data.get('pending_images', [])
    
    if mode == MODE_FACE_VIDEO_STEP1:
        if len(images) > 0:
            logger.info(f"[User:{update.effective_user.id}] Face Video - Face image saved: {images[-1]}")
        context.user_data['mode'] = MODE_FACE_VIDEO_STEP2
        await robust_reply_text(msg, "👤 收到人脸图片，请发送身体视频（提示：视频时长会截取前5s的内容）。")
    elif mode == MODE_FACE_VIDEO_STEP2:
        await robust_reply_text(msg, "❌ 请发送视频而不是图片，请发送身体视频。")

async def _handle_video_face_video(update: Update, context: ContextTypes.DEFAULT_TYPE, video_obj, is_document=False):
    """Handle Face Video logic (Step 2: Body Video)"""
    await robust_reply_text(update.message, "⚠️ 视频换脸功能由于底层节点升级暂时维护中，请使用其他功能。")
    context.user_data['mode'] = "none"
    context.user_data['pending_images'] = []
    return

    msg = update.message
    images = context.user_data.get('pending_images', [])
    
    if len(images) < 1:
        await robust_reply_text(msg, "❌ 未找到人脸图片，请重新发送人脸图片。")
        context.user_data['mode'] = MODE_FACE_VIDEO_STEP1
        return

    # Download video
    status_msg = await robust_reply_text(msg, "⏳ 正在下载视频，请稍候...")
    try:
        file = await video_obj.get_file()
        file_ext = os.path.splitext(video_obj.file_name or "video.mp4")[1].lower() if is_document else ".mp4"
        video_local_path = os.path.join(TMP_DIR, f"{uuid.uuid4()}{file_ext}")
        await file.download_to_drive(video_local_path)
        
        # Save video path
        context.user_data['pending_images'].append(video_local_path)
        logger.info(f"[User:{update.effective_user.id}] Face Video - Video saved: {video_local_path}")
        
        # Send inline keyboard for resolution selection
        keyboard = [
            [
                InlineKeyboardButton("512p (20灵石)", callback_data="start_face_video_512"),
                InlineKeyboardButton("720p (35灵石)", callback_data="start_face_video_720"),
                InlineKeyboardButton("1024p (50灵石)", callback_data="start_face_video_1024")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await status_msg.edit_text("🎬 视频下载完成！请选择生成画质：\n\n(默认截取前121帧，约5秒时长)", reply_markup=reply_markup)
        
        # Keep mode as MODE_FACE_VIDEO_STEP2 to allow resolution selection
        context.user_data['mode'] = MODE_FACE_VIDEO_STEP2
        
    except Exception as e:
        logger.error(f"Error downloading face video: {e}", exc_info=True)
        await status_msg.edit_text(f"❌ 视频下载失败：{str(e)}")
        context.user_data['mode'] = MODE_FACE_VIDEO_STEP2

async def _handle_photo_random_faceswap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Random FaceSwap logic (User Face + Random Template Body)"""
    msg = update.message
    images = context.user_data['pending_images']
    prompts_config = load_prompts()

    from src.constants import TASK_COSTS
    cost = TASK_COSTS.get(MODE_RANDOM_FACESWAP, 1)
    if not await permission_service.check_quota(update, context, cost=cost):
        context.user_data['pending_images'] = []
        return

    if not images:
        await robust_reply_text(msg, "❌ 未收到图片，请重新开始。")
        return

    face_image_path = images[0]
    context.user_data['pending_images'] = []

    try:
        from config import MINIO_TEMPLATE_BUCKET
        from src.services.storage import storage
        
        template_files = storage.list_objects("quick_face/", bucket=MINIO_TEMPLATE_BUCKET)
        template_files = [f for f in template_files if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))]
        
        if not template_files:
            await robust_reply_text(msg, "❌ 系统错误：未找到身体模板。请联系管理员添加图片。")
            return

        random_template = random.choice(template_files)
        # Random faceswap body is images[0] (template), face is images[1] (user input)
        # So we pass [template_path, face_image_path]
        template_path = f"template:{random_template}"
        
        prompt = prompts_config.get("face_swap", "face swap")
        # images[0] is Body, images[1] is Face in process_generation_task for face_swap
        swapped_images = [template_path, face_image_path] 
        
        # 保存当前人脸图片路径到 context，以便“再来一张”功能使用
        context.user_data['last_face_image'] = face_image_path
        
        keyboard = [
            [InlineKeyboardButton("🔄 再来一张", callback_data="random_faceswap_again")],
            [
                InlineKeyboardButton("👍", callback_data="rate_like"),
                InlineKeyboardButton("👎", callback_data="rate_dislike")
            ]
        ]
        if ENABLE_PUBLIC_SHARE:
            keyboard[0].insert(0, InlineKeyboardButton("公开", callback_data="public_share_request"))
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await task_service.process_generation_task(
            context, msg.chat_id, update.effective_user.id, 
            update.effective_user.username or update.effective_user.full_name, 
            prompt, swapped_images, task_type="face_swap",
            reply_markup=reply_markup,
            cleanup=False # Keep the face image for "Again" button
        )
    except Exception as e:
        logger.error(f"Error in random faceswap: {e}", exc_info=True)
        await robust_reply_text(msg, f"❌ 任务执行出错：{str(e)}")

async def _handle_custom_video_setup(update: Update, context: ContextTypes.DEFAULT_TYPE, msg, user_id: int, is_document: bool = False):
    """Extracted logic for setting up custom video generation parameters."""
    user_group = await permission_service.get_user_group(user_id)
    user_identity = await permission_service.get_user_identity(user_id)
    
    from src.constants import get_video_settings_keyboard, DEFAULT_RESOLUTION, DEFAULT_DURATION, RESOLUTION_COST, DURATION_MULTIPLIER
    current_resolution = context.user_data.get('custom_video_resolution', DEFAULT_RESOLUTION)
    current_duration = context.user_data.get('custom_video_duration', DEFAULT_DURATION)
    reply_markup = get_video_settings_keyboard(user_group, user_identity, current_resolution, current_duration)
    
    base_cost = RESOLUTION_COST.get(current_resolution, 6)
    multiplier = DURATION_MULTIPLIER.get(current_duration, 1.0)
    cost = int(base_cost * multiplier)
    
    msg_text = f"⚙️ 当前自定义视频画质：{current_resolution} | 时长：{current_duration} | 消耗灵石：{cost}\n\n请选择您需要的画质和时长（部分画质和时长需要高境界或VIP身份解锁）：\n\n*提示：画质越高、时长越长，消耗灵石越多。注意：1024p 和 10s 无法同时选择。*"
    
    file_type_str = "（文件）" if is_document else ""
    await robust_reply_text(msg, f"📥 收到起始图片{file_type_str}。请发送提示词 (Text) 以生成 5 秒视频。")
    await robust_reply_text(msg, msg_text, reply_markup=reply_markup)

async def _handle_photo_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle default Edit mode"""
    msg = update.message
    
    # Check how many images we already have
    pending_count = len(context.user_data.get('pending_images', []))
    mode = context.user_data.get('mode')
    
    if pending_count >= 1:
        if mode == MODE_I2I_PRO:
            await robust_reply_text(msg, "✅ 已收到 1 张参考图。\n请直接发送提示词 (Text) 开始生成。\n\n💡 **提示词要求**：\n描述幻想的人物和场景，后续会将参考图中的人物换脸到幻想的场景人物中。")
        else:
            await robust_reply_text(msg, "✅ 已收到 1 张参考图。请直接发送提示词 (Text) 开始生成。")
    else:
        if mode == MODE_I2I_PRO:
            await robust_reply_text(msg, "📥 收到图片。\n请直接发送提示词 (Text) 开始生成。\n\n💡 **提示词要求**：\n描述幻想的人物和场景，后续会将参考图中的人物换脸到幻想的场景人物中。")
        else:
            await robust_reply_text(msg, "📥 收到图片。请直接发送提示词 (Text) 开始生成。")

async def _handle_template_contribution(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle template contribution (Save to templates/temps/)"""
    msg = update.message
    user = update.effective_user
    username = user.username or user.full_name
    
    # 1. Determine file type and get file object
    file_id = None
    file_ext = ".png"
    file_type_name = "图片"
    
    if msg.photo:
        file_id = msg.photo[-1].file_id
        file_ext = ".png"
        file_type_name = "图片"
    elif msg.video:
        file_id = msg.video.file_id
        file_ext = os.path.splitext(msg.video.file_name or "video.mp4")[1] or ".mp4"
        file_type_name = "视频"
    elif msg.document:
        file_id = msg.document.file_id
        file_ext = os.path.splitext(msg.document.file_name or "file")[1]
        file_type_name = "文件"
    
    if not file_id:
        return

    # 2. Download and save
    try:
        file = await context.bot.get_file(file_id)
        local_filename = f"{user.id}_{uuid.uuid4().hex}{file_ext}"
        local_path = os.path.join(TEMP_TEMPLATE_DIR, local_filename)
        await file.download_to_drive(local_path)
        
        # Upload to MinIO
        from config import MINIO_TEMPLATE_BUCKET
        from src.services.storage import storage
        minio_object_name = f"temps/{local_filename}"
        storage.upload_file(local_path, minio_object_name, bucket=MINIO_TEMPLATE_BUCKET)
        
        # 3. Record in Database
        file_type_db = 'photo'
        if msg.video:
            file_type_db = 'video'
        elif msg.document:
            file_type_db = 'document'
        
        await permission_service.record_contribution(user.id, local_path, file_type_db)
        
        # 4. Track count in user_data (for session feedback)
        if 'contributed_count' not in context.user_data:
            context.user_data['contributed_count'] = 0
        context.user_data['contributed_count'] += 1
        
        count = context.user_data['contributed_count']
        await robust_reply_text(msg, f"✅ 已经收到 {count} 张图片/视频，待审核收入模板库。")
        
        logger.info(f"[Template Contribution] User {user.id}({username}) saved {file_type_name}: {local_path} (Recorded in DB)")
    except Exception as e:
        logger.error(f"Error saving template contribution: {e}", exc_info=True)
        await robust_reply_text(msg, f"❌ 保存失败：{str(e)}")

@with_db_logging_context
async def handle_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages and menu commands"""
    if not await permission_service.check_access(update, context):
        return

    text = update.message.text
    
    # --- New Menu Navigation Logic ---
    if text == "🖼️ 懒人P图":
        keyboard = [
            ["💃 快速脱衣", "🎭 快速换脸", "🥵 快速自慰"],
            ["🎭 随机换脸"],
            ["🔙 返回主菜单"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await robust_reply_text(update.message, "🖼️ **懒人P图模式**\n请选择具体功能：", reply_markup=reply_markup, parse_mode="Markdown")
        return

    if text == "🎬 懒人动图":
        keyboard = [
            ["🛌 动图传教士", "🎬 动图后入"],
            ["🎬 口交黑人", "🎬 脱衣吐舌", "🎬 特写口交"],
            ["🔙 返回主菜单"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await robust_reply_text(update.message, "🎬 **懒人动图**\n请选择演武场景：", reply_markup=reply_markup, parse_mode="Markdown")
        return

    if text == "🔙 返回主菜单":
        keyboard = [
            ["💎 充值灵石", "📅 每日签到", "👤 个人中心"],
            ["🤝 分享赚灵石", "⏳ 排队状态"],
            ["🖼️ 懒人P图", "🎬 懒人动图", "🎬 视频换脸"],
            ["🌟 幻想换脸", "🎨 自由P图 ", "🎬 自定义图生视频"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await robust_reply_text(update.message, "🏠 **已返回主菜单**", reply_markup=reply_markup, parse_mode="Markdown")
        return
    # ---------------------------------
    
    # Menu Commands
    if text == "💎 充值灵石":
        from telegram import WebAppInfo
        from config import WEBAPP_URL
        
        # 默认 WebApp URL
        webapp_url = WEBAPP_URL if 'WEBAPP_URL' in globals() and WEBAPP_URL else "https://pay.aivison.it.com/"
        
        keyboard = [
            [InlineKeyboardButton("💎 TON月卡套餐", web_app=WebAppInfo(url=webapp_url))],
            [InlineKeyboardButton("⭐️ Star月卡套餐", callback_data="recharge_stars_menu")],
            [InlineKeyboardButton("⭐️ Star直充灵石", callback_data="recharge_stars_credit_menu")],
            [InlineKeyboardButton("¥ 人民币充值月卡", callback_data="recharge_rmb_menu")],
            [InlineKeyboardButton("¥ 人民币直充灵石", callback_data="recharge_rmb_credit_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        msg = (
            "📜 **【合欢宗账房】灵石充值与身份晋升**\n\n"
            "欢迎来到合欢宗账房！灵石乃修仙界之硬通货，可用以驱动阵法（生成图像与视频）。\n\n"
            "🔰 **【内门弟子】** 1.99 TON / ¥ 30.00\n"
            "   └ 🎁 直接获得 `400` 灵石\n"
            "   └ 📅 每日签到 `+30` 灵石\n"
            "   └ 🔓 解锁特权 `720p` 画质，最长 `8s` 视频\n"
            "   └ ⚡ 排队优先级 `+15`\n\n"
            "💠 **【核心弟子】** 4.99 TON / ¥ 70.00\n"
            "   └ 🎁 直接获得 `1200` 灵石\n"
            "   └ 📅 每日签到 `+40` 灵石\n"
            "   └ 🔓 解锁特权 `1024p` 画质，最长 `10s` 视频\n"
            "   └ ⚡ 排队优先级 `+25`\n\n"
            "👑 **【真传弟子】** 9.99 TON / ¥ 120.00\n"
            "   └ 🎁 直接获得 `3000` 灵石\n"
            "   └ 📅 每日签到 `+50` 灵石\n"
            "   └ 🔓 解锁特权 `1024p` 画质，最长 `10s` 视频\n"
            "   └ 🚀 排队优先级 `+40` (极速)\n\n"
            "⚠️ **注意事项**：\n"
            "1. 充值所获灵石与身份特权，一经交付，不可退换。\n\n"
            "👇 **请选择您的支付法门**："
        )
        await robust_reply_text(update.message, msg, parse_mode="Markdown", reply_markup=reply_markup)
        return

    if text in ["💰 个人中心", "👤 个人中心"]:
        # 强制同步频道状态，确保“凡人”->“练气期”及时更新
        await permission_service.sync_channel_status(update, context)
        await permission_service.ensure_user(update)
        user_id = update.effective_user.id
        stats = await permission_service.get_user_detailed_stats(user_id)
        
        # 动态生成突破条件
        breakthrough_msg = ""
        current_group = stats['group']
        current_identity = stats.get('identity', '普通用户')
        current_priority = stats.get('priority', 0)
        
        if current_group == "凡人":
            invite_link = CHANNEL_INVITE_LINK or "https://t.me/AiVisionAV"
            breakthrough_msg = (
                "🚀 **突破至练气期条件**：\n"
                f"🔸 拜入宗门 [👉 [点击即刻拜入]({invite_link})]"
            )
        elif current_group == "练气期":
            inv_done = "✅" if stats['invitations'] > 1 else "❌"
            checkin_done = "✅" if stats['checkins'] > 3 else "❌"
            gen_done = "✅" if stats['generations'] > 10 else "❌"
            
            breakthrough_msg = (
                "🚀 **突破至筑基期(视野更加清晰了)条件**：\n"
                f"🔸 邀请道友 > 1人 ({inv_done})\n"
                f"🔸 累计签到 > 3天 ({checkin_done})\n"
                f"🔸 修炼次数 > 10次 ({gen_done})"
            )
        elif current_group == "筑基期":
            inv_done = "✅" if stats['invitations'] > 10 else "❌"
            checkin_done = "✅" if stats['checkins'] > 30 else "❌"
            gen_done = "✅" if stats['generations'] > 100 else "❌"
            
            breakthrough_msg = (
                "🚀 **突破至金丹期条件**：\n"
                f"🔸 邀请道友 > 10人 ({inv_done})\n"
                f"🔸 累计签到 > 30天 ({checkin_done})\n"
                f"🔸 修炼次数 > 100次 ({gen_done})"
            )
        elif current_group == "金丹期":
            inv_done = "✅" if stats['invitations'] > 100 else "❌"
            checkin_done = "✅" if stats['checkins'] > 300 else "❌"
            gen_done = "✅" if stats['generations'] > 1000 else "❌"
            
            breakthrough_msg = (
                "🚀 **突破至元婴期条件**：\n"
                f"🔸 邀请道友 > 100人 ({inv_done})\n"
                f"🔸 累计签到 > 300天 ({checkin_done})\n"
                f"🔸 修炼次数 > 1000次 ({gen_done})"
            )
        elif current_group == "元婴期":
            breakthrough_msg = "✨ **已修成元婴，神通广大，万法不侵**"

        identity_display = f"`{current_identity}`"
        if current_identity != "外门弟子" and stats.get('identity_expire_at'):
            from datetime import datetime
            now = datetime.now()
            expire_at = stats['identity_expire_at']
            
            # 兼容可能的 timezone aware datetime
            if expire_at.tzinfo is not None:
                expire_at = expire_at.replace(tzinfo=None)
                
            if expire_at > now:
                remaining = expire_at - now
                days = remaining.days
                hours = remaining.seconds // 3600
                expire_str = expire_at.strftime('%Y-%m-%d %H:%M')
                if days > 0:
                    identity_display += f" (剩余 {days} 天，{expire_str} 到期)"
                else:
                    identity_display += f" (剩余 {hours} 小时，{expire_str} 到期)"
            else:
                identity_display += " (已过期)"

        msg = (
            f"👤 **道友**：`{update.effective_user.first_name}`\n"
            f"📜 **修为**：`{current_group}`\n"
            f"🪪 **身份**：{identity_display}\n"
            f"⚡ **排队加速**：`+{current_priority}` 优先级\n"
            f"💰 **灵石余额**：`{stats['credits']}`\n\n"
            f"📊 **修炼数据**：\n"
            f"  - 邀请同道：`{stats['invitations']}` 人\n"
            f"  - 累计签到：`{stats['checkins']}` 天\n"
            f"  - 施法次数：`{stats['generations']}` 次\n\n"
            f"🤝 **邀请数据**：\n"
            f"  - 邀请充值：已有 `{stats['invitation_recharge']['recharged_invitees_count']}` 位道友完成 `{stats['invitation_recharge']['total_recharge_count']}` 次充值\n"
            f"  - 累积充值：`{stats['invitation_recharge']['total_ton']:.2f}` TON\n"
            f"  - 累积贡献：`{stats['invitation_recharge']['total_stars']}` Stars\n\n"
            f"💡 *提示：1点加速优先级约等于为您节约1分钟的排队时间。*\n\n"
            f"{breakthrough_msg}"
        )
        
        await robust_reply_text(update.message, msg, parse_mode="Markdown")
        return

    if text in ["📅 每日签到", "签到", "/checkin"]:
        # 检查是否加入避难所群组
        if REFUGE_GROUP_ID:
            try:
                group_id = int(REFUGE_GROUP_ID) if REFUGE_GROUP_ID.lstrip('-').isdigit() else REFUGE_GROUP_ID
                member = await context.bot.get_chat_member(chat_id=group_id, user_id=update.effective_user.id)
                if member.status in ['left', 'kicked', 'banned']:
                    link = REFUGE_INVITE_LINK or "https://t.me/+J0velHHqUF01NGM1"
                    keyboard = [[InlineKeyboardButton("🛡️ 点击加入避难所", url=link)]]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    msg = (
                        "🛡️ **避难所签到检测**\n\n"
                        "道友，检测到您尚未加入【合欢宗避难所】。\n"
                        "**加入避难所，防封不迷路！**\n\n"
                        "请先加入避难所后，再来进行每日签到领取奖励吧！"
                    )
                    await robust_reply_text(update.message, msg, parse_mode="Markdown", reply_markup=reply_markup)
                    return
            except Exception as e:
                logger.warning(f"Failed to check refuge group membership: {e}")
                # 忽略错误继续签到流程
        
        success, current_credits, error_msg, total_days, reward = await permission_service.perform_checkin(update)
        user_group = await permission_service.get_user_group(update.effective_user.id)
        user_identity = await permission_service.get_user_identity(update.effective_user.id)
        
        # 优化后的免责声明
        disclaimer = "\n\n⚠️ _注：累计签到统计始于3月5日，此前的数据未计入系统。_"
        
        if success:
            reward_msg = f"`{reward}` 灵石"
            await robust_reply_text(update.message, f"✅ **签到成功！**\n\n👤 当前境界：`{user_group}`\n🪪 当前身份：`{user_identity}`\n📅 累计签到：`{total_days}` 天\n🎉 本次获得：{reward_msg}\n💰 当前总灵石：`{current_credits}`" + disclaimer, parse_mode="Markdown")
        elif error_msg:
            await robust_reply_text(update.message, error_msg, parse_mode="Markdown")
        else:
            await robust_reply_text(update.message, f"📅 **今日已领取灵石**\n\n👤 当前境界：`{user_group}`\n🪪 当前身份：`{user_identity}`\n📅 累计签到：`{total_days}` 天\n\n请明天再来领取奖励吧！" + disclaimer, parse_mode="Markdown")
        return

    if text == "🤝 分享赚灵石":
        user_id = update.effective_user.id
        bot_username = context.bot.username or (await context.bot.get_me()).username
        invite_link = f"https://t.me/{bot_username}?start={user_id}"
        count = await permission_service.get_referral_count(user_id)
        user_group = await permission_service.get_user_group(user_id)
        msg = (
            "🤝 **分享赚灵石**\n\n"
            f"👤 **当前等级**：`{user_group}`\n"
            f"🔗 **您的专属链接**：\n`{invite_link}`\n\n"
            "📈 **邀请统计**：\n"
            f"👥 已邀请人数：`{count}` 人\n"
            "💡 **规则**：\n"
            "每成功邀请一位**新道友**使用机器人，您将自动获得 **5 灵石**奖励！\n"
            "**新道友**加入宗门，您将自动获得 **10 灵石**奖励！\n"
        )
        await robust_reply_text(update.message, msg, parse_mode="Markdown")
        return

    if text in ["⏳ 排队状态", "排队", "/queue"]:
        status = await image_service.get_queue_info()
        if status:
             queue_by_type = status.get('queue_by_type', {})
             msg = (
                 "📊 **宗门灵气损耗现状**\n\n"
                 f"👥 总排队任务：`{status.get('queue_size', 0)}` 个\n"
                 f"🎨 图生图：`{queue_by_type.get('img2img', 0)}` 个\n"
                 f"🎭 人脸替换：`{queue_by_type.get('face_swap', 0)}` 个\n"
                 f"🎬 视频插入：`{queue_by_type.get('video_insert', 0)}` 个\n"
                 f"🎬 视频编辑（通用）：`{queue_by_type.get('video_edit', 0)}` 个"
             )
             await robust_reply_text(update.message, msg, parse_mode="Markdown")
        else:
             await robust_reply_text(update.message, "⚠️ 无法获取实时排队数据，请稍后再试。")
        return
    
    # Mode Switching Commands
    mode_map = {
        "💃 快速脱衣": (MODE_UNDRESS, "💃 已切换到【快速脱衣】模式 (消耗 2 灵石)。\n请发送一张图片，我将自动处理。"),
        "🎭 快速换脸": (MODE_FACESWAP_STEP1, "🎭 已切换到【快速换脸】模式 (消耗 1 灵石)。\n请先发送一张【人脸】图片。"),
        "🎭 随机换脸": (MODE_RANDOM_FACESWAP, "🎭 已切换到【随机换脸】模式 (消耗 1 灵石)。\n请发送一张【人脸】图片，我将自动匹配模板处理。"),
        "🥵 快速自慰": (MODE_MASTURBATION, "🥵 已切换到【快速自慰】模式 (消耗 2 灵石)。\n请发送一张图片，我将自动处理。"),
        "🎨 自由P图": (MODE_EDIT, "🎨 已切换到【自由P图】模式 (消耗 2 灵石)。\n请发送 1 张参考图片，随后发送提示词开始融合生成。"),
        "🎬 自定义图生视频": (MODE_CUSTOM_VIDEO, "🎬 已切换到【自定义图生视频】模式。\n请发送一张【起始图片】。\n(注意：该模式生成 5 秒视频，请确保提示词动作逻辑合理)"),
        "🛌 动图传教士": (MODE_PERFECT_VIDEO_INSERT, "🛌 已切换到【动图传教士】模式。\n请发送一张【人脸】图片（正面、清晰），我将自动处理。"),
        "🎬 动图后入": (MODE_DOGGY_STYLE, "🎬 已切换到【动图后入】模式。\n请发送一张【人脸】图片（正面、清晰），我将自动处理。"),
        "🎬 视频换脸": (MODE_FACE_VIDEO_STEP1, "🎬 已切换到【视频换脸】模式。\n请先发送一张【人脸】图片。"),
        "🎬 口交黑人": (MODE_BLOWJOB, "🎬 已切换到【口交黑人】模式。\n请发送一张【正面清晰图片】，我将自动处理。"),
        "🎬 脱衣吐舌": (MODE_UNDRESS_TONGUE, "🎬 已切换到【脱衣吐舌】模式。\n请发送一张【正面清晰图片】，我将自动处理。"),
        "🎬 特写口交": (MODE_CLOSEUP_BLOWJOB, "🎬 已切换到【特写口交】模式。\n请发送一张【正面清晰图片】，我将自动处理。"),
        "🌟 幻想换脸": (MODE_I2I_PRO, "🌟 已切换到【幻想换脸】模式 (消耗 6 灵石)。\n请发送 1 张参考图片，随后发送提示词开始生成。")
    }
    
    if text == "📝 文生图":
        await robust_reply_text(update.message, "⚠️ 文生图功能已替换为图生图Pro，请使用其他功能。")
        return

    if text == "🎬 视频换脸":
        await robust_reply_text(update.message, "⚠️ 视频换脸功能由于底层节点升级暂时维护中，请使用其他功能。")
        return

    if text in mode_map:
        new_mode, reply = mode_map[text]
        context.user_data['mode'] = new_mode
        context.user_data['pending_images'] = []
        context.user_data['contributed_count'] = 0 # Reset count when switching mode
        
        if new_mode in [MODE_CUSTOM_VIDEO, MODE_PERFECT_VIDEO_INSERT, MODE_DOGGY_STYLE, MODE_BLOWJOB, MODE_UNDRESS_TONGUE, MODE_CLOSEUP_BLOWJOB]:
            user_group = await permission_service.get_user_group(update.effective_user.id)
            user_identity = await permission_service.get_user_identity(update.effective_user.id)
            from src.constants import get_video_settings_keyboard, DEFAULT_RESOLUTION, DEFAULT_DURATION, RESOLUTION_COST, DURATION_MULTIPLIER
            current_resolution = context.user_data.get('custom_video_resolution', DEFAULT_RESOLUTION)
            current_duration = context.user_data.get('custom_video_duration', DEFAULT_DURATION)
            reply_markup = get_video_settings_keyboard(user_group, user_identity, current_resolution, current_duration)
            
            base_cost = RESOLUTION_COST.get(current_resolution, 6)
            multiplier = DURATION_MULTIPLIER.get(current_duration, 1.0)
            cost = int(base_cost * multiplier)
            
            reply += f"\n\n⚙️ 当前视频画质：{current_resolution} | 时长：{current_duration} | 消耗灵石：{cost}\n请在下方选择您需要的画质和时长（部分画质和时长需要高境界或VIP身份解锁）：\n\n*提示：画质越高、时长越长，消耗灵石越多。注意：1024p 和 10s 无法同时选择。*"
            await robust_reply_text(update.message, reply, reply_markup=reply_markup)
        else:
            await robust_reply_text(update.message, reply)
        return

    # Generation Handling
    if not _is_mentioned(update, context):
        return

    mode = context.user_data.get('mode', MODE_EDIT)
    images = context.user_data.get('pending_images', [])
    
    # Do not treat text commands as generation prompts if they match button texts
    if text in ["� 充值灵石", "�� 每日签到", "👤 个人中心", "💰 个人中心", "🤝 分享赚灵石", "⏳ 排队状态", "签到", "排队", "/queue", "/checkin", "🔙 返回主菜单", "/start", "/help"]:
        return

    if not images:
        await robust_reply_text(update.message, "请先发送一张图片。")
        return

    # In single image mode, we only care about the last sent valid image
    valid_images = [path for path in images if os.path.exists(path)]
    if not valid_images:
        await robust_reply_text(update.message, "❌ 图片已丢失，请重新发送图片。")
        return
    
    # Force single image for all modes
    valid_images = [valid_images[-1]]

    # Execute Generation
    from src.utils import is_maintenance_mode
    if is_maintenance_mode():
        await robust_reply_text(update.message, "⚠️ 服务器即将运维，暂停生成服务中")
        return

    chat_id = update.message.chat_id
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.full_name

    # Check Priority
    priority = await permission_service.calculate_user_priority(user_id)
    if priority <= 0:
        await robust_reply_text(update.message, "⚠️ 道友，您的排队优先级已耗尽（或修为不足），今日已无法再凝聚灵力，请明日再来或提升修为！")
        # Clear pending images if they had any
        context.user_data['pending_images'] = []
        return
    
    if mode == MODE_CUSTOM_VIDEO:
        # 自定义图生视频
        if len(valid_images) != 1:
            await robust_reply_text(update.message, "❌ 需要且仅能发送一张起始图片，请重新发送。")
            context.user_data['pending_images'] = []
            return
        await task_service.process_custom_video_task(update, context, text, valid_images[0])
    elif mode == MODE_I2I_PRO:
        await task_service.process_i2i_pro_task(context, chat_id, user_id, username, text, valid_images)
    else:
        # Default Edit/Generation
        is_video = False
        task_type = "image"
        # Determine task type from mode if possible to avoid fallback to img2img
        if mode in [MODE_FACESWAP_STEP1, MODE_FACESWAP_STEP2, MODE_RANDOM_FACESWAP]:
            task_type = "face_swap"
        elif mode == MODE_UNDRESS:
            task_type = "undress"
        elif mode == MODE_MASTURBATION:
            task_type = "masturbation"
            
        await task_service.process_generation_task(
            context, chat_id, user_id, username, text, valid_images, 
            is_video=is_video, task_type=task_type
        )

    # Clear pending after generation
    context.user_data['pending_images'] = []
