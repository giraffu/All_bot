import logging

from telegram import Update
from telegram.ext import ContextTypes

from src.core.task_core import cancel_user_task, CoreDomainError
from src.core.user_core import get_or_create_user_by_telegram
from src.handlers.callback_router import register_callback
from src.utils import safe_answer_query

logger = logging.getLogger(__name__)

@register_callback("cancel_task_")
async def cancel_task_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    task_id = query.data.replace("cancel_task_", "")

    internal_user, _ = await get_or_create_user_by_telegram(
        update.effective_user.id,
        update.effective_user.username
    )

    try:
        cancel_result = await cancel_user_task(task_id, internal_user.id)
        cancel_state = cancel_result.get("state")
        cancel_message = cancel_result.get("message", "撤销请求失败，请稍后重试")
        await safe_answer_query(
            query,
            text=cancel_message,
            show_alert=cancel_state == "not_cancellable",
        )
    except CoreDomainError as e:
        await safe_answer_query(query, text=str(e), show_alert=True)
    except Exception as e:
        logger.error(f"撤销失败: {e}")
        await safe_answer_query(query, text="撤销失败，请稍后重试", show_alert=True)
