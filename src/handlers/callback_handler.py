import logging

from telegram import Update
from telegram.ext import ContextTypes

import src.handlers.callback_router as router

# 导入拆分后的子模块，触发装饰器注册路由
import src.handlers.callbacks.affiliate_callbacks  # noqa: F401
import src.handlers.callbacks.billing_callbacks  # noqa: F401
import src.handlers.callbacks.gallery_callbacks  # noqa: F401
import src.handlers.callbacks.misc_callbacks  # noqa: F401
import src.handlers.callbacks.task_callbacks  # noqa: F401

from src.handlers.utils import with_db_logging_context
from src.services.permission_service import permission_service
from src.utils import safe_answer_query

logger = logging.getLogger(__name__)


@with_db_logging_context
async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle callback queries from inline keyboards using prefix-based routing.
    """
    query = update.callback_query
    logger.info(
        f"handle_callback_query received: {query.data}, SORTED_ROUTES count: {len(router.SORTED_ROUTES)}"
    )

    # 身份强同步保留
    if not update.effective_user:
        return
    user = update.effective_user
    await permission_service.ensure_user(
        user.id, user.username, user.full_name, user.language_code
    )

    # 按前缀长度降序匹配，防止短前缀劫持长前缀
    for prefix in router.SORTED_ROUTES:
        if query.data.startswith(prefix):
            return await router.CALLBACK_ROUTES[prefix](update, context)

    # 兜底机制 (Fallback)
    logger.warning(f"Unmatched callback data: {query.data}")
    await safe_answer_query(query)
    await query.message.reply_text("该按钮已过期或系统升级中，请重新发送指令。")
