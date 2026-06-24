import logging

from telegram import Update
from telegram.ext import ContextTypes

from qqcc_bot.keyboards import (
    get_qqcc_main_menu_keyboard,
    get_qqcc_photo_edit_keyboard,
    get_qqcc_video_edit_keyboard,
)
from src.handlers.message_handler_common import (
    build_private_prompt_fallback,
    dispatch_prompt_route,
    ensure_user_access_reward,
    extract_prompt_message_text,
    get_reply_message,
)
from src.handlers.message_handler_prompt import handle_prompt_impl
from src.utils import robust_reply_text

logger = logging.getLogger("qqcc_bot.prompt")


async def _reply_payload(update, context, text: str, reply_markup):
    message = get_reply_message(update)
    if not message:
        return None
    await robust_reply_text(
        message,
        text,
        reply_markup=reply_markup,
        parse_mode="Markdown",
    )
    return None


async def handle_photo_edit_menu(update, context, text: str = None):
    return await _reply_payload(
        update,
        context,
        context.t("system.photo_edit_hint"),
        get_qqcc_photo_edit_keyboard(context.lang),
    )


async def handle_video_edit_menu(update, context, text: str = None):
    return await _reply_payload(
        update,
        context,
        context.t("system.video_edit_hint"),
        get_qqcc_video_edit_keyboard(context.lang),
    )


async def handle_back_to_main_menu(update, context, text: str = None):
    return await _reply_payload(
        update,
        context,
        context.t("system.back_to_main"),
        get_qqcc_main_menu_keyboard(context.lang),
    )


QQCC_PROMPT_ROUTES = {
    "menu.photo_edit": handle_photo_edit_menu,
    "menu.video_edit": handle_video_edit_menu,
    "menu.main_menu": handle_back_to_main_menu,
    "menu.back_main": handle_back_to_main_menu,
}


async def reply_qqcc_private_prompt_fallback(message, *, lang: str, reply_text):
    chat = getattr(message, "chat", None)
    if not chat or chat.type != "private":
        return None
    await reply_text(
        message,
        build_private_prompt_fallback(lang),
        reply_markup=get_qqcc_main_menu_keyboard(lang),
    )
    return None


async def handle_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await handle_prompt_impl(
        update,
        context,
        prompt_routes=QQCC_PROMPT_ROUTES,
        ensure_user_access_reward=ensure_user_access_reward,
        extract_prompt_message_text=extract_prompt_message_text,
        dispatch_prompt_route=dispatch_prompt_route,
        reply_private_prompt_fallback=reply_qqcc_private_prompt_fallback,
        reply_text=robust_reply_text,
        logger=logger,
    )

