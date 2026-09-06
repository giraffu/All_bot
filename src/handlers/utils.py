from functools import wraps

from telegram import Update
from telegram.ext import ContextTypes

from src.context import user_id_ctx
from src.services.permission_service import permission_service
from src.utils import (
    create_background_task,
    get_user_channel_status,
    notify_inviter_reward,
)


def with_db_logging_context(func):
    @wraps(func)
    async def wrapper(
        update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs
    ):
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


async def ensure_access_and_reward(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> bool:
    """
    Check access and trigger background reward notification if needed.
    Returns True if access is granted (or exception raised), False if no user.
    """
    user = update.effective_user
    if not user:
        return False

    is_member = await get_user_channel_status(context, user.id)
    inviter_id = await permission_service.check_access(
        user.id, user.username, user.full_name, is_member
    )

    if inviter_id:
        create_background_task(
            context, notify_inviter_reward(context.bot, inviter_id, user.full_name)
        )

    return True


def _is_mentioned(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    msg = update.message
    chat = update.effective_chat

    if chat.type not in ["group", "supergroup"]:
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
                text = text_content[entity.offset : entity.offset + entity.length]
                if text.lower() == f"@{bot_username.lower()}":
                    return True
    return False
