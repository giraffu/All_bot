from __future__ import annotations

from observer_bot.domain import GroupMessage


async def collect_authorized_group_message(update, context) -> None:
    chat = update.effective_chat
    message = update.effective_message
    if chat is None or message is None:
        return

    runtime_config = await context.application.bot_data[
        "runtime_config_provider"
    ].get()
    if (
        not runtime_config.group_collection_enabled
        or int(chat.id) not in runtime_config.authorized_group_ids
    ):
        return

    author = message.from_user
    if author is not None and author.is_bot:
        return

    content = str(message.text or message.caption or "").strip()
    if not content:
        return

    await context.application.bot_data["repository"].save_group_message(
        GroupMessage(
            chat_id=int(chat.id),
            message_id=int(message.message_id),
            thread_id=(
                int(message.message_thread_id)
                if message.message_thread_id is not None
                else None
            ),
            chat_title=str(chat.title or chat.id),
            author_user_id=int(author.id) if author is not None else None,
            author_username=str(author.username or "") if author is not None else "",
            author_display_name=str(author.full_name or "") if author is not None else "",
            content=content,
            sent_at=message.date,
            edited_at=message.edit_date,
        )
    )
