import pytest

from src.services.redis_client import RedisClient
from src.services.task_registry import TaskRegistry


@pytest.mark.asyncio
async def test_active_task_reference_scan_is_one_atomic_server_side_read(monkeypatch):
    class FakeRedis:
        def __init__(self):
            self.eval_calls = []

        async def eval(self, script, numkeys, key, *candidate_keys):
            self.eval_calls.append((script, numkeys, key, candidate_keys))
            return [candidate_keys[1]]

    client = object.__new__(RedisClient)
    fake_redis = FakeRedis()
    client.redis = fake_redis
    monkeypatch.setattr("src.services.redis_client.REDIS_PREFIX", "prod_bot_")

    matches = await client.find_active_task_references_strict(
        ["source-a.png", "source-b.png"]
    )

    assert matches == {"source-b.png"}
    [(script, numkeys, key, candidate_keys)] = fake_redis.eval_calls
    assert numkeys == 1
    assert key == "prod_bot_active_tasks"
    assert candidate_keys == ("source-a.png", "source-b.png")
    assert "redis.call('HVALS', KEYS[1])" in script
    assert "pcall(cjson.decode, raw)" in script
    assert "redis.error_reply" in script


@pytest.mark.asyncio
async def test_active_task_reference_scan_skips_redis_for_empty_candidates(
    monkeypatch,
):
    class FakeRedis:
        async def eval(self, *_args):
            raise AssertionError("Redis must not be read for an empty candidate set")

    client = object.__new__(RedisClient)
    client.redis = FakeRedis()
    monkeypatch.setattr("src.services.redis_client.REDIS_PREFIX", "prod_bot_")

    assert await client.find_active_task_references_strict([]) == set()


@pytest.mark.asyncio
async def test_task_registry_closes_isolated_long_timeout_connection(monkeypatch):
    class FakeRedis:
        def __init__(self):
            self.closed = False

        async def aclose(self):
            self.closed = True

    fake_redis = FakeRedis()
    build_calls = []

    def build(url, **kwargs):
        build_calls.append((url, kwargs))
        return fake_redis

    async def find(self, keys):
        assert self.redis is fake_redis
        assert keys == ["source.png"]
        return {"source.png"}

    monkeypatch.setattr("src.services.task_registry.REDIS_URL", "redis://example")
    monkeypatch.setattr("src.services.task_registry.build_redis_client", build)
    monkeypatch.setattr(RedisClient, "find_active_task_references_strict", find)

    matches = await TaskRegistry.find_active_task_references_strict(
        ["source.png"],
        socket_timeout=60,
    )

    assert matches == {"source.png"}
    assert build_calls == [
        (
            "redis://example",
            {"decode_responses": True, "socket_timeout": 60},
        )
    ]
    assert fake_redis.closed is True
