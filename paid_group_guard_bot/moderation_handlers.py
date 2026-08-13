from __future__ import annotations

import logging
from dataclasses import dataclass

from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

from typing import Protocol
from paid_group_guard_bot.moderation import (
    PaidGroupModerationConfigProvider,
    PaidGroupModerationDecision,
    PaidGroupModerationLogEvent,
    append_moderation_log,
    build_text_snippet,
    evaluate_moderation_decision,
    now_timestamp,
)

logger = logging.getLogger(__name__)
ADMIN_STATUSES = {"administrator", "creator", "owner"}
LINK_ENTITY_TYPES = {"url", "text_link"}


class ModerationSettings(Protocol):
    target_chat_id: int
    moderation_config_file: str
    moderation_log_file: str


@dataclass(frozen=True)
class _MessageContext:
    chat_id: int
    message_id: int
    user_id: int
    username: str | None
    full_name: str | None
    text: str
    link_candidates: list[str]


def _entity_type(entity) -> str | None:
    raw_type = getattr(entity, "type", None)
    value = getattr(raw_type, "value", raw_type)
    return str(value) if value is not None else None


def _parse_entity_value(message, entity, *, caption: bool = False) -> str | None:
    entity_type = _entity_type(entity)
    if entity_type == "text_link":
        return getattr(entity, "url", None)
    if entity_type != "url":
        return None

    parse_method_name = "parse_caption_entity" if caption else "parse_entity"
    parse_method = getattr(message, parse_method_name, None)
    if callable(parse_method):
        try:
            return parse_method(entity)
        except Exception:
            logger.debug("Failed to parse Telegram message entity", exc_info=True)

    source = getattr(message, "caption" if caption else "text", None) or ""
    offset = getattr(entity, "offset", None)
    length = getattr(entity, "length", None)
    if isinstance(offset, int) and isinstance(length, int):
        return source[offset : offset + length]
    return None


def _collect_link_candidates(message) -> list[str]:
    candidates: list[str] = []
    for entity in getattr(message, "entities", None) or []:
        if _entity_type(entity) in LINK_ENTITY_TYPES:
            value = _parse_entity_value(message, entity, caption=False)
            if value:
                candidates.append(value)
    for entity in getattr(message, "caption_entities", None) or []:
        if _entity_type(entity) in LINK_ENTITY_TYPES:
            value = _parse_entity_value(message, entity, caption=True)
            if value:
                candidates.append(value)
    return candidates


def _build_message_context(update: Update) -> _MessageContext | None:
    message = update.effective_message
    if message is None:
        return None

    chat = getattr(message, "chat", None)
    user = getattr(message, "from_user", None)
    if chat is None or user is None:
        return None

    text_parts = [
        getattr(message, "text", None) or "",
        getattr(message, "caption", None) or "",
    ]
    text = "\n".join(part for part in text_parts if part)
    return _MessageContext(
        chat_id=int(chat.id),
        message_id=int(message.message_id),
        user_id=int(user.id),
        username=getattr(user, "username", None),
        full_name=getattr(user, "full_name", None),
        text=text,
        link_candidates=_collect_link_candidates(message),
    )


async def _is_admin_or_owner(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int
) -> bool:
    member = await context.bot.get_chat_member(chat_id=chat_id, user_id=user_id)
    status = str(getattr(member, "status", "")).lower()
    return status in ADMIN_STATUSES


def _write_moderation_event(
    *,
    settings: ModerationSettings,
    msg: _MessageContext,
    decision: PaidGroupModerationDecision,
    action: str,
    error: str | None = None,
) -> None:
    append_moderation_log(
        settings.moderation_log_file,
        PaidGroupModerationLogEvent(
            timestamp=now_timestamp(),
            chat_id=msg.chat_id,
            message_id=msg.message_id,
            user_id=msg.user_id,
            username=msg.username,
            full_name=msg.full_name,
            reason=decision.reason or "unknown",
            matched_value=decision.matched_value,
            text_snippet=build_text_snippet(msg.text),
            action=action,
            error=error,
        ),
    )


async def handle_message_moderation(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    settings: ModerationSettings,
    config_provider: PaidGroupModerationConfigProvider | None = None,
) -> None:
    msg = _build_message_context(update)
    if msg is None or msg.chat_id != settings.target_chat_id:
        return

    provider = config_provider or PaidGroupModerationConfigProvider(
        settings.moderation_config_file
    )
    config = provider.load()

    decision = evaluate_moderation_decision(
        config=config,
        text=msg.text,
        link_candidates=msg.link_candidates,
    )
    if not decision.should_delete:
        return

    if msg.user_id in config.exempt_user_ids:
        return

    try:
        if await _is_admin_or_owner(context, msg.chat_id, msg.user_id):
            return
    except Exception as exc:
        logger.warning(
            "Paid group moderation admin check failed chat_id=%s user_id=%s "
            "message_id=%s: %s",
            msg.chat_id,
            msg.user_id,
            msg.message_id,
            exc,
        )
        return

    if config.dry_run:
        _write_moderation_event(
            settings=settings,
            msg=msg,
            decision=decision,
            action="dry_run",
        )
        logger.info(
            "Paid group moderation dry-run chat_id=%s message_id=%s user_id=%s "
            "reason=%s matched=%s",
            msg.chat_id,
            msg.message_id,
            msg.user_id,
            decision.reason,
            decision.matched_value,
        )
        return

    try:
        await context.bot.delete_message(chat_id=msg.chat_id, message_id=msg.message_id)
    except Exception as exc:
        _write_moderation_event(
            settings=settings,
            msg=msg,
            decision=decision,
            action="delete_failed",
            error=str(exc),
        )
        logger.warning(
            "Paid group moderation delete failed chat_id=%s message_id=%s "
            "user_id=%s reason=%s error=%s",
            msg.chat_id,
            msg.message_id,
            msg.user_id,
            decision.reason,
            exc,
        )
        return

    _write_moderation_event(
        settings=settings,
        msg=msg,
        decision=decision,
        action="deleted",
    )
    logger.info(
        "Paid group moderation deleted message chat_id=%s message_id=%s user_id=%s "
        "reason=%s matched=%s",
        msg.chat_id,
        msg.message_id,
        msg.user_id,
        decision.reason,
        decision.matched_value,
    )


def build_message_moderation_handler(
    settings: ModerationSettings,
    *,
    config_provider=None,
) -> MessageHandler:
    provider = config_provider or PaidGroupModerationConfigProvider(
        settings.moderation_config_file
    )

    async def _callback(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        await handle_message_moderation(
            update,
            context,
            settings=settings,
            config_provider=provider,
        )

    return MessageHandler(filters.ALL, _callback)
