import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.qqcc_channel_membership_service import (
    OfficialQqccChannelMembershipChecker,
    build_official_qqcc_channel_membership_checker,
)
from src.utils import get_user_channel_status


class FakeRedis:
    def __init__(self):
        self.values: dict[str, str] = {}
        self.get_calls: list[str] = []
        self.setex_calls: list[tuple[str, int, str]] = []

    async def get(self, key: str):
        self.get_calls.append(key)
        return self.values.get(key)

    async def setex(self, key: str, ttl: int, value: str):
        self.values[key] = value
        self.setex_calls.append((key, ttl, value))


@pytest.mark.asyncio
async def test_private_qqcc_context_uses_injected_official_checker_not_tenant_bot(
    monkeypatch,
):
    monkeypatch.setattr("src.utils.REQUIRED_CHANNEL_ID", "-100123")
    tenant_bot = SimpleNamespace(get_chat_member=AsyncMock())
    official_checker = AsyncMock(return_value=True)
    context = SimpleNamespace(
        bot=tenant_bot,
        bot_data={
            "bot_client_type": "bot:qqcc-private:7",
            "private_qqcc_bot_id": 7,
            "qqcc_channel_membership_checker": official_checker,
        },
    )

    assert await get_user_channel_status(context, 12345) is True
    official_checker.assert_awaited_once_with(12345)
    tenant_bot.get_chat_member.assert_not_awaited()


@pytest.mark.asyncio
async def test_private_qqcc_context_without_central_checker_falls_back_to_persisted_status(
    monkeypatch,
):
    monkeypatch.setattr("src.utils.REQUIRED_CHANNEL_ID", "-100123")
    tenant_bot = SimpleNamespace(get_chat_member=AsyncMock())
    context = SimpleNamespace(
        bot=tenant_bot,
        bot_data={
            "bot_client_type": "bot:qqcc-private:7",
            "private_qqcc_bot_id": 7,
        },
    )

    assert await get_user_channel_status(context, 12345) is None
    tenant_bot.get_chat_member.assert_not_awaited()


@pytest.mark.asyncio
async def test_official_qqcc_context_keeps_direct_bot_membership_check(monkeypatch):
    monkeypatch.setattr("src.utils.REQUIRED_CHANNEL_ID", "-100123")
    official_bot = SimpleNamespace(
        get_chat_member=AsyncMock(return_value=SimpleNamespace(status="member"))
    )
    context = SimpleNamespace(
        bot=official_bot,
        bot_data={"bot_client_type": "bot:qqcc"},
    )

    assert await get_user_channel_status(context, 12345) is True
    official_bot.get_chat_member.assert_awaited_once_with(
        chat_id=-100123,
        user_id=12345,
    )


@pytest.mark.asyncio
async def test_central_checker_reuses_shared_redis_status_before_official_bot(
    monkeypatch,
):
    monkeypatch.setattr(
        "src.services.qqcc_channel_membership_service.REQUIRED_CHANNEL_ID",
        "-100123",
    )
    redis = FakeRedis()
    redis.values["test:qqcc:channel-membership:12345"] = "1"
    official_bot = SimpleNamespace(get_chat_member=AsyncMock())
    checker = OfficialQqccChannelMembershipChecker(
        official_bot,
        redis=redis,
        redis_prefix="test:",
        initialize_bot=False,
    )

    assert await checker(12345) is True
    official_bot.get_chat_member.assert_not_awaited()


@pytest.mark.asyncio
async def test_central_checker_populates_shared_cache_from_official_bot(monkeypatch):
    monkeypatch.setattr(
        "src.services.qqcc_channel_membership_service.REQUIRED_CHANNEL_ID",
        "-100123",
    )
    monkeypatch.setattr("src.utils.REQUIRED_CHANNEL_ID", "-100123")
    redis = FakeRedis()
    official_bot = SimpleNamespace(
        get_chat_member=AsyncMock(return_value=SimpleNamespace(status="left"))
    )
    checker = OfficialQqccChannelMembershipChecker(
        official_bot,
        redis=redis,
        redis_prefix="test:",
        cache_ttl_seconds=45,
        negative_cache_ttl_seconds=5,
        initialize_bot=False,
    )

    assert await checker(12345) is False
    assert redis.setex_calls == [("test:qqcc:channel-membership:12345", 5, "0")]


def test_official_checker_factory_uses_private_https_transport_contract(monkeypatch):
    monkeypatch.setenv("BOT_TYPE", "PROD")
    monkeypatch.setenv("QQCC_BOT_TOKEN", "123456:official-membership-credential")
    monkeypatch.setenv(
        "PRIVATE_QQCC_BOT_TELEGRAM_API_BASE_URL",
        "https://api.telegram.org",
    )
    monkeypatch.setenv(
        "PRIVATE_QQCC_BOT_TELEGRAM_FILE_BASE_URL",
        "https://api.telegram.org/file/bot",
    )
    fake_bot = SimpleNamespace()
    bot_constructor = MagicMock(return_value=fake_bot)
    request = object()
    monkeypatch.setattr(
        "src.services.qqcc_channel_membership_service.Bot",
        bot_constructor,
    )
    monkeypatch.setattr(
        "src.services.qqcc_channel_membership_service.build_telegram_httpx_request",
        MagicMock(return_value=request),
    )

    checker = build_official_qqcc_channel_membership_checker(
        redis=None,
        redis_prefix="test:",
    )

    assert isinstance(checker, OfficialQqccChannelMembershipChecker)
    assert (
        bot_constructor.call_args.kwargs["base_url"] == "https://api.telegram.org/bot"
    )
    assert (
        bot_constructor.call_args.kwargs["base_file_url"]
        == "https://api.telegram.org/file/bot"
    )
    assert bot_constructor.call_args.kwargs["request"] is request


@pytest.mark.asyncio
async def test_central_checker_coalesces_concurrent_cross_tenant_cache_misses(
    monkeypatch,
):
    monkeypatch.setattr(
        "src.services.qqcc_channel_membership_service.REQUIRED_CHANNEL_ID",
        "-100123",
    )
    monkeypatch.setattr("src.utils.REQUIRED_CHANNEL_ID", "-100123")
    redis = FakeRedis()
    release = asyncio.Event()
    started = asyncio.Event()

    async def get_chat_member(**_kwargs):
        started.set()
        await release.wait()
        return SimpleNamespace(status="member")

    official_bot = SimpleNamespace(
        get_chat_member=AsyncMock(side_effect=get_chat_member)
    )
    checker = OfficialQqccChannelMembershipChecker(
        official_bot,
        redis=redis,
        redis_prefix="test:",
        initialize_bot=False,
    )

    checks = [asyncio.create_task(checker(12345)) for _ in range(10)]
    await asyncio.wait_for(started.wait(), timeout=1)
    await asyncio.sleep(0)
    assert official_bot.get_chat_member.await_count == 1

    release.set()
    assert await asyncio.gather(*checks) == [True] * 10
    assert official_bot.get_chat_member.await_count == 1
