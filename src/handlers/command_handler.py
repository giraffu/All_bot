import logging
import os

from telegram import BotCommand, Update
from telegram.ext import Application, ContextTypes

from config import ADMIN_USERS

from src.handlers.utils import with_db_logging_context
from src.services.permission_service import permission_service
from src.utils import (
    MAINTENANCE_FILE,
    robust_send_message,
    get_user_channel_status,
    notify_inviter_reward,
    create_background_task,
)
from src.handlers.error_handlers import with_unified_error_handler
import contextlib


async def setup_commands(app: Application):
    """
    Set default commands for the bot menu button with multi-language support
    """
    from src.i18n.translator import get_text

    # Define commands for Chinese (Default)
    commands_zh = [
        BotCommand("start", get_text("menu.main_menu", "zh")),
        BotCommand("cancel", get_text("menu.cancel", "zh")),
    ]

    # Define commands for English
    commands_en = [
        BotCommand("start", get_text("menu.main_menu", "en")),
        BotCommand("cancel", get_text("menu.cancel", "en")),
    ]

    # Register native Telegram menus
    await app.bot.set_my_commands(commands_zh, language_code="zh")
    await app.bot.set_my_commands(commands_en, language_code="en")
    # Fallback to English for users with other languages
    await app.bot.set_my_commands(commands_en)


@with_db_logging_context
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):

    # Globally clear the FSM lock
    context.user_data.pop("in_conversation", None)

    # Clear all state data
    keys_to_remove = [k for k in context.user_data.keys() if k.endswith("_data")]
    for k in keys_to_remove:
        context.user_data.pop(k, None)

    # Define menu keyboard
    from src.i18n.keyboards import get_main_menu_keyboard

    reply_markup = get_main_menu_keyboard(context.lang)

    await update.message.reply_text(
        "🚫 **已强制取消当前所有流程。**\n\n您可以重新选择菜单中的功能开始新任务。",
        reply_markup=reply_markup,
        parse_mode="Markdown",
    )


@with_unified_error_handler
@with_db_logging_context
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return
    logger = logging.getLogger("bot.command")
    user = update.effective_user

    # Process Referral BEFORE check_access or ensure_user
    # Because check_access/ensure_user creates the user in DB,
    # which makes process_referral think it's an existing user.
    args = context.args
    if args and len(args) > 0:
        try:
            inviter_id = int(args[0])
            success, status = False, None
            if inviter_id != user.id:
                success, status = await permission_service.process_referral(
                    user.id, user.username, user.full_name, inviter_id
                )
            if success:
                # Notify inviter
                with contextlib.suppress(Exception):
                    await robust_send_message(
                        context.bot,
                        chat_id=inviter_id,
                        text=f"🎉 **道缘已至！**\n\n道友 {user.full_name} 响应了您的号召，入驻宗门。\n获得奖励：`5` 灵石。",
                        parse_mode="Markdown",
                    )
            elif status == "visitor_limit":
                # Notify inviter about visitor limit
                with contextlib.suppress(Exception):
                    await robust_send_message(
                        context.bot,
                        chat_id=inviter_id,
                        text="⚠️ **邀请奖励未发放**\n\n您目前尚处于凡人境界，无法获得邀请奖励。请先拜入 **宗门** 踏入 **练气期** 即可解锁邀请奖励权限！",
                        parse_mode="Markdown",
                    )
        except ValueError:
            pass

    is_member = await get_user_channel_status(context.bot, user.id)
    inviter_id_reward = await permission_service.check_access(
        user.id, user.username, user.full_name, is_member
    )
    if inviter_id_reward:
        create_background_task(
            context,
            notify_inviter_reward(context.bot, inviter_id_reward, user.full_name),
        )

    # Ensure user info is up to date
    is_new = await permission_service.ensure_user(
        user.id, user.username, user.full_name, user.language_code
    )

    # Log User Info
    if is_new:
        logger.info(
            f"🆕 NEW USER REGISTERED: {user.id} (@{user.username or 'N/A'}) - {user.full_name}"
        )
    else:
        logger.info(f"🤖 User started the bot: {user.id} (@{user.username or 'N/A'})")

    # Initialize mode to NONE
    context.user_data["mode"] = "none"

    # Define menu keyboard
    from src.i18n.keyboards import get_main_menu_keyboard

    reply_markup = get_main_menu_keyboard(context.lang)

    await update.message.reply_text(
        "⛩️ **欢迎来到宗门灵境**\n\n"
        "请选择您的修炼方式：\n\n"
        "💎 **充值灵石**：在合欢宗账房换取极品灵石与身份特权。\n"
        "📅 **每日签到**：每日吐纳，根据修为(基础10-20)和身份(额外+30~50)领取丰厚灵石。\n"
        "🤝 **分享赚灵石**：邀请道友入宗，无限领灵石！\n"
        "🌟 **幻想换脸**：以图生图，发挥无限想象。\n"
        "🎨 **自由P图**：施展随心所欲的炼金术。\n"
        "🎬 **自定义视频**：赋予画卷生命，生成演武视频。\n"
        "👤 **个人中心**：查看当前境界、灵石余额及突破规则。\n\n"
        "⚠️ **使用说明**：请仅上传您有权使用的素材，并确保生成内容符合法律法规与平台规则；严禁用于未成年人、偷拍、侵权、非自愿或其他违规场景。",
        reply_markup=reply_markup,
        parse_mode="Markdown",
    )


@with_db_logging_context
async def toggle_maintenance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle maintenance mode for generation services. Only accessible by admins."""
    user = update.effective_user
    if user.id not in ADMIN_USERS:
        await robust_send_message(
            context.bot, update.message.chat_id, "🚫 您没有权限执行此操作。"
        )
        return

    args = context.args
    if not args or args[0].lower() not in ["on", "off"]:
        await robust_send_message(
            context.bot, update.message.chat_id, "用法: /maintenance on|off"
        )
        return

    action = args[0].lower()

    if action == "on":
        with open(MAINTENANCE_FILE, "w") as f:
            f.write("1")
        await robust_send_message(
            context.bot,
            update.message.chat_id,
            "✅ 维护模式已开启，已暂停所有生成服务。",
        )
    else:
        if os.path.exists(MAINTENANCE_FILE):
            os.remove(MAINTENANCE_FILE)
        await robust_send_message(
            context.bot, update.message.chat_id, "✅ 维护模式已关闭，生成服务恢复正常。"
        )
