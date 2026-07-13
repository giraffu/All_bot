from datetime import datetime

import pytest

from src.services.private_qqcc_bot_metrics import (
    collect_private_qqcc_runtime_metrics,
    publish_private_qqcc_worker_metrics,
)


class _Redis:
    def __init__(self):
        self.values = {}
        self.hashes = {}
        self.backlog = 12
        self.pending = 4

    async def set(self, key, value, *, ex):
        self.values[key] = (value, ex)
        return True

    async def get(self, key):
        item = self.values.get(key)
        return item[0] if item else None

    async def xlen(self, _key):
        return self.backlog

    async def xpending(self, _key, _group):
        return {"pending": self.pending}

    async def hgetall(self, key):
        return self.hashes.get(key, {})


@pytest.mark.asyncio
async def test_private_worker_metrics_publish_and_collect_runtime_health():
    redis = _Redis()
    redis.hashes["test:private_qqcc_bot:metrics:counters"] = {
        b"webhook_enqueued_total": b"55",
        b"webhook_queue_errors_total": b"2",
    }
    now = datetime(2026, 7, 12, 18, 0, 0)

    await publish_private_qqcc_worker_metrics(
        redis,
        active_applications=7,
        update_processing_failures=3,
        dead_lettered_updates=1,
        recovery_failures=2,
        inflight_updates=5,
        max_inflight_updates=64,
        deferred_updates=9,
        redis_prefix="test:",
        now=now,
    )
    result = await collect_private_qqcc_runtime_metrics(
        redis,
        redis_prefix="test:",
    )

    assert result["available"] is True
    assert result["stream_backlog"] == 12
    assert result["stream_pending"] == 4
    assert result["counters"]["webhook_enqueued_total"] == 55
    assert result["counters"]["webhook_queue_errors_total"] == 2
    assert result["worker"]["active_applications"] == 7
    assert result["worker"]["inflight_updates"] == 5
    assert result["worker"]["max_inflight_updates"] == 64
    assert result["worker"]["deferred_updates"] == 9
    assert result["worker"]["updated_at"] == now.isoformat()


@pytest.mark.asyncio
async def test_private_metrics_use_environment_specific_consumer_group(monkeypatch):
    redis = _Redis()
    seen = []

    async def _xpending(_key, group):
        seen.append(group)
        return {"pending": 0}

    redis.xpending = _xpending
    monkeypatch.setenv(
        "PRIVATE_QQCC_BOT_WORKER_CONSUMER_GROUP",
        "private-qqcc-bot-workers-test",
    )

    await collect_private_qqcc_runtime_metrics(redis, redis_prefix="test:")

    assert seen == ["private-qqcc-bot-workers-test"]


@pytest.mark.asyncio
async def test_private_runtime_metrics_fail_closed_to_sanitized_unavailable_state():
    class _BrokenRedis:
        async def xlen(self, _key):
            raise ConnectionError("secret redis endpoint")

    result = await collect_private_qqcc_runtime_metrics(
        _BrokenRedis(),
        redis_prefix="test:",
    )

    assert result == {
        "available": False,
        "error_code": "private_bot_metrics_unavailable",
    }
