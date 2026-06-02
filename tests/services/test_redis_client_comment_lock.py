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
