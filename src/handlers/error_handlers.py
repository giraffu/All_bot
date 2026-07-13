import functools
import logging

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from src.core.exceptions import (
    AccessDeniedError,
    DomainException,
    InsufficientCreditsError,
)
from src.services.fsm_temp_file_service import cleanup_fsm_user_data
from src.services.private_bot_update_admission import mark_private_bot_update_failed
from src.utils import robust_send_message
from src.i18n.translator import get_text
from config import CHANNEL_INVITE_LINK

logger = logging.getLogger(__name__)


def with_unified_error_handler(func):
    """
    Decorator to catch DomainExceptions and translate them to user-friendly messages.
    """

    @functools.wraps(func)
    async def wrapper(
        update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs
    ):
        try:
            return await func(update, context, *args, **kwargs)
        except InsufficientCreditsError as e:
            if update.effective_chat:
                lang = (
                    context.user_data.get("language_code", "zh")
                    if context.user_data
                    else "zh"
                )
                chat_id = update.effective_chat.id
                msg = get_text(
                    "system.error_insufficient_credits",
                    lang,
                    current=e.current,
                    cost=e.cost,
                )
                await robust_send_message(
                    context.bot, chat_id, msg, parse_mode="Markdown"
                )
            return ConversationHandler.END
        except AccessDeniedError:
            if update.effective_chat:
                lang = (
                    context.user_data.get("language_code", "zh")
                    if context.user_data
                    else "zh"
                )
                chat_id = update.effective_chat.id
                invite_link = CHANNEL_INVITE_LINK or "https://t.me/AiVisionAV"
                msg = get_text(
                    "system.error_access_denied", lang, invite_link=invite_link
                )
                await robust_send_message(
                    context.bot, chat_id, msg, parse_mode="Markdown"
                )
            return ConversationHandler.END
        except DomainException as e:
            if update.effective_chat:
                chat_id = update.effective_chat.id
                await robust_send_message(
                    context.bot, chat_id, str(e), parse_mode="Markdown"
                )
            return ConversationHandler.END

    return wrapper


async def _handle_global_error(
    update: object, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    全局兜底拦截器
    用于捕获游离于装饰器之外的业务异常，进行规范化的错误提示与状态清理
    """
    lang = context.user_data.get("language_code", "zh") if context.user_data else "zh"

    if isinstance(update, Update) and update.callback_query:
        try:
            await update.callback_query.answer()
        except Exception as e:
            logger.debug(f"Failed to answer callback query in error handler: {e}")

    # 安全清理可能存在的全局交互状态字典，防止幽灵死锁（仅清理业务临时数据，保留语言等偏好）
    cleanup_fsm_user_data(context.user_data)

    if isinstance(context.error, InsufficientCreditsError):
        if isinstance(update, Update) and update.effective_chat:
            msg = get_text(
                "system.error_insufficient_credits",
                lang,
                current=context.error.current,
                cost=context.error.cost,
            )
            await robust_send_message(
                context.bot, update.effective_chat.id, msg, parse_mode="Markdown"
            )

    elif isinstance(context.error, AccessDeniedError):
        if isinstance(update, Update) and update.effective_chat:
            invite_link = CHANNEL_INVITE_LINK or "https://t.me/AiVisionAV"
            msg = get_text("system.error_access_denied", lang, invite_link=invite_link)
            await robust_send_message(
                context.bot, update.effective_chat.id, msg, parse_mode="Markdown"
            )

    elif isinstance(context.error, DomainException):
        if isinstance(update, Update) and update.effective_chat:
            await robust_send_message(
                context.bot,
                update.effective_chat.id,
                str(context.error),
                parse_mode="Markdown",
            )

    else:
        mark_private_bot_update_failed()
        logger.error(
            f"Exception while handling an update: {context.error}",
            exc_info=context.error,
        )
        return


async def global_error_handler(
    update: object, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Run the global handler and fail private webhook admission if it fails.

    PTB reports exceptions raised by an error handler separately and does not
    reliably propagate them back through ``Application.process_update``. Mark
    the active private-Bot scope first so the stream worker leaves the update
    pending instead of ACKing an update whose user-facing error was never sent.
    """

    try:
        await _handle_global_error(update, context)
    except Exception as exc:
        mark_private_bot_update_failed()
        logger.error(
            "Global update error handler failed error_type=%s "
            "original_error_type=%s",
            type(exc).__name__,
            type(getattr(context, "error", None)).__name__,
        )
        raise
