import os
import uuid
import random
import time
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, WebAppInfo
from telegram.ext import ContextTypes

from config import CHANNEL_INVITE_LINK, ENABLE_PUBLIC_SHARE, REFUGE_GROUP_ID, REFUGE_INVITE_LINK, WEBAPP_URL, MINIO_TEMPLATE_BUCKET
from src.services.permission_service import permission_service
from src.services.image_service import image_service
from src.services.storage import storage
from src.services.task_service import task_service
from src.logger import UserLogger
from src.utils import robust_reply_text, load_prompts
from src.constants import (
    TMP_DIR, TEMPLATE_DIR_PENETRATION, TEMPLATE_DIR_QUICK_FACE, TEMPLATE_DIR_VIDEO_NICE, TEMP_TEMPLATE_DIR,
    MODE_EDIT, MODE_UNDRESS, MODE_MASTURBATION,
    MODE_FACESWAP_STEP1, MODE_FACESWAP_STEP2, MODE_RANDOM_FACESWAP,
    MODE_FACE_VIDEO_STEP1, MODE_FACE_VIDEO_STEP2,
    MODE_TEMPLATE_CONTRIBUTE, MODE_NONE, MODE_CUSTOM_VIDEO, MODE_PERFECT_VIDEO_INSERT,
    MODE_DOGGY_STYLE, MODE_BLOWJOB, MODE_UNDRESS_TONGUE, MODE_CLOSEUP_BLOWJOB, MODE_I2I_PRO,
    MAIN_MENU_KEYBOARD
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
    if not _is_mentioned(update, context): return
    if not await permission_service.check_access(update, context): return

    mode = context.user_data.get('mode', MODE_NONE)
    if mode == MODE_TEMPLATE_CONTRIBUTE:
        return await _handle_template_contribution(update, context)
    
    return await _handle_photo_idle(update, context)

@with_db_logging_context
async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_mentioned(update, context): return
    if not await permission_service.check_access(update, context): return

    mode = context.user_data.get('mode', MODE_NONE)
    if mode == MODE_TEMPLATE_CONTRIBUTE:
        return await _handle_template_contribution(update, context)
    
    await robust_reply_text(update.message, "⚠️ 当前模式不支持视频处理。")

@with_db_logging_context
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_mentioned(update, context): return
    if not await permission_service.check_access(update, context): return

    mode = context.user_data.get('mode', MODE_NONE)
    if mode == MODE_TEMPLATE_CONTRIBUTE:
        return await _handle_template_contribution(update, context)
    
    return await _handle_photo_idle(update, context)

async def _handle_photo_idle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = time.time()
    last_reminder = context.user_data.get('last_reminder_time', 0)
    if now - last_reminder < 3.0:
        return
        
    reply_markup = ReplyKeyboardMarkup(MAIN_MENU_KEYBOARD, resize_keyboard=True)
    
    await robust_reply_text(
        update.message, 
        "⚠️ **请先选择功能模式**\n\n点击下方菜单选择您想要的功能 👇", 
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    context.user_data['last_reminder_time'] = now

async def _handle_template_contribution(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    user = update.effective_user
    username = user.username or user.full_name
    
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

    try:
        file = await context.bot.get_file(file_id)
        local_filename = f"{user.id}_{uuid.uuid4().hex}{file_ext}"
        local_path = os.path.join(TEMP_TEMPLATE_DIR, local_filename)
        await file.download_to_drive(local_path)
        
        minio_object_name = f"temps/{local_filename}"
        storage.upload_file(local_path, minio_object_name, bucket=MINIO_TEMPLATE_BUCKET)
        
        file_type_db = 'photo'
        if msg.video:
            file_type_db = 'video'
        elif msg.document:
            file_type_db = 'document'
        
        await permission_service.record_contribution(user.id, local_path, file_type_db)
        
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
    if not await permission_service.check_access(update, context):
        return

    text = update.message.text.strip() if update.message.text else ""
    logger.info(f"handle_prompt received: {text.encode('utf-8')}")
    if not text:
        return

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

    if text == "🏆 发现/排行榜":
        keyboard = [
            [InlineKeyboardButton("🔥 最新投稿", callback_data="gallery_catmenu_latest")],
            [InlineKeyboardButton("❤️ 最多点赞", callback_data="gallery_catmenu_likes")],
            [InlineKeyboardButton("🪄 最多应用", callback_data="gallery_catmenu_applied")],
            [InlineKeyboardButton("🙋 我的投稿", callback_data="gallery_catmenu_mine")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await robust_reply_text(
            update.message, 
            "🏆 **修仙界广场**\n\n请选择您想查看的榜单：", 
            reply_markup=reply_markup, 
            parse_mode="Markdown"
        )
        return

    if text == "🔙 返回主菜单":
        reply_markup = ReplyKeyboardMarkup(MAIN_MENU_KEYBOARD, resize_keyboard=True)
        await robust_reply_text(update.message, "🏠 **已返回主菜单**", reply_markup=reply_markup, parse_mode="Markdown")
        return
        
    if text == "💎 充值灵石":
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
        await permission_service.sync_channel_status(update, context)
        await permission_service.ensure_user(update)
        user_id = update.effective_user.id
        stats = await permission_service.get_user_detailed_stats(user_id)
        
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
            f"  - 累积充值：`¥ {stats['invitation_recharge']['total_rmb']:.2f}`\n"
            f"  - 累积贡献：`{stats['invitation_recharge']['total_stars']}` Stars\n\n"
            f"💡 *提示：1点加速优先级约等于为您节约1分钟的排队时间。*\n\n"
            f"{breakthrough_msg}"
        )
        
        await robust_reply_text(update.message, msg, parse_mode="Markdown")
        return

    if text in ["📅 每日签到", "签到", "/checkin"]:
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
        
        from src.core.user_core import get_or_create_user_by_telegram
        internal_user, _ = await get_or_create_user_by_telegram(update.effective_user.id)
        internal_user_id = internal_user.id
        
        success, current_credits, error_msg, total_days, reward = await permission_service.perform_checkin(update)
        user_group = await permission_service.get_user_group(internal_user_id)
        user_identity = await permission_service.get_user_identity(internal_user_id)
        
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
        from src.core.user_core import get_or_create_user_by_telegram
        internal_user, _ = await get_or_create_user_by_telegram(user_id)
        internal_user_id = internal_user.id
        
        invite_link = f"https://t.me/{bot_username}?start={user_id}"
        count = await permission_service.get_referral_count(internal_user_id)
        user_group = await permission_service.get_user_group(internal_user_id)
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
