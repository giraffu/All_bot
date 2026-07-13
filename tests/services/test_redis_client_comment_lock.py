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


@pytest.mark.asyncio
async def test_task_idempotent_concurrency_release_uses_atomic_redis_marker(monkeypatch):
    client = RedisClient()
    eval_script = AsyncMock(return_value=1)
    monkeypatch.setattr(
        client,
        "redis",
        type("FakeRedis", (), {"eval": eval_script})(),
    )
    monkeypatch.setattr("src.services.redis_client.REDIS_PREFIX", "prod_bot_")

    result = await client.decrement_user_concurrency(
        123,
        idempotency_key="task_concurrency:task-a",
    )

    assert result == 1
    args = eval_script.await_args.args
    assert args[1:] == (
        3,
        "prod_bot_user_concurrency:123",
        "prod_bot_acquired_task_concurrency:123",
        "prod_bot_acquired_task_concurrency",
        "task_concurrency:task-a",
        "3600",
    )
    assert "ZREM" in args[0]


@pytest.mark.asyncio
async def test_task_idempotent_concurrency_acquire_returns_existing_ownership(monkeypatch):
    client = RedisClient()
    eval_script = AsyncMock(return_value=[2, 0])
    monkeypatch.setattr(
        client,
        "redis",
        type("FakeRedis", (), {"eval": eval_script})(),
    )
    monkeypatch.setattr("src.services.redis_client.REDIS_PREFIX", "prod_bot_")

    result = await client.increment_user_concurrency(
        123,
        idempotency_key="task_concurrency:task-a",
    )

    assert result == (2, False)
    args = eval_script.await_args.args
    assert args[1:-1] == (
        3,
        "prod_bot_user_concurrency:123",
        "prod_bot_acquired_task_concurrency:123",
        "prod_bot_acquired_task_concurrency",
        "task_concurrency:task-a",
    )
    assert float(args[-1]) > 0
    assert "ZADD" in args[0]


@pytest.mark.asyncio
async def test_task_concurrency_release_consumes_only_matching_acquire(monkeypatch):
    class MarkerRedis:
        def __init__(self):
            self.count = 0
            self.acquired = set()

        async def eval(
            self,
            script,
            _numkeys,
            _counter,
            _markers,
            _legacy_markers,
            identity,
            *args,
        ):
            if "ZADD" in script:
                if identity in self.acquired:
                    return [self.count, 0]
                self.acquired.add(identity)
                self.count += 1
                return [self.count, 1]
            if "ZREM" in script:
                if identity not in self.acquired:
                    return self.count
                self.acquired.remove(identity)
                self.count = max(0, self.count - 1)
                return self.count
            raise AssertionError("unexpected script")

    client = RedisClient()
    redis = MarkerRedis()
    monkeypatch.setattr(client, "redis", redis)

    assert await client.decrement_user_concurrency(
        1,
        idempotency_key="task_concurrency:never-acquired",
    ) == 0
    assert await client.increment_user_concurrency(
        1,
        idempotency_key="task_concurrency:task-a",
    ) == (1, True)
    assert await client.increment_user_concurrency(
        1,
        idempotency_key="task_concurrency:task-a",
    ) == (1, False)
    assert await client.decrement_user_concurrency(
        1,
        idempotency_key="task_concurrency:task-a",
    ) == 0
    assert await client.decrement_user_concurrency(
        1,
        idempotency_key="task_concurrency:task-a",
    ) == 0
    assert redis.count == 0


@pytest.mark.asyncio
async def test_long_lived_task_release_cannot_decrement_newer_task(monkeypatch):
    class MarkerRedis:
        def __init__(self):
            self.count = 0
            self.acquired = set()

        async def eval(
            self,
            script,
            _numkeys,
            _counter,
            _markers,
            _legacy_markers,
            identity,
            *args,
        ):
            if "ZADD" in script:
                added = identity not in self.acquired
                self.acquired.add(identity)
                self.count = len(self.acquired)
                return [self.count, int(added)]
            if "ZREM" in script:
                self.acquired.discard(identity)
                self.count = len(self.acquired)
                return self.count
            raise AssertionError("unexpected script")

    client = RedisClient()
    redis = MarkerRedis()
    monkeypatch.setattr(client, "redis", redis)

    await client.increment_user_concurrency(
        1,
        idempotency_key="task_concurrency:task-a",
    )
    # The old scalar key may expire, but task A's ownership marker remains.
    redis.count = 0
    assert await client.increment_user_concurrency(
        1,
        idempotency_key="task_concurrency:task-b",
    ) == (2, True)
    assert await client.decrement_user_concurrency(
        1,
        idempotency_key="task_concurrency:task-a",
    ) == 1
    assert redis.acquired == {"task_concurrency:task-b"}


@pytest.mark.asyncio
async def test_stale_concurrency_repair_preserves_live_pre_registry_marker(monkeypatch):
    client = RedisClient()
    releases = []

    class FakeRedis:
        async def scan_iter(self, match=None, count=None):
            assert match.endswith("acquired_task_concurrency:*")
            yield "prod_bot_acquired_task_concurrency:123"

        async def zrangebyscore(self, *_args):
            return [
                "task_concurrency:live-task",
                "task_concurrency:stale-task",
            ]

    async def release(user_id, *, idempotency_key):
        releases.append((user_id, idempotency_key))
        return 0

    monkeypatch.setattr(client, "redis", FakeRedis())
    monkeypatch.setattr(client, "decrement_user_concurrency", release)
    monkeypatch.setattr("src.services.redis_client.REDIS_PREFIX", "prod_bot_")

    removed = await client.repair_stale_user_concurrency_acquisitions(
        active_registry_task_ids={"live-task"},
        stale_before_timestamp=123.0,
    )

    assert removed == 1
    assert releases == [(123, "task_concurrency:stale-task")]
