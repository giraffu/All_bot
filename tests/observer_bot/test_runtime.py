from types import SimpleNamespace

import pytest
from telegram.ext import CommandHandler, MessageHandler

from observer_bot.config import ObserverSettings
from observer_bot.main import build_application
from observer_bot.notifier import split_telegram_text


class FakeClosable:
    async def open(self):
        return None

    async def close(self):
        return None

    async def bootstrap_runtime_config(self, **_kwargs):
        return None

    async def get_runtime_config(self):
        return SimpleNamespace(
            admin_chat_ids=frozenset({42}),
            authorized_group_ids=frozenset({-1001}),
            queue_alerts_enabled=True,
            group_collection_enabled=True,
            daily_reports_enabled=True,
            weekly_reports_enabled=True,
            monthly_reports_enabled=True,
        )


def _settings():
    return ObserverSettings(
        token="123:observer-token",
        database_url="postgresql://observer@db/observer_prod",
        admin_chat_ids=frozenset({42}),
        authorized_group_ids=frozenset({-1001}),
        lm_studio_base_url="http://lmstudio:1234",
    )


def test_observer_application_registers_only_its_commands_and_group_collection():
    app = build_application(
        _settings(),
        repository=FakeClosable(),
        queue_client=FakeClosable(),
        lm_client=FakeClosable(),
    )
    handlers = [handler for group in app.handlers.values() for handler in group]

    command_handlers = [handler for handler in handlers if isinstance(handler, CommandHandler)]
    message_handlers = [handler for handler in handlers if isinstance(handler, MessageHandler)]
    commands = {command for handler in command_handlers for command in handler.commands}

    assert commands == {"start", "status", "report"}
    assert len(message_handlers) == 2  # new and edited authorized group messages


def test_split_telegram_text_keeps_every_message_within_limit():
    text = ("line\n" * 2000).strip()

    chunks = split_telegram_text(text, limit=3900)

    assert "\n".join(chunks) == text
    assert all(len(chunk) <= 3900 for chunk in chunks)


@pytest.mark.asyncio
async def test_runtime_rejects_non_admin_status_command():
    from observer_bot.runtime import handle_status

    replies = []
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=99),
        effective_chat=SimpleNamespace(type="private"),
        effective_message=SimpleNamespace(reply_text=lambda text: replies.append(text)),
    )
    context = SimpleNamespace(
        application=SimpleNamespace(
            bot_data={
                "runtime_config_provider": SimpleNamespace(
                    get=lambda: _async_value(SimpleNamespace(admin_chat_ids=frozenset({42})))
                )
            }
        )
    )

    await handle_status(update, context)

    assert replies == []


async def _async_value(value):
    return value
