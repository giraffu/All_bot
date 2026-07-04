from unittest.mock import AsyncMock

import pytest

from src.services.redis_client import RedisClient


@pytest.mark.asyncio
async def test_set_comment_lock_fails_open_when_redis_errors(monkeypatch):
    client = RedisClient()
    fake_redis = type(
        "FakeRedis",
        (),
        {"set": AsyncMock(side_effect=RuntimeError("redis down"))},
    )()
    monkeypatch.setattr(client, "redis", fake_redis)

    assert await client.set_comment_lock(123, ttl=5) is True


@pytest.mark.asyncio
async def test_pending_web_finalizer_lock_fails_closed_when_redis_errors(monkeypatch):
    client = RedisClient()
    fake_redis = type(
        "FakeRedis",
        (),
        {"set": AsyncMock(side_effect=RuntimeError("redis down"))},
    )()
    monkeypatch.setattr(client, "redis", fake_redis)

    assert await client.acquire_pending_web_finalizer_lock("registry-1") is None


@pytest.mark.asyncio
async def test_get_all_user_concurrencies_uses_scan_not_keys(monkeypatch):
    client = RedisClient()

    class FakePipeline:
        def __init__(self):
            self.keys = []

        def get(self, key):
            self.keys.append(key)
            return self

        async def execute(self):
            return ["2", "0", None]

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc_info):
            return False

    class FakeRedis:
        async def keys(self, *_args, **_kwargs):
            raise AssertionError("KEYS must not be used")

        async def scan_iter(self, match=None, count=None):
            assert match.endswith("user_concurrency:*")
            assert count == 500
            yield "prod_bot_user_concurrency:123"
            yield b"prod_bot_user_concurrency:456"
            yield "prod_bot_user_concurrency:789"

        def pipeline(self, transaction=False):
            assert transaction is False
            return FakePipeline()

    monkeypatch.setattr(client, "redis", FakeRedis())
    monkeypatch.setattr("src.services.redis_client.REDIS_PREFIX", "prod_bot_")

    assert await client.get_all_user_concurrencies() == {123: 2}
