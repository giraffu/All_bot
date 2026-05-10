import logging

from telegram import Update
from telegram.ext import ContextTypes

from src.core.task_core import cancel_user_task, CoreDomainError
from src.core.user_core import get_or_create_user_by_telegram
from src.handlers.callback_router import register_callback

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
        await cancel_user_task(task_id, internal_user.id)
        await query.answer("撤销指令已发送，正在处理...", show_alert=False)
    except CoreDomainError as e:
        await query.answer(str(e), show_alert=True)
    except Exception as e:
        logger.error(f"撤销失败: {e}")
        await query.answer("撤销失败，请稍后重试", show_alert=True)