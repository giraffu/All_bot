import asyncio
import contextlib
import logging

from telegram import Update
from telegram.ext import ContextTypes

import src.handlers.callback_router as router

# Import only the callback modules needed by the QQCC lazy bot surface.
import src.handlers.callbacks.gallery_callbacks_interactions  # noqa: F401
import src.handlers.callbacks.misc_callbacks  # noqa: F401
import src.handlers.callbacks.task_callbacks  # noqa: F401
import qqcc_bot.gallery_market  # noqa: F401
import qqcc_bot.regeneration_callback  # noqa: F401
import qqcc_bot.result_followup_callback  # noqa: F401

from src.handlers.utils import with_db_logging_context
from src.services.permission_service import permission_service
from src.utils import safe_answer_query

logger = logging.getLogger("qqcc_bot.callback")

QQCC_CALLBACK_HANDLER_TIMEOUT_SECONDS = 45.0
QQCC_CALLBACK_TIMEOUT_NOTICE_SECONDS = 5.0

QQCC_REQUIRED_CALLBACK_PREFIXES = (
    "noop",
    "cancel_task_",
    "public_share",
    "rate_like",
    "qqcc_regenerate",
    "qfu",
    "qvid_mode:",
    "qg:m",
    "qg:p:",
    "qg:l:",
    "qg:d:",
    "qg:a:",
)
QQCC_DISABLED_PUBLISH_CALLBACK_PREFIXES = (
    "submit_gallery_",
    "public_share",
)

router.validate_callback_routes(
    required_prefixes=QQCC_REQUIRED_CALLBACK_PREFIXES,
    namespace="QQCC bot",
)


@with_db_logging_context
async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = str(query.data or "")
    logger.info(
        "QQCC callback received: %s, routes=%s",
        data,
        len(router.SORTED_ROUTES),
    )

    if not update.effective_user:
        return
    if data.startswith(QQCC_DISABLED_PUBLISH_CALLBACK_PREFIXES):
        await safe_answer_query(
            query,
            text="功能暂未开放",
            show_alert=True,
        )
        return

    user = update.effective_user
    await permission_service.ensure_user(
        user.id, user.username, user.full_name, user.language_code
    )

    for prefix in router.SORTED_ROUTES:
        if data.startswith(prefix):
            try:
                return await asyncio.wait_for(
                    router.CALLBACK_ROUTES[prefix](update, context),
                    timeout=QQCC_CALLBACK_HANDLER_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                logger.error(
                    "QQCC callback handler timed out prefix=%s timeout_seconds=%.1f",
                    prefix,
                    QQCC_CALLBACK_HANDLER_TIMEOUT_SECONDS,
                )
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(
                        safe_answer_query(
                            query,
                            text="处理超时，请重试",
                            show_alert=True,
                        ),
                        timeout=QQCC_CALLBACK_TIMEOUT_NOTICE_SECONDS,
                    )
                return None

    logger.warning("Unmatched QQCC callback data: %s", data)
    await safe_answer_query(query)
    await query.message.reply_text(context.t("system.callback_expired"))
