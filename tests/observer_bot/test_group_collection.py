from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from observer_bot.handlers import collect_authorized_group_message


class RecordingRepository:
    def __init__(self):
        self.messages = []

    async def save_group_message(self, message):
        self.messages.append(message)


class RuntimeConfigProvider:
    def __init__(self, *, enabled=True, group_ids=frozenset({-1001})):
        self.config = SimpleNamespace(
            group_collection_enabled=enabled,
            authorized_group_ids=group_ids,
        )

    async def get(self):
        return self.config


def _update(*, chat_id=-1001, text="hello", is_bot=False):
    user = SimpleNamespace(
        id=42,
        username="alice",
        full_name="Alice",
        is_bot=is_bot,
    )
    message = SimpleNamespace(
        message_id=7,
        message_thread_id=None,
        text=text,
        caption=None,
        date=datetime(2026, 8, 29, tzinfo=timezone.utc),
        edit_date=None,
        from_user=user,
    )
    return SimpleNamespace(
        effective_chat=SimpleNamespace(id=chat_id, title="Authorized Group"),
        effective_message=message,
    )


@pytest.mark.asyncio
async def test_authorized_group_text_is_persisted():
    repository = RecordingRepository()
    context = SimpleNamespace(
        application=SimpleNamespace(
            bot_data={
                "runtime_config_provider": RuntimeConfigProvider(),
                "repository": repository,
            }
        )
    )

    await collect_authorized_group_message(_update(), context)

    assert len(repository.messages) == 1
    assert repository.messages[0].chat_id == -1001
    assert repository.messages[0].content == "hello"
    assert repository.messages[0].author_user_id == 42


@pytest.mark.asyncio
async def test_unapproved_group_and_bot_messages_are_not_persisted():
    repository = RecordingRepository()
    context = SimpleNamespace(
        application=SimpleNamespace(
            bot_data={
                "runtime_config_provider": RuntimeConfigProvider(),
                "repository": repository,
            }
        )
    )

    await collect_authorized_group_message(_update(chat_id=-9999), context)
    await collect_authorized_group_message(_update(is_bot=True), context)

    assert repository.messages == []


@pytest.mark.asyncio
async def test_group_collection_can_be_disabled_without_restarting_bot():
    repository = RecordingRepository()
    context = SimpleNamespace(
        application=SimpleNamespace(
            bot_data={
                "runtime_config_provider": RuntimeConfigProvider(enabled=False),
                "repository": repository,
            }
        )
    )

    await collect_authorized_group_message(_update(), context)

    assert repository.messages == []
