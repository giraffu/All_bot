from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ChatJoinRequestHandler, ContextTypes

from paid_group_guard_bot.config import PaidGroupBotSettings
from paid_group_guard_bot.eligibility import check_paid_group_eligibility

logger = logging.getLogger(__name__)


async def handle_chat_join_request(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    settings: PaidGroupBotSettings,
    eligibility_checker=check_paid_group_eligibility,
) -> None:
    join_request = update.chat_join_request
    if join_request is None:
        return

    chat_id = int(join_request.chat.id)
    user = join_request.from_user
    telegram_id = int(user.id)

    if chat_id != settings.target_chat_id:
        logger.warning(
            "Ignoring join request for unexpected chat_id=%s user_id=%s",
            chat_id,
            telegram_id,
        )
        return

    decision = await eligibility_checker(telegram_id)
    logger.info(
        "Paid group join request user_id=%s chat_id=%s eligible=%s reason=%s "
        "internal_user_id=%s matched_order_id=%s",
        telegram_id,
        chat_id,
        decision.eligible,
        decision.reason,
        decision.internal_user_id,
        decision.matched_order_id,
    )

    if settings.dry_run:
        logger.info(
            "Dry-run enabled; no moderation action taken for user_id=%s",
            telegram_id,
        )
        return

    if decision.eligible:
        await context.bot.approve_chat_join_request(
            chat_id=chat_id,
            user_id=telegram_id,
        )
        logger.info("Approved paid group join request user_id=%s", telegram_id)
        return

    if settings.decline_unqualified:
        await context.bot.decline_chat_join_request(
            chat_id=chat_id,
            user_id=telegram_id,
        )
        logger.info(
            "Declined paid group join request user_id=%s reason=%s",
            telegram_id,
            decision.reason,
        )
        return

    logger.info(
        "Left unqualified paid group join request pending user_id=%s reason=%s",
        telegram_id,
        decision.reason,
    )


def build_chat_join_request_handler(
    settings: PaidGroupBotSettings,
) -> ChatJoinRequestHandler:
    async def _callback(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        await handle_chat_join_request(update, context, settings=settings)

    return ChatJoinRequestHandler(_callback)

