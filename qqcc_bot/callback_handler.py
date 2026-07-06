import logging

from telegram import Update
from telegram.ext import ContextTypes

import src.handlers.callback_router as router

# Import only the callback modules needed by the QQCC lazy bot surface.
import src.handlers.callbacks.gallery_callbacks_interactions  # noqa: F401
import src.handlers.callbacks.misc_callbacks  # noqa: F401
import src.handlers.callbacks.task_callbacks  # noqa: F401
import qqcc_bot.gallery_market  # noqa: F401

from src.handlers.utils import with_db_logging_context
from src.services.permission_service import permission_service
from src.utils import safe_answer_query

logger = logging.getLogger("qqcc_bot.callback")

QQCC_REQUIRED_CALLBACK_PREFIXES = (
    "noop",
    "cancel_task_",
    "public_share",
    "rate_like",
    "qvid_mode:",
    "qg:m",
    "qg:p:",
    "qg:l:",
    "qg:d:",
    "qg:a:",
)

router.validate_callback_routes(
    required_prefixes=QQCC_REQUIRED_CALLBACK_PREFIXES,
    namespace="QQCC bot",
)


@with_db_logging_context
async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    logger.info(
        "QQCC callback received: %s, routes=%s",
        query.data,
        len(router.SORTED_ROUTES),
    )

    if not update.effective_user:
        return
    user = update.effective_user
    await permission_service.ensure_user(
        user.id, user.username, user.full_name, user.language_code
    )

    for prefix in router.SORTED_ROUTES:
        if query.data.startswith(prefix):
            return await router.CALLBACK_ROUTES[prefix](update, context)

    logger.warning("Unmatched QQCC callback data: %s", query.data)
    await safe_answer_query(query)
    await query.message.reply_text(context.t("system.callback_expired"))
