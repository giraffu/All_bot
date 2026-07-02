import logging

from telegram import Update
from telegram.ext import ContextTypes

from qqcc_bot.keyboards import (
    get_qqcc_draw_edit_inline_keyboard,
    get_qqcc_main_bot_link_keyboard,
    get_qqcc_main_menu_keyboard,
    get_qqcc_photo_edit_keyboard,
    get_qqcc_video_edit_inline_keyboard,
)
from qqcc_bot.commands import resolve_main_bot_url
from qqcc_bot.gallery_market import open_qqcc_gallery_market_menu
from src.handlers.message_handler_common import (
    build_private_prompt_fallback,
    dispatch_prompt_route,
    ensure_user_access_reward,
    extract_prompt_message_text,
    get_reply_message,
)
from src.handlers.message_handler_prompt import handle_prompt_impl
from src.services.qqcc_config_service import (
    has_enabled_qqcc_draw_scenes,
    has_enabled_qqcc_values,
    has_enabled_qqcc_video_scenes,
    is_qqcc_global_enabled,
    is_qqcc_main_bot_link_enabled,
    is_qqcc_main_button_enabled,
    load_runtime_qqcc_config,
    normalize_qqcc_config,
)
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


async def _load_menu_config() -> dict:
    try:
        return await load_runtime_qqcc_config()
    except Exception:
        logger.exception("Failed to load QQCC lazy bot config; using defaults.")
        return normalize_qqcc_config(None)


def _can_open_photo_menu(config: dict) -> bool:
    return (
        is_qqcc_global_enabled(config)
        and is_qqcc_main_button_enabled(config, "photo_edit")
        and has_enabled_qqcc_values(config, "photo_buttons")
    )


def _can_open_video_menu(config: dict) -> bool:
    return (
        is_qqcc_global_enabled(config)
        and is_qqcc_main_button_enabled(config, "video_edit")
        and has_enabled_qqcc_video_scenes(config)
    )


def _can_open_ai_draw_menu(config: dict) -> bool:
    return (
        is_qqcc_global_enabled(config)
        and is_qqcc_main_button_enabled(config, "ai_draw")
        and has_enabled_qqcc_draw_scenes(config)
    )


def _can_open_market(config: dict) -> bool:
    return (
        is_qqcc_global_enabled(config)
        and is_qqcc_main_button_enabled(config, "market")
    )


async def _reply_feature_disabled(update, context, config: dict):
    return await _reply_payload(
        update,
        context,
        context.t("qqcc.feature_disabled"),
        get_qqcc_main_menu_keyboard(context.lang, config),
    )


async def handle_photo_edit_menu(update, context, text: str = None):
    config = await _load_menu_config()
    if not _can_open_photo_menu(config):
        return await _reply_feature_disabled(update, context, config)
    return await _reply_payload(
        update,
        context,
        context.t("system.photo_edit_hint"),
        get_qqcc_photo_edit_keyboard(context.lang, config),
    )


async def handle_video_edit_menu(update, context, text: str = None):
    config = await _load_menu_config()
    if not _can_open_video_menu(config):
        return await _reply_feature_disabled(update, context, config)
    return await _reply_payload(
        update,
        context,
        context.t("system.video_edit_hint"),
        get_qqcc_video_edit_inline_keyboard(context.lang, config),
    )


async def handle_ai_draw_menu(update, context, text: str = None):
    config = await _load_menu_config()
    if not _can_open_ai_draw_menu(config):
        return await _reply_feature_disabled(update, context, config)
    return await _reply_payload(
        update,
        context,
        context.t("system.ai_draw_hint"),
        get_qqcc_draw_edit_inline_keyboard(context.lang, config),
    )


async def handle_back_to_main_menu(update, context, text: str = None):
    context.user_data.pop("qqcc_gallery_apply", None)
    config = await _load_menu_config()
    return await _reply_payload(
        update,
        context,
        context.t("system.back_to_main"),
        get_qqcc_main_menu_keyboard(context.lang, config),
    )


async def handle_market_menu(update, context, text: str = None):
    config = await _load_menu_config()
    if not _can_open_market(config):
        return await _reply_feature_disabled(update, context, config)
    return await open_qqcc_gallery_market_menu(update, context)


async def handle_open_main_bot(update, context, text: str = None):
    config = await _load_menu_config()
    if not is_qqcc_main_bot_link_enabled(config):
        return await _reply_feature_disabled(update, context, config)
    main_bot_url = resolve_main_bot_url()
    if not main_bot_url:
        return await _reply_payload(
            update,
            context,
            context.t("system.main_bot_link_unavailable"),
            get_qqcc_main_menu_keyboard(context.lang, config),
        )
    return await _reply_payload(
        update,
        context,
        context.t("system.open_main_bot_hint"),
        get_qqcc_main_bot_link_keyboard(context.lang, main_bot_url),
    )


QQCC_PROMPT_ROUTES = {
    "menu.photo_edit": handle_photo_edit_menu,
    "qqcc.menu.ai_draw": handle_ai_draw_menu,
    "menu.video_edit": handle_video_edit_menu,
    "menu.main_menu": handle_back_to_main_menu,
    "menu.back_main": handle_back_to_main_menu,
    "menu.open_main_bot": handle_open_main_bot,
    "qqcc.menu.market": handle_market_menu,
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
