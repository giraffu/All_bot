import functools

from telegram import Update
from telegram.ext import ContextTypes

from src.core.exceptions import AccessDeniedError, DomainException, InsufficientCreditsError
from src.utils import robust_send_message
from config import CHANNEL_INVITE_LINK


def with_unified_error_handler(func):
    """
    Decorator to catch DomainExceptions and translate them to user-friendly messages.
    """
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        try:
            return await func(update, context, *args, **kwargs)
        except InsufficientCreditsError as e:
            chat_id = update.effective_chat.id
            msg = (
                f"🚫 **灵石不足**\n\n"
                f"道友当前余额: `{e.current}` 灵石\n"
                f"本次修炼需要: `{e.cost}` 灵石\n"
                f"请联系管理员获取更多灵石。"
            )
            await robust_send_message(context.bot, chat_id, msg, parse_mode="Markdown")
            # Cleanup FSM contexts if they exist
            from telegram.ext import ConversationHandler
            return ConversationHandler.END
        except AccessDeniedError as e:
            chat_id = update.effective_chat.id
            invite_link = CHANNEL_INVITE_LINK or "https://t.me/AiVisionAV"
            msg = (
                "⛩️ **尚未拜入宗门**\n\n"
                "欲求长生，必先寻得仙缘。您需要先加入我们的 **官方宗门** 才能开始修炼。\n\n"
                f"👉 [点击即刻拜入宗门]({invite_link})"
            )
            await robust_send_message(context.bot, chat_id, msg, parse_mode="Markdown")
            from telegram.ext import ConversationHandler
            return ConversationHandler.END
        except DomainException as e:
            chat_id = update.effective_chat.id
            await robust_send_message(context.bot, chat_id, str(e), parse_mode="Markdown")
            from telegram.ext import ConversationHandler
            return ConversationHandler.END

    return wrapper
