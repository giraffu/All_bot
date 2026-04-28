from telegram import Update
from telegram.ext import ContextTypes
from functools import wraps
import logging
from src.context import user_id_ctx
from src.utils import robust_send_message
from src.core.task_core import CoreDomainError, InsufficientCreditsError, ConcurrencyLimitError

logger = logging.getLogger(__name__)

def with_db_logging_context(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        token = None
        if user:
            token = user_id_ctx.set(user.id)
        
        try:
            return await func(update, context, *args, **kwargs)
        finally:
            if token:
                user_id_ctx.reset(token)
    return wrapper

def with_unified_error_handler(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        try:
            return await func(update, context, *args, **kwargs)
        except ConcurrencyLimitError as e:
            if update.effective_chat:
                await robust_send_message(context.bot, update.effective_chat.id, f"⚠️ {e}")
        except InsufficientCreditsError as e:
            if update.effective_chat:
                await robust_send_message(context.bot, update.effective_chat.id, f"⚠️ {e}")
        except CoreDomainError as e:
            if update.effective_chat:
                await robust_send_message(context.bot, update.effective_chat.id, f"❌ {e}")
        except Exception as e:
            logger.error(f"Unhandled exception in handler {func.__name__}: {e}", exc_info=True)
            if update.effective_chat:
                error_msg = str(e)
                if any(kw in error_msg for kw in ["Circuit is open", "All connection attempts failed", "Connection refused", "timeout", "ConnectError"]) or "CircuitBreaker" in str(type(e)):
                    user_msg = "当前服务器繁忙，请稍后再试"
                else:
                    user_msg = f"系统错误：{error_msg}"
                await robust_send_message(context.bot, update.effective_chat.id, f"❌ {user_msg}")
    return wrapper

def _is_mentioned(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    msg = update.message
    chat = update.effective_chat
    
    if chat.type not in ['group', 'supergroup']:
        return True
        
    bot_username = context.bot.username
    
    # 1. Reply check
    if msg.reply_to_message and msg.reply_to_message.from_user.id == context.bot.id:
        return True
        
    # 2. Mention check (Caption or Text)
    entities = msg.caption_entities if msg.caption else msg.entities
    if entities:
        text_content = msg.caption if msg.caption else msg.text
        for entity in entities:
            if entity.type == "mention":
                text = text_content[entity.offset:entity.offset + entity.length]
                if text.lower() == f"@{bot_username.lower()}":
                    return True
    return False

class MockMessage:
    """Mock Message object for reuse in utility functions"""
    def __init__(self, bot, chat_id, message_id):
        self.bot = bot
        self.chat_id = chat_id
        self.message_id = message_id
        self.chat = type('obj', (object,), {'id': chat_id})
    
    async def edit_text(self, text, **kwargs):
        return await self.bot.edit_message_text(
            chat_id=self.chat_id,
            message_id=self.message_id,
            text=text,
            **kwargs
        )
        
    async def delete(self):
        return await self.bot.delete_message(
            chat_id=self.chat_id,
            message_id=self.message_id
        )
    
    async def reply_text(self, text, **kwargs):
        return await self.bot.send_message(
            chat_id=self.chat_id,
            text=text,
            **kwargs
        )
