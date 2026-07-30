import asyncio
import json
from types import SimpleNamespace

import pytest

from src.ops import generation_release_refund as refund


class FakeRedis:
    def __init__(self, *, pending=None, running=None, active_tasks=None, race=None):
        self.pending = list(pending or [])
        self.running = set(running or [])
        self.active_tasks = dict(active_tasks or {})
        self.race = set(race or [])
        self.hash_writes = []
        self.published = []

    async def zrange(self, _key, _start, _end):
        return list(self.pending)

    async def smembers(self, _key):
        return set(self.running)

    async def hgetall(self, _key):
        return dict(self.active_tasks)

    async def zrem(self, _key, item):
        if item in self.race or item not in self.pending:
            return 0
        self.pending.remove(item)
        return 1

    async def hset(self, key, mapping):
        self.hash_writes.append((key, mapping))

    async def srem(self, _key, item):
        self.running.discard(item)

    async def publish(self, channel, payload):
        self.published.append((channel, payload))


def active(registry_id="registry-1", backend_id="backend-1", user_id=7, cost=2):
    return {
        registry_id: json.dumps(
            {
                "backend_task_id": backend_id,
                "user_id": user_id,
                "username": "secret-name",
                "cost": cost,
            }
        )
    }


def run_refund(worker, app, *, execute=False, finalize=None):
    calls = []

    async def default_finalize(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(refunded=True)

    async def sync(*args):
        calls.append(("sync", args))

    summary = asyncio.run(
        refund.refund_pending_tasks(
            worker_redis=worker,
            app_redis=app,
            redis_prefix="prod_bot_",
            threshold=10,
            allow_above_threshold=True,
            execute=execute,
            finalize_task_failure_func=finalize or default_finalize,
            sync_user_concurrency_func=sync,
        )
    )
    return summary, calls


def test_dry_run_is_summary_only_and_has_no_pii():
    worker = FakeRedis(pending=["backend-1"])
    app = FakeRedis(active_tasks=active())

    summary, calls = run_refund(worker, app)
    rendered = json.dumps(summary.__dict__)

    assert summary.mapped_pending_count == 1
    assert calls == []
    assert "secret-name" not in rendered
    assert "backend-1" not in rendered
    assert "registry-1" not in rendered


def test_orphan_blocks_before_any_queue_mutation():
    worker = FakeRedis(pending=["orphan"])
    app = FakeRedis(active_tasks={})

    with pytest.raises(refund.RefundGateError, match="orphan"):
        run_refund(worker, app, execute=True)

    assert worker.pending == ["orphan"]
    assert worker.hash_writes == []


def test_zrem_race_skips_task_without_refund():
    worker = FakeRedis(pending=["backend-1"], race=["backend-1"])
    app = FakeRedis(active_tasks=active())

    summary, calls = run_refund(worker, app, execute=True)

    assert summary.moved_count == 1
    assert not [item for item in calls if isinstance(item, dict)]
    assert worker.hash_writes == []


def test_duplicate_refund_is_counted_as_idempotent_not_reapplied():
    worker = FakeRedis(pending=["backend-1"])
    app = FakeRedis(active_tasks=active())

    async def already_refunded(**_kwargs):
        return SimpleNamespace(refunded=False)

    summary, _calls = run_refund(
        worker, app, execute=True, finalize=already_refunded
    )

    assert summary.already_refunded_count == 1
    assert summary.refunded_count == 0


def test_ledger_mismatch_stops_execution():
    worker = FakeRedis(pending=["backend-1"])
    app = FakeRedis(active_tasks=active())

    async def ledger_mismatch(**_kwargs):
        raise ValueError("credit idempotency key was reused with a different amount")

    with pytest.raises(ValueError, match="different amount"):
        run_refund(worker, app, execute=True, finalize=ledger_mismatch)

    assert worker.pending == []
