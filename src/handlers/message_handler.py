import os
import uuid
import random
import time
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import ContextTypes

from config import REQUIRED_CHANNEL_ID, CHANNEL_INVITE_LINK, REFUGE_GROUP_ID, REFUGE_INVITE_LINK
from src.services.permission_service import permission_service
from src.services.image_service import image_service
from src.services.task_service import task_service
from src.logger import UserLogger
from src.utils import robust_reply_text, robust_send_message, robust_edit_text, robust_send_photo, robust_delete_message, robust_send_video, load_prompts
from src.constants import (
    TMP_DIR, TEMPLATE_DIR_PENETRATION, TEMPLATE_DIR_QUICK_FACE, TEMPLATE_DIR_VIDEO_NICE, TEMP_TEMPLATE_DIR,
    MODE_EDIT, MODE_UNDRESS, MODE_MASTURBATION,
    MODE_FACESWAP_STEP1, MODE_FACESWAP_STEP2, MODE_RANDOM_FACESWAP,
    MODE_PENETRATION_STEP1, MODE_PENETRATION_STEP2,
    MODE_TEMPLATE_CONTRIBUTE, MODE_NONE, MODE_CUSTOM_VIDEO, MODE_PERFECT_VIDEO_INSERT,
    MODE_DOGGY_STYLE, MODE_BLOWJOB, MODE_UNDRESS_TONGUE, MODE_CLOSEUP_BLOWJOB, MODE_TEXT_TO_IMAGE
)
from src.handlers.utils import _is_mentioned, MockMessage, with_db_logging_context

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
    user_logger.log_interaction(f"Sent photo (Mode: {mode})", type="File Interaction")

    try:
        # 0. Idle State Check
        if mode == MODE_NONE:
            return await _handle_photo_idle(update, context)

        # 0.1 Template Contribution Check (Avoid double download)
        if mode == MODE_TEMPLATE_CONTRIBUTE:
            return await _handle_template_contribution(update, context)

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
        if mode in [MODE_UNDRESS, MODE_MASTURBATION]:
            await _handle_quick_task(update, context, local_path)
            context.user_data['pending_images'] = []
        elif mode in [MODE_FACESWAP_STEP1, MODE_FACESWAP_STEP2]:
            await _handle_photo_faceswap(update, context)
        elif mode == MODE_RANDOM_FACESWAP:
            await _handle_photo_random_faceswap(update, context)
        elif mode == MODE_CUSTOM_VIDEO:
            await robust_reply_text(msg, "📥 收到起始图片。请发送提示词 (Text) 以生成 5 秒视频。")
        elif mode == MODE_PERFECT_VIDEO_INSERT:
            # 动图传教士：收到图片直接开始生成
            await task_service.process_perfect_video_insert_task(update, context, local_path)
            context.user_data['pending_images'] = []
        elif mode == MODE_DOGGY_STYLE:
            # 动图后入：收到图片直接开始生成
            await task_service.process_doggy_style_task(update, context, local_path)
            context.user_data['pending_images'] = []
        elif mode == MODE_BLOWJOB:
            # 口交黑人：收到图片直接开始生成
            await task_service.process_blowjob_task(update, context, local_path)
            context.user_data['pending_images'] = []
        elif mode == MODE_UNDRESS_TONGUE:
            # 脱衣吐舌：收到图片直接开始生成
            await task_service.process_undress_tongue_task(update, context, local_path)
            context.user_data['pending_images'] = []
        elif mode == MODE_CLOSEUP_BLOWJOB:
            # 特写口交：收到图片直接开始生成
            await task_service.process_closeup_blowjob_task(update, context, local_path)
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
    user_logger.log_interaction(f"Sent document (Mode: {mode})", type="File Interaction")

    try:
        # 0. Idle State Check
        if mode == MODE_NONE:
            return await _handle_photo_idle(update, context)

        # 0.1 Template Contribution Check
        if mode == MODE_TEMPLATE_CONTRIBUTE:
            return await _handle_template_contribution(update, context)

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
        if mode in [MODE_UNDRESS, MODE_MASTURBATION]:
            await _handle_quick_task(update, context, local_path)
            context.user_data['pending_images'] = []
        elif mode in [MODE_FACESWAP_STEP1, MODE_FACESWAP_STEP2]:
            await _handle_photo_faceswap(update, context)
        elif mode == MODE_RANDOM_FACESWAP:
            await _handle_photo_random_faceswap(update, context)
        elif mode == MODE_CUSTOM_VIDEO:
            await robust_reply_text(msg, "📥 收到起始图片（文件）。请发送提示词 (Text) 以生成 5 秒视频。")
        elif mode == MODE_PERFECT_VIDEO_INSERT:
            await task_service.process_perfect_video_insert_task(update, context, local_path)
            context.user_data['pending_images'] = []
        elif mode == MODE_DOGGY_STYLE:
            await task_service.process_doggy_style_task(update, context, local_path)
            context.user_data['pending_images'] = []
        elif mode == MODE_BLOWJOB:
            await task_service.process_blowjob_task(update, context, local_path)
            context.user_data['pending_images'] = []
        elif mode == MODE_UNDRESS_TONGUE:
            await task_service.process_undress_tongue_task(update, context, local_path)
            context.user_data['pending_images'] = []
        elif mode == MODE_CLOSEUP_BLOWJOB:
            await task_service.process_closeup_blowjob_task(update, context, local_path)
            context.user_data['pending_images'] = []
        else:
            await _handle_photo_edit(update, context)
            
    except Exception as e:
        logger.error(f"Error in handle_document for user {user.id}: {e}", exc_info=True)
        await robust_reply_text(msg, f"❌ 文件处理错误：{str(e)}")

async def _handle_photo_idle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle photo when no mode is selected"""
    now = time.time()
    last_reminder = context.user_data.get('last_reminder_time', 0)
    if now - last_reminder < 3.0:
        return
        
    keyboard = [
        ["📅 每日签到", "💰 个人中心", "🤝 分享赚灵石", "⏳ 排队状态"],
        ["🖼️ 懒人P图", "🎬 懒人动图"],
        ["📝 文生图", "✨ 🎨 自由P图 🎨 ✨", "🎬 自定义图生视频"]
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
            try: os.remove(image_path)
            except: pass
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
            try: os.remove(image_path)
            except: pass

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
        if not await permission_service.check_quota(update, context, cost=2):
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

async def _handle_photo_random_faceswap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Random FaceSwap logic (User Face + Random Template Body)"""
    msg = update.message
    images = context.user_data['pending_images']
    prompts_config = load_prompts()

    if not await permission_service.check_quota(update, context, cost=2):
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
        
        reply_markup = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("公开", callback_data="public_share_request"),
                InlineKeyboardButton("🔄 再来一张", callback_data="random_faceswap_again")
            ]
        ])
        
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

async def _handle_photo_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle default Edit mode"""
    msg = update.message
    
    # Check how many images we already have
    pending_count = len(context.user_data.get('pending_images', []))
    
    if pending_count > 1:
        await robust_reply_text(msg, "⚠️ 已收到多张图片。当前模式仅最后一张图片会生效，请直接发送提示词 (Text) 开始生成。")
    else:
        await robust_reply_text(msg, "📥 收到图片。请发送提示词 (Text) 开始生成。")

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
        
        # 3. Record in Database
        file_type_db = 'photo'
        if msg.video: file_type_db = 'video'
        elif msg.document: file_type_db = 'document'
        
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
            ["🎭 随机换脸", "🎁 模板共建"],
            ["🔙 返回主菜单"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await robust_reply_text(update.message, "🖼️ **懒人P图模式**\n请选择具体功能：", reply_markup=reply_markup, parse_mode="Markdown")
        return

    if text in ["🎬 懒人动图", ]:
        keyboard = [
            ["🛌 动图传教士", "🎬 动图后入"],
            ["🎬 口交黑人", "🎬 脱衣吐舌","🎬 特写口交"],
            ["🔙 返回主菜单"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await robust_reply_text(update.message, "🎬 **懒人动图**\n请选择演武场景：", reply_markup=reply_markup, parse_mode="Markdown")
        return

    if text == "🔙 返回主菜单":
        keyboard = [
            ["📅 每日签到", "👤 个人中心", "🤝 分享赚灵石", "⏳ 排队状态"],
            ["🖼️ 懒人P图", "🎬 懒人动图"],
            ["📝 文生图", "🎨 自由P图 ", "🎬 自定义图生视频"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await robust_reply_text(update.message, "🏠 **已返回主菜单**", reply_markup=reply_markup, parse_mode="Markdown")
        return
    # ---------------------------------
    
    # Menu Commands
    if text in ["💰 个人中心", "👤 个人中心"]:
        # 强制同步频道状态，确保“凡人”->“练气期”及时更新
        await permission_service.sync_channel_status(update, context)
        await permission_service.ensure_user(update)
        user_id = update.effective_user.id
        stats = await permission_service.get_user_detailed_stats(user_id)
        
        # 动态生成突破条件
        breakthrough_msg = ""
        current_group = stats['group']
        
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
            breakthrough_msg = "✨ **已登峰造极，成就金丹大道**"

        
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
        
        success, current_credits, error_msg, total_days = await permission_service.perform_checkin(update)
        user_group = await permission_service.get_user_group(update.effective_user.id)
        
        # 优化后的免责声明
        disclaimer = "\n\n⚠️ _注：累计签到统计始于3月5日，此前的数据未计入系统。_"
        
        if success:
            await robust_reply_text(update.message, f"✅ **签到成功！**\n\n👤 当前境界：`{user_group}`\n📅 累计签到：`{total_days}` 天\n🎉 本次获得：`5` 永久灵石 + `15` 临时灵石\n💰 当前总灵石：`{current_credits}`" + disclaimer, parse_mode="Markdown")
        elif error_msg:
            await robust_reply_text(update.message, error_msg, parse_mode="Markdown")
        else:
            await robust_reply_text(update.message, f"📅 **今日已领取灵石**\n\n👤 当前境界：`{user_group}`\n📅 累计签到：`{total_days}` 天\n\n请明天再来领取奖励吧！" + disclaimer, parse_mode="Markdown")
        return

    if text == "🤝 分享赚灵石":
        user_id = update.effective_user.id
        bot_username = context.bot.username or (await context.bot.get_me()).username
        invite_link = f"https://t.me/{bot_username}?start={user_id}"
        count = await permission_service.get_referral_count(user_id)
        user_group = await permission_service.get_user_group(user_id)
        earned = count * 20
        msg = (
            "🤝 **分享赚灵石**\n\n"
            f"👤 **当前等级**：`{user_group}`\n"
            f"🔗 **您的专属链接**：\n`{invite_link}`\n\n"
            "📈 **邀请统计**：\n"
            f"👥 已邀请人数：`{count}` 人\n"
            f"💰 累计获得奖励：`{earned}` 灵石\n\n"
            "💡 **规则**：\n"
            "每成功邀请一位**新道友**使用机器人，您将自动获得 **5 灵石**奖励！\n"
            "**新道友**加入宗门，您将自动获得 **20 灵石**奖励！\n"
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
        "🎭 快速换脸": (MODE_FACESWAP_STEP1, "🎭 已切换到【快速换脸】模式 (消耗 2 灵石)。\n请先发送一张【人脸】图片。"),
        "🎭 随机换脸": (MODE_RANDOM_FACESWAP, "🎭 已切换到【随机换脸】模式 (消耗 2 灵石)。\n请发送一张【人脸】图片，我将自动匹配模板处理。"),
        "🎁 模板共建": (MODE_TEMPLATE_CONTRIBUTE, "🎁 已切换到【模板共建】模式。\n\n可以选择发送1到n张图片、视频，模板需要包含脸部和身体，露脸图片不会泄露，仅用于模板库建设，模板采纳会奖励灵石。"),
        "🥵 快速自慰": (MODE_MASTURBATION, "🥵 已切换到【快速自慰】模式 (消耗 2 灵石)。\n请发送一张图片，我将自动处理。"),
        "🎨 自由P图": (MODE_EDIT, "🎨 已切换到【自由P图】模式 (消耗 2 灵石)。\n请发送一张图片。"),
        "🎬 自定义图生视频": (MODE_CUSTOM_VIDEO, "🎬 已切换到【自定义图生视频】模式 (消耗 6 灵石)。\n请发送一张【起始图片】。\n(注意：该模式生成 5 秒视频，请确保提示词动作逻辑合理)"),
        "🛌 动图传教士": (MODE_PERFECT_VIDEO_INSERT, "🛌 已切换到【动图传教士】模式 (消耗 6 灵石)。\n请发送一张【人脸】图片（正面、清晰），我将自动处理。"),
        "🎬 动图后入": (MODE_DOGGY_STYLE, "🎬 已切换到【动图后入】模式 (消耗 6 灵石)。\n请发送一张【人脸】图片（正面、清晰），我将自动处理。"),
        "🎬 口交黑人": (MODE_BLOWJOB, "🎬 已切换到【口交黑人】模式 (消耗 6 灵石)。\n请发送一张【正面清晰图片】，我将自动处理。"),
        "🎬 脱衣吐舌": (MODE_UNDRESS_TONGUE, "🎬 已切换到【脱衣吐舌】模式 (消耗 6 灵石)。\n请发送一张【正面清晰图片】，我将自动处理。"),
        "🎬 特写口交": (MODE_CLOSEUP_BLOWJOB, "🎬 已切换到【特写口交】模式 (消耗 6 灵石)。\n请发送一张【正面清晰图片】，我将自动处理。"),
        "📝 文生图": (MODE_TEXT_TO_IMAGE, "📝 已切换到【文生图】模式 (消耗 3 灵石)。\n请直接发送【提示词】(支持中英韩文)，我将为您生成图片。")
    }
    
    if text in mode_map:
        new_mode, reply = mode_map[text]
        context.user_data['mode'] = new_mode
        context.user_data['pending_images'] = []
        context.user_data['contributed_count'] = 0 # Reset count when switching mode
        await robust_reply_text(update.message, reply)
        return

    # Generation Handling
    if not _is_mentioned(update, context):
        return

    mode = context.user_data.get('mode', MODE_EDIT)
    images = context.user_data.get('pending_images', [])
    
    if mode != MODE_TEXT_TO_IMAGE:
        if not images:
            await robust_reply_text(update.message, "请先发送一张图片。")
            return

        # In single image mode, we only care about the last sent valid image
        valid_images = [path for path in images if os.path.exists(path)]
        if not valid_images:
            await robust_reply_text(update.message, "❌ 图片已丢失，请重新发送图片。")
            return
        
        # Force single image for EDIT mode to match prompt
        if mode == MODE_EDIT:
            valid_images = [valid_images[-1]]

    # Execute Generation
    chat_id = update.message.chat_id
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.full_name
    
    if mode == MODE_CUSTOM_VIDEO:
        # 自定义图生视频
        if len(valid_images) != 1:
            await robust_reply_text(update.message, "❌ 需要且仅能发送一张起始图片，请重新发送。")
            context.user_data['pending_images'] = []
            return
        await task_service.process_custom_video_task(update, context, text, valid_images[0])
    elif mode == MODE_TEXT_TO_IMAGE:
        # 文生图
        if len(text) > 500:
            await robust_reply_text(update.message, "❌ 提示词过长，请控制在 500 字以内。")
            return
        await task_service.process_text_to_image_task(update, context, text)
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
