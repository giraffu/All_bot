from types import SimpleNamespace

import pytest

from observer_bot.notifier import TelegramAdminNotifier
from observer_bot.runtime_config import ObserverRuntimeConfigProvider


class Repository:
    def __init__(self):
        self.calls = 0

    async def get_runtime_config(self):
        self.calls += 1
        return SimpleNamespace(admin_chat_ids=frozenset({42}))


@pytest.mark.asyncio
async def test_runtime_config_provider_caches_short_lived_database_config():
    repository = Repository()
    provider = ObserverRuntimeConfigProvider(repository, ttl_seconds=30)

    first = await provider.get()
    second = await provider.get()

    assert first is second
    assert repository.calls == 1


@pytest.mark.asyncio
async def test_notifier_loads_recipients_dynamically_and_records_attempts():
    bot = SimpleNamespace(send_message=_recording_send([]))
    config_provider = SimpleNamespace(
        get=lambda: _async_value(SimpleNamespace(admin_chat_ids=frozenset({42, 84})))
    )
    logged = []
    repository = SimpleNamespace(
        log_notification=lambda **kwargs: _append_async(logged, kwargs)
    )
    notifier = TelegramAdminNotifier(
        bot,
        runtime_config_provider=config_provider,
        repository=repository,
    )

    await notifier.send_admins("queue alert", event_type="queue_alert")

    assert [item["destination_chat_id"] for item in logged] == [42, 84]
    assert all(item["status"] == "sent" for item in logged)


def _recording_send(sent):
    async def send_message(**kwargs):
        sent.append(kwargs)

    return send_message


async def _async_value(value):
    return value


async def _append_async(items, value):
    items.append(value)
