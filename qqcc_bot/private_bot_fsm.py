from __future__ import annotations

import logging
import os
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from src.core.user_core import get_or_create_user_by_telegram
from src.database.core import AsyncSessionLocal
from src.database.models import PrivateQqccBot
from src.filters.i18n_filter import I18nFilter
from src.handlers.prompt_router import is_global_menu_command
from src.services.private_qqcc_bot_credentials import PrivateBotCredentialError
from src.services.private_qqcc_bot_owner_auth import issue_private_bot_owner_ticket
from src.services.private_qqcc_bot_runtime import (
    build_private_qqcc_bot_lifecycle_service,
)
from src.services.private_qqcc_bot_service import PrivateBotServiceError
from src.services.qqcc_config_service import (
    is_qqcc_private_bot_entry_enabled,
    load_runtime_qqcc_config,
)
from src.services.redis_client import redis_client

logger = logging.getLogger("qqcc_bot.private_bot")

WAIT_PRIVATE_BOT_TOKEN = 1
PRIVATE_BOT_OWNER_ID_KEY = "private_bot_owner_id"


def _t(context, key: str, **kwargs) -> str:
    translate = getattr(context, "t", None)
    return translate(key, **kwargs) if callable(translate) else key


def _owner_webapp_url(ticket: str) -> str | None:
    raw_url = os.getenv("PRIVATE_QQCC_BOT_OWNER_WEBAPP_URL", "").strip()
    expected_host = os.getenv("PRIVATE_QQCC_BOT_OWNER_HOST", "").strip().lower()
    parsed = urlsplit(raw_url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or not expected_host
        or parsed.hostname.lower() != expected_host
    ):
        return None
    fragment = dict(parse_qsl(parsed.fragment, keep_blank_values=True))
    fragment["ticket"] = ticket
    return urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, parsed.query, urlencode(fragment))
    )


async def build_private_bot_management_markup(
    *,
    owner_user_id: int,
    context,
) -> InlineKeyboardMarkup | None:
    ticket = await issue_private_bot_owner_ticket(
        internal_user_id=owner_user_id,
        redis=redis_client.redis,
    )
    url = _owner_webapp_url(ticket)
    if not url:
        return None
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    _t(context, "qqcc.private_bot.manage_button"),
                    web_app=WebAppInfo(url=url),
                )
            ]
        ]
    )


async def _resolve_owner(update: Update):
    user = update.effective_user
    if user is None:
        return None
    owner, _created = await get_or_create_user_by_telegram(
        tg_id=user.id,
        username=user.username,
        full_name=user.full_name,
        language_code=user.language_code,
    )
    return owner


async def _load_owner_bot(owner_user_id: int):
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(PrivateQqccBot).where(
                PrivateQqccBot.owner_user_id == owner_user_id
            )
        )
        return result.scalar_one_or_none()


async def _private_bot_entry_enabled() -> bool:
    try:
        config = await load_runtime_qqcc_config()
    except Exception:
        logger.error("Private Bot config unavailable: code=config_load_error")
        return False
    return is_qqcc_private_bot_entry_enabled(config)


async def start_private_bot_provisioning(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.effective_message
    if not await _private_bot_entry_enabled():
        if message is not None:
            await message.reply_text(_t(context, "qqcc.feature_disabled"))
        return ConversationHandler.END
    if getattr(getattr(update, "effective_chat", None), "type", None) != "private":
        if message is not None:
            await message.reply_text(
                _t(context, "qqcc.private_bot.private_chat_only")
            )
        return ConversationHandler.END
    owner = await _resolve_owner(update)
    if message is None or owner is None:
        return ConversationHandler.END

    existing = await _load_owner_bot(int(owner.id))
    if existing is not None:
        try:
            markup = await build_private_bot_management_markup(
                owner_user_id=int(owner.id),
                context=context,
            )
        except Exception:
            logger.error("Private Bot management ticket unavailable: code=redis_error")
            markup = None
        await message.reply_text(
            _t(
                context,
                "qqcc.private_bot.existing",
                username=existing.telegram_username or "",
                status=existing.runtime_status,
            ),
            reply_markup=markup,
        )
        return ConversationHandler.END

    context.user_data[PRIVATE_BOT_OWNER_ID_KEY] = int(owner.id)
    await message.reply_text(
        _t(context, "qqcc.private_bot.instructions"),
        parse_mode="Markdown",
    )
    return WAIT_PRIVATE_BOT_TOKEN


async def _provision_private_bot(
    *,
    owner_user_id: int,
    token: str,
):
    source_config = await load_runtime_qqcc_config()
    async with AsyncSessionLocal() as db:
        return await build_private_qqcc_bot_lifecycle_service(db).provision(
            owner_user_id=owner_user_id,
            token=token,
            source_config=source_config,
        )


async def receive_private_bot_token(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    provision_func=None,
    management_markup_func=None,
):
    message = update.effective_message
    if message is None:
        return ConversationHandler.END
    if getattr(getattr(update, "effective_chat", None), "type", None) != "private":
        await message.reply_text(_t(context, "qqcc.private_bot.private_chat_only"))
        return ConversationHandler.END
    token = str(message.text or "").strip()
    if is_global_menu_command(token):
        context.user_data.pop(PRIVATE_BOT_OWNER_ID_KEY, None)
        await message.reply_text(_t(context, "qqcc.private_bot.cancelled"))
        return ConversationHandler.END

    token_message_deleted = True
    try:
        await message.delete()
    except Exception:
        token_message_deleted = False

    if not await _private_bot_entry_enabled():
        context.user_data.pop(PRIVATE_BOT_OWNER_ID_KEY, None)
        text = _t(context, "qqcc.feature_disabled")
        if not token_message_deleted:
            text = f"{text}\n\n{_t(context, 'qqcc.private_bot.token_delete_warning')}"
        await message.reply_text(text)
        return ConversationHandler.END

    owner_user_id = int(context.user_data.get(PRIVATE_BOT_OWNER_ID_KEY) or 0)
    if owner_user_id <= 0:
        owner = await _resolve_owner(update)
        owner_user_id = int(getattr(owner, "id", 0) or 0)
    if owner_user_id <= 0:
        text = _t(context, "qqcc.private_bot.failed")
        if not token_message_deleted:
            text = f"{text}\n\n{_t(context, 'qqcc.private_bot.token_delete_warning')}"
        await message.reply_text(text)
        return ConversationHandler.END

    provision_func = provision_func or _provision_private_bot
    management_markup_func = (
        management_markup_func or build_private_bot_management_markup
    )
    try:
        result = await provision_func(
            owner_user_id=owner_user_id,
            token=token,
        )
        try:
            markup = await management_markup_func(
                owner_user_id=owner_user_id,
                context=context,
            )
        except Exception:
            logger.error("Private Bot management ticket unavailable: code=redis_error")
            markup = None
        text = _t(
            context,
            (
                "qqcc.private_bot.activated"
                if result.runtime_status == "active"
                else "qqcc.private_bot.activation_error"
            ),
            username=result.telegram_username,
        )
        if not token_message_deleted:
            text = f"{text}\n\n{_t(context, 'qqcc.private_bot.token_delete_warning')}"
        await message.reply_text(text, reply_markup=markup)
    except (PrivateBotServiceError, PrivateBotCredentialError) as exc:
        logger.warning("Private Bot provisioning rejected: code=%s", getattr(exc, "code", "error"))
        text = _t(
            context,
            "qqcc.private_bot.validation_error",
            code=getattr(exc, "code", "invalid_token"),
        )
        if not token_message_deleted:
            text = f"{text}\n\n{_t(context, 'qqcc.private_bot.token_delete_warning')}"
        await message.reply_text(text)
    except Exception:
        logger.error("Private Bot provisioning failed: code=unexpected_error")
        text = _t(context, "qqcc.private_bot.failed")
        if not token_message_deleted:
            text = f"{text}\n\n{_t(context, 'qqcc.private_bot.token_delete_warning')}"
        await message.reply_text(text)
    finally:
        context.user_data.pop(PRIVATE_BOT_OWNER_ID_KEY, None)
    return ConversationHandler.END


async def cancel_private_bot_provisioning(update: Update, context):
    context.user_data.pop(PRIVATE_BOT_OWNER_ID_KEY, None)
    if update.effective_message:
        await update.effective_message.reply_text(
            _t(context, "qqcc.private_bot.cancelled")
        )
    return ConversationHandler.END


async def timeout_private_bot_provisioning(update: Update, context):
    context.user_data.pop(PRIVATE_BOT_OWNER_ID_KEY, None)
    if update.effective_message:
        await update.effective_message.reply_text(
            _t(context, "qqcc.private_bot.timeout")
        )
    return ConversationHandler.END


def get_private_bot_provisioning_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            MessageHandler(
                I18nFilter("qqcc.menu.private_bot") & filters.ChatType.PRIVATE,
                start_private_bot_provisioning,
            ),
            MessageHandler(
                I18nFilter("qqcc.menu.private_bot") & ~filters.ChatType.PRIVATE,
                private_bot_group_redirect,
            ),
        ],
        states={
            WAIT_PRIVATE_BOT_TOKEN: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
                    receive_private_bot_token,
                )
            ],
            ConversationHandler.TIMEOUT: [
                MessageHandler(filters.ALL, timeout_private_bot_provisioning)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_private_bot_provisioning)],
        conversation_timeout=300,
        name="qqcc_private_bot_provisioning",
        persistent=False,
    )


async def private_bot_group_redirect(update: Update, context):
    if update.effective_message:
        if not await _private_bot_entry_enabled():
            await update.effective_message.reply_text(
                _t(context, "qqcc.feature_disabled")
            )
            return ConversationHandler.END
        await update.effective_message.reply_text(
            _t(context, "qqcc.private_bot.private_chat_only")
        )
    return ConversationHandler.END
