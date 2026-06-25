import contextlib
import logging
import os
import re
from urllib.parse import urlparse

from telegram import BotCommand, Update
from telegram.ext import Application, ContextTypes

from qqcc_bot.keyboards import get_qqcc_main_menu_keyboard
from src.handlers.utils import with_db_logging_context
from src.i18n.translator import get_text
from src.services.permission_service import permission_service
from src.utils import (
    create_background_task,
    get_user_channel_status,
    notify_inviter_reward,
    robust_send_message,
)

logger = logging.getLogger("qqcc_bot.command")
_BOT_USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{5,32}$")


async def setup_commands(app: Application):
    commands_zh = [
        BotCommand("start", get_text("menu.main_menu", "zh")),
        BotCommand("cancel", get_text("menu.cancel", "zh")),
    ]
    commands_en = [
        BotCommand("start", get_text("menu.main_menu", "en")),
        BotCommand("cancel", get_text("menu.cancel", "en")),
    ]
    await app.bot.set_my_commands(commands_zh, language_code="zh")
    await app.bot.set_my_commands(commands_en, language_code="en")
    await app.bot.set_my_commands(commands_en)


def _is_supported_telegram_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme in {"http", "https"}:
        return parsed.netloc.lower() in {"t.me", "telegram.me"} and bool(
            parsed.path.strip("/")
        )
    if parsed.scheme == "tg":
        return parsed.netloc == "resolve" and bool(parsed.query)
    return False


def resolve_main_bot_url() -> str | None:
    configured_url = (os.getenv("QQCC_MAIN_BOT_URL") or "").strip()
    if configured_url:
        if _is_supported_telegram_url(configured_url):
            return configured_url
        logger.warning("Ignoring unsupported QQCC main bot URL configuration.")
        return None

    configured_username = (os.getenv("QQCC_MAIN_BOT_USERNAME") or "").strip()
    if not configured_username:
        return None

    username = configured_username.removeprefix("@")
    if not _BOT_USERNAME_PATTERN.fullmatch(username):
        logger.warning("Ignoring unsupported QQCC main bot username: %s", username)
        return None
    return f"https://t.me/{username}"


@with_db_logging_context
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return

    user = update.effective_user
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
                with contextlib.suppress(Exception):
                    await robust_send_message(
                        context.bot,
                        chat_id=inviter_id,
                        text=(
                            f"🎉 **道缘已至！**\n\n道友 {user.full_name} 响应了您的号召，入驻宗门。\n"
                            "TA 拜入宗门后您可获得 `5` 灵石；TA 首次成功生成后，邀请奖励累计至 `10` 灵石。"
                        ),
                        parse_mode="Markdown",
                    )
            elif status == "visitor_limit":
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

    is_new = await permission_service.ensure_user(
        user.id, user.username, user.full_name, user.language_code
    )
    if is_new:
        logger.info(
            "New QQCC user registered: %s (@%s)",
            user.id,
            user.username or "N/A",
        )
    else:
        logger.info("QQCC user started: %s (@%s)", user.id, user.username or "N/A")

    context.user_data["mode"] = "none"
    await update.message.reply_text(
        context.t("command.start_intro"),
        reply_markup=get_qqcc_main_menu_keyboard(context.lang),
        parse_mode="Markdown",
    )


@with_db_logging_context
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("in_conversation", None)
    keys_to_remove = [key for key in context.user_data.keys() if key.endswith("_data")]
    for key in keys_to_remove:
        context.user_data.pop(key, None)

    await update.message.reply_text(
        context.t("command.force_cancel"),
        reply_markup=get_qqcc_main_menu_keyboard(context.lang),
        parse_mode="Markdown",
    )
