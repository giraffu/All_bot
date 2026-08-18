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
async def test_pending_web_finalizer_write_updates_hash_due_and_backend_index(
    monkeypatch,
):
    operations = []

    class FakePipeline:
        def hset(self, *args, **kwargs):
            operations.append(("hset", args, kwargs))
            return self

        def zadd(self, *args, **kwargs):
            operations.append(("zadd", args, kwargs))
            return self

        def sadd(self, *args, **kwargs):
            operations.append(("sadd", args, kwargs))
            return self

        async def execute(self):
            return [1] * len(operations)

    class FakeRedis:
        def pipeline(self, transaction=False):
            assert transaction is True
            return FakePipeline()

    client = RedisClient()
    monkeypatch.setattr(client, "redis", FakeRedis())
    monkeypatch.setattr("src.services.redis_client.REDIS_PREFIX", "prod_bot_")

    await client.add_pending_web_finalizer(
        "registry-1",
        {"backend_task_id": "backend-1", "phase": "accepted"},
        due_at=123.5,
    )

    assert operations[0][0] == "hset"
    assert operations[0][1][:2] == (
        "prod_bot_pending_web_finalizers",
        "registry-1",
    )
    assert operations[1] == (
        "zadd",
        ("prod_bot_pending_web_finalizers:due", {"registry-1": 123.5}),
        {},
    )
    assert operations[2] == (
        "hset",
        (
            "prod_bot_pending_web_finalizers:backend_index",
            "backend-1",
            "registry-1",
        ),
        {},
    )
    assert operations[3] == (
        "sadd",
        ("prod_bot_pending_web_finalizer_backends:registry-1", "backend-1"),
        {},
    )


@pytest.mark.asyncio
async def test_pending_web_finalizer_due_read_is_bounded(monkeypatch):
    client = RedisClient()
    zrangebyscore = AsyncMock(return_value=["registry-1", "registry-2"])
    monkeypatch.setattr(
        client,
        "redis",
        type("FakeRedis", (), {"zrangebyscore": zrangebyscore})(),
    )
    monkeypatch.setattr("src.services.redis_client.REDIS_PREFIX", "prod_bot_")

    assert await client.get_due_pending_web_finalizer_ids(
        now=456.0,
        limit=25,
    ) == ["registry-1", "registry-2"]
    zrangebyscore.assert_awaited_once_with(
        "prod_bot_pending_web_finalizers:due",
        "-inf",
        456.0,
        start=0,
        num=25,
    )


@pytest.mark.asyncio
async def test_legacy_finalizer_index_uses_hscan_and_zadd_nx(monkeypatch):
    operations = []

    class FakePipeline:
        def zadd(self, *args, **kwargs):
            operations.append(("zadd", args, kwargs))
            return self

        def hset(self, *args, **kwargs):
            operations.append(("hset", args, kwargs))
            return self

        def sadd(self, *args, **kwargs):
            operations.append(("sadd", args, kwargs))
            return self

        async def execute(self):
            return [1] * len(operations)

    class FakeRedis:
        async def hscan(self, key, cursor, count):
            assert key == "prod_bot_pending_web_finalizers"
            assert (cursor, count) == (17, 200)
            return 0, {
                "registry-1": '{"backend_task_id": "backend-1"}',
                "registry-bad": "not-json",
            }

        async def hgetall(self, *_args, **_kwargs):
            raise AssertionError("HGETALL must not be used")

        def pipeline(self, transaction=False):
            assert transaction is True
            return FakePipeline()

    client = RedisClient()
    monkeypatch.setattr(client, "redis", FakeRedis())
    monkeypatch.setattr("src.services.redis_client.REDIS_PREFIX", "prod_bot_")

    assert await client.index_legacy_pending_web_finalizers(
        cursor=17,
        due_at=789.0,
        count=200,
    ) == (0, 2)
    zadds = [operation for operation in operations if operation[0] == "zadd"]
    assert len(zadds) == 2
    assert all(operation[2] == {"nx": True} for operation in zadds)


@pytest.mark.asyncio
async def test_remove_pending_web_finalizer_cleans_due_and_backend_indexes(monkeypatch):
    operations = []

    class FakePipeline:
        def __getattr__(self, name):
            def record(*args, **kwargs):
                operations.append((name, args, kwargs))
                return self

            return record

        async def execute(self):
            return [1] * len(operations)

    class FakeRedis:
        async def smembers(self, key):
            assert key == "prod_bot_pending_web_finalizer_backends:registry-1"
            return {"backend-1", "backend-2"}

        def pipeline(self, transaction=False):
            assert transaction is True
            return FakePipeline()

    client = RedisClient()
    monkeypatch.setattr(client, "redis", FakeRedis())
    monkeypatch.setattr("src.services.redis_client.REDIS_PREFIX", "prod_bot_")

    await client.remove_pending_web_finalizer("registry-1")

    assert ("hdel", ("prod_bot_pending_web_finalizers", "registry-1"), {}) in operations
    assert (
        "zrem",
        ("prod_bot_pending_web_finalizers:due", "registry-1"),
        {},
    ) in operations
    backend_hdel = next(operation for operation in operations if operation[0] == "hdel" and "backend_index" in operation[1][0])
    assert set(backend_hdel[1][1:]) == {"backend-1", "backend-2"}


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
async def test_get_user_concurrency_reads_live_counter_without_mutation(monkeypatch):
    client = RedisClient()
    get = AsyncMock(return_value="3")
    monkeypatch.setattr(
        client,
        "redis",
        type("FakeRedis", (), {"get": get})(),
    )
    monkeypatch.setattr("src.services.redis_client.REDIS_PREFIX", "prod_bot_")

    assert await client.get_user_concurrency(123) == 3
    get.assert_awaited_once_with("prod_bot_user_concurrency:123")


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
