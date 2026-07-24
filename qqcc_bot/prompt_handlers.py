import logging

from telegram import Update
from telegram.ext import ContextTypes

from qqcc_bot.keyboards import (
    get_qqcc_draw_edit_inline_keyboard,
    get_qqcc_filter_edit_inline_keyboard,
    get_qqcc_main_bot_link_keyboard,
    get_qqcc_main_menu_keyboard,
    get_qqcc_video_edit_inline_keyboard,
    get_qqcc_video_v1_inline_keyboard,
    get_qqcc_draw_v1_inline_keyboard,
    get_qqcc_ai_video_inline_keyboard,
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
    get_qqcc_copywriting_override,
    has_enabled_qqcc_draw_scenes,
    has_enabled_qqcc_filter_scenes,
    has_enabled_qqcc_video_scenes,
    has_enabled_qqcc_ai_video_scenes,
    is_qqcc_global_enabled,
    is_qqcc_main_bot_link_enabled,
    is_qqcc_main_button_enabled,
    load_runtime_qqcc_config,
    normalize_qqcc_config,
)
from src.services.qqcc_runtime_context import (
    is_private_qqcc_bot_context,
    load_qqcc_config_for_context,
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


async def _load_menu_config(context=None) -> dict:
    try:
        if context is not None and is_private_qqcc_bot_context(context):
            return await load_qqcc_config_for_context(context)
        return await load_runtime_qqcc_config()
    except Exception:
        if context is not None and is_private_qqcc_bot_context(context):
            logger.error("Private QQCC Bot config is unavailable; failing closed.")
            raise
        logger.exception("Failed to load QQCC lazy bot config; using defaults.")
        return normalize_qqcc_config(None)


def _main_menu_keyboard(context, config):
    bot_data = getattr(context, "bot_data", {}) or {}
    private_entry_enabled = bot_data.get(
        "private_bot_provisioning_enabled",
        True,
    )
    return get_qqcc_main_menu_keyboard(
        context.lang,
        config,
        include_private_bot_entry=(
            bool(private_entry_enabled)
            and not is_private_qqcc_bot_context(context)
        ),
    )


def _can_open_video_menu(config: dict) -> bool:
    return (
        is_qqcc_global_enabled(config)
        and is_qqcc_main_button_enabled(config, "video_edit_v2")
        and has_enabled_qqcc_video_scenes(config)
    )


def _can_open_ai_video_menu(config: dict) -> bool:
    return (
        is_qqcc_global_enabled(config)
        and is_qqcc_main_button_enabled(config, "ai_video")
        and has_enabled_qqcc_ai_video_scenes(config)
    )


def _can_open_ai_draw_menu(config: dict) -> bool:
    return (
        is_qqcc_global_enabled(config)
        and is_qqcc_main_button_enabled(config, "ai_draw_v2")
        and has_enabled_qqcc_draw_scenes(config)
    )


def _can_open_ai_filter_menu(config: dict) -> bool:
    return (
        is_qqcc_global_enabled(config)
        and is_qqcc_main_button_enabled(config, "ai_filter")
        and has_enabled_qqcc_filter_scenes(config)
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
        _main_menu_keyboard(context, config),
    )


async def handle_photo_edit_menu(update, context, text: str = None):
    config = await _load_menu_config(context)
    return await _reply_feature_disabled(update, context, config)


async def handle_video_edit_menu(update, context, text: str = None):
    config = await _load_menu_config(context)
    if not _can_open_video_menu(config):
        return await _reply_feature_disabled(update, context, config)
    return await _reply_payload(
        update,
        context,
        get_qqcc_copywriting_override(config, "video_menu")
        or context.t("system.video_edit_hint"),
        get_qqcc_video_edit_inline_keyboard(context.lang, config),
    )


async def handle_video_v1_menu(update, context, text: str = None):
    config = await _load_menu_config(context)
    if not (is_qqcc_global_enabled(config) and is_qqcc_main_button_enabled(config, "video_edit_v1")):
        return await _reply_feature_disabled(update, context, config)
    return await _reply_payload(update, context, "🎬 **AI动图V1**\n请选择动图场景：", get_qqcc_video_v1_inline_keyboard(context.lang, config))


async def handle_ai_video_menu(update, context, text: str = None):
    config = await _load_menu_config(context)
    if not _can_open_ai_video_menu(config):
        return await _reply_feature_disabled(update, context, config)
    return await _reply_payload(
        update,
        context,
        get_qqcc_copywriting_override(config, "ai_video_menu")
        or context.t("system.ai_video_hint"),
        get_qqcc_ai_video_inline_keyboard(context.lang, config),
    )


async def handle_ai_draw_menu(update, context, text: str = None):
    config = await _load_menu_config(context)
    if not _can_open_ai_draw_menu(config):
        return await _reply_feature_disabled(update, context, config)
    return await _reply_payload(
        update,
        context,
        get_qqcc_copywriting_override(config, "ai_draw_menu")
        or context.t("system.ai_draw_hint"),
        get_qqcc_draw_edit_inline_keyboard(context.lang, config),
    )


async def handle_ai_draw_v1_menu(update, context, text: str = None):
    config = await _load_menu_config(context)
    if not (is_qqcc_global_enabled(config) and is_qqcc_main_button_enabled(config, "ai_draw_v1")):
        return await _reply_feature_disabled(update, context, config)
    return await _reply_payload(update, context, "🎨 **AI绘图V1**\n请选择绘图场景：", get_qqcc_draw_v1_inline_keyboard(context.lang, config))


async def handle_ai_filter_menu(update, context, text: str = None):
    config = await _load_menu_config(context)
    if not _can_open_ai_filter_menu(config):
        return await _reply_feature_disabled(update, context, config)
    return await _reply_payload(
        update,
        context,
        get_qqcc_copywriting_override(config, "ai_filter_menu")
        or context.t("system.ai_filter_hint"),
        get_qqcc_filter_edit_inline_keyboard(context.lang, config),
    )


async def handle_back_to_main_menu(update, context, text: str = None):
    context.user_data.pop("qqcc_gallery_apply", None)
    config = await _load_menu_config(context)
    return await _reply_payload(
        update,
        context,
        context.t("system.back_to_main"),
        _main_menu_keyboard(context, config),
    )


async def handle_market_menu(update, context, text: str = None):
    config = await _load_menu_config(context)
    if not _can_open_market(config):
        return await _reply_feature_disabled(update, context, config)
    return await open_qqcc_gallery_market_menu(update, context)


async def handle_open_main_bot(update, context, text: str = None):
    config = await _load_menu_config(context)
    if not is_qqcc_main_bot_link_enabled(config):
        return await _reply_feature_disabled(update, context, config)
    main_bot_url = resolve_main_bot_url()
    if not main_bot_url:
        return await _reply_payload(
            update,
            context,
            context.t("system.main_bot_link_unavailable"),
            _main_menu_keyboard(context, config),
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
    "qqcc.menu.ai_draw_v1": handle_ai_draw_v1_menu,
    "qqcc.menu.ai_filter": handle_ai_filter_menu,
    "menu.video_edit": handle_video_edit_menu,
    "qqcc.menu.video_edit_v1": handle_video_v1_menu,
    "qqcc.menu.ai_video": handle_ai_video_menu,
    "menu.main_menu": handle_back_to_main_menu,
    "menu.back_main": handle_back_to_main_menu,
    "menu.open_main_bot": handle_open_main_bot,
    "qqcc.menu.market": handle_market_menu,
}


async def reply_qqcc_private_prompt_fallback(
    message,
    *,
    lang: str,
    reply_text,
    include_private_bot_entry: bool = True,
    config: dict | None = None,
):
    chat = getattr(message, "chat", None)
    if not chat or chat.type != "private":
        return None
    await reply_text(
        message,
        build_private_prompt_fallback(lang),
        reply_markup=get_qqcc_main_menu_keyboard(
            lang,
            config,
            include_private_bot_entry=include_private_bot_entry,
        ),
    )
    return None


async def handle_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async def _context_fallback(message, *, lang: str, reply_text):
        config = await _load_menu_config(context)
        bot_data = getattr(context, "bot_data", {}) or {}
        return await reply_qqcc_private_prompt_fallback(
            message,
            lang=lang,
            reply_text=reply_text,
            include_private_bot_entry=(
                bool(
                    bot_data.get(
                        "private_bot_provisioning_enabled",
                        True,
                    )
                )
                and not is_private_qqcc_bot_context(context)
            ),
            config=config,
        )

    return await handle_prompt_impl(
        update,
        context,
        prompt_routes=QQCC_PROMPT_ROUTES,
        ensure_user_access_reward=ensure_user_access_reward,
        extract_prompt_message_text=extract_prompt_message_text,
        dispatch_prompt_route=dispatch_prompt_route,
        reply_private_prompt_fallback=_context_fallback,
        reply_text=robust_reply_text,
        logger=logger,
    )
