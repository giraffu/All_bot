import logging
import os
import time
import uuid

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    Update,
    WebAppInfo,
)
from telegram.ext import ContextTypes

from config import (
    CHANNEL_INVITE_LINK,
    MINIO_TEMPLATE_BUCKET,
    REFUGE_GROUP_ID,
    REFUGE_INVITE_LINK,
    WEBAPP_URL,
)
from src.constants import (

    MODE_NONE,
    MODE_TEMPLATE_CONTRIBUTE,
    TEMP_TEMPLATE_DIR,
    TEMPLATE_DIR_PENETRATION,
    TEMPLATE_DIR_QUICK_FACE,
    TEMPLATE_DIR_VIDEO_NICE,
    TMP_DIR,
)
from src.handlers.prompt_router import prompt_route, prompt_routes
from src.handlers.utils import _is_mentioned, with_db_logging_context, ensure_access_and_reward
from src.services.image_service import image_service
from src.services.permission_service import permission_service
from src.services.storage import storage
from src.services.task_service import task_service
from src.utils import robust_reply_text, create_background_task, is_maintenance_mode, robust_send_message, get_user_channel_status, notify_inviter_reward
from src.handlers.error_handlers import with_unified_error_handler

# Re-exporting for compatibility if needed, but preferred to import from constants/utils
process_generation_task = task_service.process_generation_task

os.makedirs(TMP_DIR, exist_ok=True)
os.makedirs(TEMPLATE_DIR_PENETRATION, exist_ok=True)
os.makedirs(TEMPLATE_DIR_QUICK_FACE, exist_ok=True)
os.makedirs(TEMPLATE_DIR_VIDEO_NICE, exist_ok=True)
os.makedirs(TEMP_TEMPLATE_DIR, exist_ok=True)

logger = logging.getLogger(__name__)

@with_unified_error_handler
@with_db_logging_context
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_mentioned(update, context): return
    if not await ensure_access_and_reward(update, context): return

    mode = context.user_data.get('mode', MODE_NONE)
    if mode == MODE_TEMPLATE_CONTRIBUTE:
        return await _handle_template_contribution(update, context)
    
    return await _handle_photo_idle(update, context)

@with_unified_error_handler
@with_db_logging_context
async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_mentioned(update, context): return
    if not await ensure_access_and_reward(update, context): return

    mode = context.user_data.get('mode', MODE_NONE)
    if mode == MODE_TEMPLATE_CONTRIBUTE:
        return await _handle_template_contribution(update, context)
    
    await robust_reply_text(update.message, "⚠️ 当前模式不支持视频处理。")

@with_unified_error_handler
@with_db_logging_context
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_mentioned(update, context): return
    if not await ensure_access_and_reward(update, context): return

    mode = context.user_data.get('mode', MODE_NONE)
    if mode == MODE_TEMPLATE_CONTRIBUTE:
        return await _handle_template_contribution(update, context)
    
    await robust_reply_text(update.message, "⚠️ 请发送压缩后的图片或视频格式，不要发送原图/文件。")

async def _handle_photo_idle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = time.time()
    last_reminder = context.user_data.get('last_reminder_time', 0)
    if now - last_reminder < 3.0:
        return
        
    from src.i18n.keyboards import get_main_menu_keyboard
    reply_markup = get_main_menu_keyboard(context.lang)
    
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
    username = user.username
    
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

@with_unified_error_handler
@prompt_route("menu.photo_edit")
async def handle_photo_edit_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    if not update.effective_user: return
    user = update.effective_user
    is_member = await get_user_channel_status(context.bot, user.id)
    inviter_id = await permission_service.check_access(user.id, user.username, user.full_name, is_member)
    if inviter_id:
        create_background_task(context, notify_inviter_reward(context.bot, inviter_id, user.full_name))
        
    from src.i18n.keyboards import get_photo_edit_keyboard
    reply_markup = get_photo_edit_keyboard(context.lang)
    await robust_reply_text(update.message, context.t("system.photo_edit_hint"), reply_markup=reply_markup, parse_mode="Markdown")

@prompt_route("menu.video_edit")
async def handle_video_edit_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    from src.i18n.keyboards import get_video_edit_keyboard
    reply_markup = get_video_edit_keyboard(context.lang)
    await robust_reply_text(update.message, context.t("system.video_edit_hint"), reply_markup=reply_markup, parse_mode="Markdown")

@prompt_route("menu.gallery")
async def handle_gallery_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    from src.i18n.keyboards import get_gallery_keyboard
    reply_markup = get_gallery_keyboard(context.lang)
    await robust_reply_text(
        update.message, 
        context.t("system.gallery_hint"), 
        reply_markup=reply_markup, 
        parse_mode="Markdown"
    )

@prompt_route("menu.back_main")
@prompt_route("menu.main_menu")
async def handle_back_to_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    from src.i18n.keyboards import get_main_menu_keyboard
    reply_markup = get_main_menu_keyboard(context.lang)
    await robust_reply_text(update.message, "🏠 **已返回主菜单**", reply_markup=reply_markup, parse_mode="Markdown")

@prompt_route("menu.recharge")
async def handle_recharge_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
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
        "   └ 📅 每日签到额外 `+30` 灵石\n"
        "   └ 🔓 解锁特权 `720p` 画质，最长 `8s` 视频\n"
        "   └ ⚡ 排队优先级 `+20`\n\n"
        "💠 **【核心弟子】** 4.99 TON / ¥ 70.00\n"
        "   └ 🎁 直接获得 `1200` 灵石\n"
        "   └ 📅 每日签到额外 `+40` 灵石\n"
        "   └ 🔓 解锁特权 `1024p` 画质，最长 `10s` 视频\n"
        "   └ ⚡ 排队优先级 `+30`\n\n"
        "👑 **【真传弟子】** 9.99 TON / ¥ 120.00\n"
        "   └ 🎁 直接获得 `3000` 灵石\n"
        "   └ 📅 每日签到额外 `+50` 灵石\n"
        "   └ 🔓 解锁特权 `1024p` 画质，最长 `10s` 视频\n"
        "   └ 🚀 排队优先级 `+45` (极速)\n\n"
        "⚠️ **注意事项**：\n"
        "1. 充值所获灵石与身份特权，一经交付，不可退换。\n\n"
        "👇 **请选择您的支付法门**："
    )
    await robust_reply_text(update.message, msg, parse_mode="Markdown", reply_markup=reply_markup)

@with_unified_error_handler
@prompt_route("menu.profile")
async def handle_personal_center(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    if not update.effective_user:
        return
    user = update.effective_user
    
    is_member = await get_user_channel_status(context.bot, user.id)
    if is_member is not None:
        await permission_service.sync_channel_status(user.id, user.username, user.full_name, is_member)
        
    await permission_service.ensure_user(user.id, user.username, user.full_name, user.language_code)
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name
    invite_link = CHANNEL_INVITE_LINK or "https://t.me/AiVisionAV"
    
    from src.core.user_facade import get_user_dashboard_info
    dto = await get_user_dashboard_info(user_id, first_name)
    
    # 构建突破提示
    breakthrough_msg = ""
    if dto.current_group == "凡人":
        breakthrough_msg = f"🚀 **突破至练气期条件**：\n🔸 拜入宗门 [👉 [点击即刻拜入]({invite_link})]"
    elif dto.current_group == "练气期":
        inv_done = "✅" if dto.invitations > 1 else "❌"
        checkin_done = "✅" if dto.checkins > 3 else "❌"
        gen_done = "✅" if dto.generations > 10 else "❌"
        breakthrough_msg = f"🚀 **突破至筑基期(视野更加清晰了)条件**：\n🔸 邀请道友 > 1人 ({inv_done})\n🔸 累计签到 > 3天 ({checkin_done})\n🔸 修炼次数 > 10次 ({gen_done})"
    elif dto.current_group == "筑基期":
        inv_done = "✅" if dto.invitations > 10 else "❌"
        checkin_done = "✅" if dto.checkins > 30 else "❌"
        gen_done = "✅" if dto.generations > 100 else "❌"
        breakthrough_msg = f"🚀 **突破至金丹期条件**：\n🔸 邀请道友 > 10人 ({inv_done})\n🔸 累计签到 > 30天 ({checkin_done})\n🔸 修炼次数 > 100次 ({gen_done})"
    elif dto.current_group == "金丹期":
        inv_done = "✅" if dto.invitations > 100 else "❌"
        checkin_done = "✅" if dto.checkins > 300 else "❌"
        gen_done = "✅" if dto.generations > 1000 else "❌"
        breakthrough_msg = f"🚀 **突破至元婴期条件**：\n🔸 邀请道友 > 100人 ({inv_done})\n🔸 累计签到 > 300天 ({checkin_done})\n🔸 修炼次数 > 1000次 ({gen_done})"
    elif dto.current_group == "元婴期":
        breakthrough_msg = "✨ **已修成元婴，神通广大，万法不侵**"

    # 构建身份展示
    identity_display = f"`{dto.current_identity}`"
    if dto.current_identity != "外门弟子" and dto.identity_expire_at:
        from datetime import datetime
        now = datetime.now()
        expire_at = dto.identity_expire_at
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
        f"👤 **道友**：`{dto.first_name}`\n"
        f"📜 **修为**：`{dto.current_group}`\n"
        f"🪪 **身份**：{identity_display}\n"
        f"⚡ **排队加速**：`+{dto.current_priority}` 优先级\n"
        f"💰 **灵石余额**：`{dto.credits}`\n\n"
        f"📊 **修炼数据**：\n"
        f"  - 邀请同道：`{dto.invitations}` 人\n"
        f"  - 累计签到：`{dto.checkins}` 天\n"
        f"  - 施法次数：`{dto.generations}` 次\n\n"
        f"🤝 **邀请数据**：\n"
        f"  - 邀请充值：已有 `{dto.invitation_recharge['recharged_invitees_count']}` 位道友完成 `{dto.invitation_recharge['total_recharge_count']}` 次充值\n"
        f"  - 累积充值：`{dto.invitation_recharge['total_ton']:.2f}` TON\n"
        f"  - 累积充值：`¥ {dto.invitation_recharge['total_rmb']:.2f}`\n"
        f"  - 累积贡献：`{dto.invitation_recharge['total_stars']}` Stars\n"
        f"  - 预估分成：*$ {dto.invitation_recharge.get('commission_usdt', 0.0):.2f} USDT* (仅计算受邀者历史首充金额的10%)\n\n"
        f"💡 *提示：1点加速优先级约等于为您节约1分钟的排队时间。*\n\n"
        f"{breakthrough_msg}"
    )
    
    reply_markup = None
    if dto.is_unlocked:
        msg += "\n\n🌐 **合欢密宗已解锁**"
        keyboard = [
            [
                InlineKeyboardButton("🌐 前往合欢密宗 (Web端)", url="https://web.aivison.it.com/"),
                InlineKeyboardButton("📱 沉浸式 Mini App", web_app=WebAppInfo(url="https://web.aivison.it.com/"))
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

    await robust_reply_text(update.message, msg, parse_mode="Markdown", reply_markup=reply_markup)

@prompt_route("menu.checkin")
async def handle_checkin(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str = None):
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
    
    if not update.effective_user: return
    user = update.effective_user
    success, current_credits, error_msg, total_days, reward = await permission_service.perform_checkin(user.id, user.username, user.full_name)
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

@prompt_route("menu.share")
async def handle_share(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str = None):
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

TASK_TYPE_DISPLAY_NAMES = {
    "img2img": "task.img2img",
    "img2img_lora": "task.img2img_lora",
    "i2i_pro": "task.i2i_pro",
    "face_swap": "task.face_swap",
    "video_insert": "task.video_insert",
    "video_edit": "task.video_edit",
    "face_video": "task.face_video",
    "ltx_video": "task.ltx_video",
    "t2i-pornmaster-turbo": "task.t2i_pornmaster_turbo",
    "custom_video": "task.custom_video",
    "video_lora": "task.video_lora"
}

@prompt_route("menu.queue")
async def handle_queue_status(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str = None):
    status = await image_service.get_queue_info()
    if status:
        queue_size = status.get('queue_size', 0)
        queue_by_type = status.get('queue_by_type', {})
        
        msg_lines = [
            "📊 **宗门灵气损耗现状**\n",
            f"👥 总排队任务：`{queue_size}` 个"
        ]
        
        # 固定展示字典中定义的所有类型（即使数量为0）
        for task_type, i18n_key in TASK_TYPE_DISPLAY_NAMES.items():
            count = queue_by_type.get(task_type, 0)
            display_name = context.t(i18n_key)
            msg_lines.append(f"{display_name}：`{count}` 个")
            
        # 兜底：如果队列里出现了未知类型，且数量大于0，也展示出来
        for task_type, count in queue_by_type.items():
            if task_type not in TASK_TYPE_DISPLAY_NAMES and count > 0:
                msg_lines.append(f"❓ 其他 ({task_type})：`{count}` 个")
                
        msg = "\n".join(msg_lines)
        await robust_reply_text(update.message, msg, parse_mode="Markdown")
    else:
        await robust_reply_text(update.message, "⚠️ 无法获取实时排队数据，请稍后再试。")

from src.handlers.error_handlers import with_unified_error_handler

@with_unified_error_handler
@with_db_logging_context
async def handle_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user: return
    user = update.effective_user
    await permission_service.check_access(user.id, user.username, user.full_name)

    message = update.message or update.edited_message
    if not message:
        return
    text = message.text.strip() if message.text else ""
    logger.info(f"handle_prompt received: {text.encode('utf-8')}")
    if not text:
        return

    from src.handlers.prompt_router import GLOBAL_REVERSE_MAP
    route_key = GLOBAL_REVERSE_MAP.get(text)
    if route_key and route_key in prompt_routes:
        return await prompt_routes[route_key](update, context, text)
            
    # 处理普通对话/Prompt 输入
    # (如果是其他普通文本，当前不需要做任何处理，或者可以交给AI对话)
    return
