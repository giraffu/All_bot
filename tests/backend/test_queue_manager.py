import asyncio
import json

import pytest
from app import queue_manager as queue_manager_module
from app.agent_router_helpers import check_task_payload, update_status_payload
from app.models import TaskStatus, TaskType
from app.queue_manager import QueueManager
from asgi_correlation_id import correlation_id


class _FakePipeline:
    def __init__(self, redis):
        self._redis = redis
        self._ops = []

    def hget(self, key, field):
        self._ops.append(("hget", (key, field), {}))
        return self

    def hset(self, key, field=None, value=None, mapping=None):
        self._ops.append(
            ("hset", (key,), {"field": field, "value": value, "mapping": mapping})
        )
        return self

    def expire(self, key, ttl):
        self._ops.append(("expire", (key, ttl), {}))
        return self

    def zadd(self, key, mapping):
        self._ops.append(("zadd", (key, mapping), {}))
        return self

    async def execute(self):
        results = []
        for method_name, args, kwargs in self._ops:
            method = getattr(self._redis, method_name)
            results.append(await method(*args, **kwargs))
        return results

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc_info):
        return False


class _FakeRedis:
    def __init__(self):
        self.hashes = {}
        self.sorted_sets = {}
        self.sets = {}
        self.values = {}
        self.published = []
        self.task_create_count = 0

    async def eval(
        self,
        script,
        _numkeys,
        *args,
    ):
        if "preferred_count" in script:
            pending_key, task_prefix, allowed_count, preferred_count, *task_types = args
            allowed_count = int(allowed_count)
            preferred_count = int(preferred_count)
            allowed = set(task_types[:allowed_count])
            preferred = set(
                task_types[allowed_count : allowed_count + preferred_count]
            )
            fallback = None
            for task_id, score in sorted(
                self.sorted_sets.get(pending_key, {}).items(),
                key=lambda item: item[1],
            ):
                task_type = self.hashes.get(f"{task_prefix}{task_id}", {}).get("type")
                if task_type not in allowed:
                    continue
                if fallback is None:
                    fallback = (task_id, score)
                if task_type in preferred:
                    self.sorted_sets[pending_key].pop(task_id)
                    return [task_id, score]
            if fallback is not None:
                self.sorted_sets[pending_key].pop(fallback[0])
                return list(fallback)
            return []

        (
            task_key,
            pending_key,
            request_fingerprint,
            task_data_json,
            _ttl,
            score,
            task_id,
        ) = args
        existing = self.hashes.get(task_key)
        if existing is not None:
            return (
                0
                if existing.get("request_fingerprint") == request_fingerprint
                else -1
            )
        self.hashes[task_key] = json.loads(task_data_json)
        self.sorted_sets.setdefault(pending_key, {})[task_id] = float(score)
        self.task_create_count += 1
        return 1

    async def hset(self, key, field=None, value=None, mapping=None):
        bucket = self.hashes.setdefault(key, {})
        if mapping is not None:
            bucket.update(mapping)
        elif field is not None:
            bucket[field] = value
        return 1

    async def hget(self, key, field):
        return self.hashes.get(key, {}).get(field)

    async def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    async def hdel(self, key, *fields):
        bucket = self.hashes.setdefault(key, {})
        removed = 0
        for field in fields:
            if field in bucket:
                removed += 1
                bucket.pop(field, None)
        return removed

    async def exists(self, key):
        return int(
            key in self.hashes
            or key in self.values
            or key in self.sets
            or key in self.sorted_sets
        )

    async def expire(self, _key, _ttl):
        return True

    async def setex(self, key, _ttl, value):
        self.values[key] = value
        return True

    async def zadd(self, key, mapping):
        bucket = self.sorted_sets.setdefault(key, {})
        bucket.update(mapping)
        return len(mapping)

    async def zpopmin(self, key):
        bucket = self.sorted_sets.setdefault(key, {})
        if not bucket:
            return []
        member, score = min(bucket.items(), key=lambda item: item[1])
        del bucket[member]
        return [(member, score)]

    async def zrange(self, key, start, end, withscores=False):
        items = sorted(self.sorted_sets.get(key, {}).items(), key=lambda item: item[1])
        if end == -1:
            sliced = items[start:]
        else:
            sliced = items[start : end + 1]
        if withscores:
            return sliced
        return [member for member, _score in sliced]

    async def zrem(self, key, member):
        bucket = self.sorted_sets.setdefault(key, {})
        existed = member in bucket
        bucket.pop(member, None)
        return 1 if existed else 0

    async def zrank(self, key, member):
        items = [task_id for task_id, _score in sorted(self.sorted_sets.get(key, {}).items(), key=lambda item: item[1])]
        try:
            return items.index(member)
        except ValueError:
            return None

    async def zcard(self, key):
        return len(self.sorted_sets.get(key, {}))

    async def sadd(self, key, member):
        bucket = self.sets.setdefault(key, set())
        bucket.add(member)
        return 1

    async def srem(self, key, member):
        bucket = self.sets.setdefault(key, set())
        existed = member in bucket
        bucket.discard(member)
        return 1 if existed else 0

    async def sismember(self, key, member):
        return member in self.sets.get(key, set())

    async def smembers(self, key):
        return set(self.sets.get(key, set()))

    async def publish(self, channel, message):
        self.published.append((channel, message))
        return 1

    async def scan(self, cursor, match=None, count=100):
        _ = count
        matched = [key for key in self.hashes if not match or key.startswith(match.rstrip("*"))]
        if cursor != 0:
            return 0, []
        return 0, matched

    def pipeline(self, transaction=True):
        _ = transaction
        return _FakePipeline(self)


class _FlakyRedis(_FakeRedis):
    def __init__(self, failures):
        super().__init__()
        self.failures = dict(failures)
        self.calls = {}

    def _record_call(self, name):
        self.calls[name] = self.calls.get(name, 0) + 1
        if self.failures.get(name, 0) > 0:
            self.failures[name] -= 1
            raise ConnectionResetError(f"{name} connection lost")

    async def hset(self, *args, **kwargs):
        self._record_call("hset")
        return await super().hset(*args, **kwargs)

    async def eval(self, *args, **kwargs):
        self._record_call("eval")
        return await super().eval(*args, **kwargs)

    async def hget(self, *args, **kwargs):
        self._record_call("hget")
        return await super().hget(*args, **kwargs)

    async def hgetall(self, *args, **kwargs):
        self._record_call("hgetall")
        return await super().hgetall(*args, **kwargs)

    async def hdel(self, *args, **kwargs):
        self._record_call("hdel")
        return await super().hdel(*args, **kwargs)

    async def exists(self, *args, **kwargs):
        self._record_call("exists")
        return await super().exists(*args, **kwargs)

    async def setex(self, *args, **kwargs):
        self._record_call("setex")
        return await super().setex(*args, **kwargs)

    async def publish(self, *args, **kwargs):
        self._record_call("publish")
        return await super().publish(*args, **kwargs)

    async def zpopmin(self, *args, **kwargs):
        self._record_call("zpopmin")
        return await super().zpopmin(*args, **kwargs)

    async def zrem(self, *args, **kwargs):
        self._record_call("zrem")
        return await super().zrem(*args, **kwargs)

    async def sismember(self, *args, **kwargs):
        self._record_call("sismember")
        return await super().sismember(*args, **kwargs)


@pytest.fixture(autouse=True)
def _disable_retry_sleep(monkeypatch):
    monkeypatch.setattr(
        queue_manager_module,
        "REDIS_TRANSIENT_RETRY_BASE_DELAY_SECONDS",
        0,
    )


@pytest.mark.asyncio
async def test_enqueue_task_persists_trace_id_and_priority_adjusted_score():
    redis = _FakeRedis()
    manager = QueueManager(redis)
    token = correlation_id.set("trace-123")

    try:
        task_id = await manager.enqueue_task(
            TaskType.IMG2IMG,
            {"prompt": "test"},
            2,
            "task-priority",
        )
    finally:
        correlation_id.reset(token)

    task_key = f"{manager.task_prefix}task-priority"
    stored = redis.hashes[task_key]

    assert task_id == "task-priority"
    assert stored["trace_id"] == "trace-123"
    assert json.loads(stored["params"]) == {"prompt": "test", "trace_id": "trace-123"}
    assert redis.sorted_sets[manager.pending_key]["task-priority"] == pytest.approx(
        float(stored["created_at"]) - 120.0
    )


@pytest.mark.asyncio
async def test_enqueue_task_retries_transient_pipeline_write_failure():
    redis = _FlakyRedis({"eval": 1})
    manager = QueueManager(redis)

    task_id = await manager.enqueue_task(
        TaskType.IMG2IMG,
        {"prompt": "test"},
        0,
        "task-retry",
    )

    assert task_id == "task-retry"
    assert redis.calls["eval"] == 2
    assert redis.task_create_count == 1
    assert redis.hashes[manager._task_key("task-retry")]["status"] == TaskStatus.PENDING
    assert "task-retry" in redis.sorted_sets[manager.pending_key]


@pytest.mark.asyncio
async def test_enqueue_task_retry_after_accepted_timeout_does_not_reset_or_duplicate():
    class AcceptedThenTimeoutRedis(_FakeRedis):
        def __init__(self):
            super().__init__()
            self.eval_calls = 0

        async def eval(self, *args, **kwargs):
            self.eval_calls += 1
            result = await super().eval(*args, **kwargs)
            if self.eval_calls == 1:
                task_key = args[2]
                self.hashes[task_key]["status"] = TaskStatus.RUNNING
                raise ConnectionResetError("reply lost after commit")
            return result

    redis = AcceptedThenTimeoutRedis()
    manager = QueueManager(redis)

    result = await manager.enqueue_task(
        TaskType.IMG2IMG,
        {"prompt": "same request"},
        0,
        "deterministic-task",
    )

    assert result == "deterministic-task"
    assert redis.eval_calls == 2
    assert redis.task_create_count == 1
    stored = redis.hashes[manager._task_key("deterministic-task")]
    assert stored["status"] == TaskStatus.RUNNING
    assert list(redis.sorted_sets[manager.pending_key]) == ["deterministic-task"]


@pytest.mark.asyncio
async def test_enqueue_task_same_id_conflicting_request_is_rejected_without_mutation():
    from app.queue_manager import TaskAdmissionConflictError

    redis = _FakeRedis()
    manager = QueueManager(redis)
    await manager.enqueue_task(
        TaskType.IMG2IMG,
        {"prompt": "original"},
        0,
        "deterministic-task",
    )
    original = dict(redis.hashes[manager._task_key("deterministic-task")])

    with pytest.raises(TaskAdmissionConflictError):
        await manager.enqueue_task(
            TaskType.IMG2IMG,
            {"prompt": "changed"},
            0,
            "deterministic-task",
        )

    assert redis.hashes[manager._task_key("deterministic-task")] == original
    assert redis.task_create_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_name", ["exists", "hgetall"])
async def test_check_task_payload_retries_transient_task_status_read(failure_name):
    redis = _FlakyRedis({failure_name: 1})
    manager = QueueManager(redis)
    redis.hashes[manager._task_key("task-check")] = {
        "status": TaskStatus.RUNNING,
        "cancel_requested": 0,
        "cancel_locked": 1,
        "execution_phase": "preparing",
    }

    payload = await check_task_payload(task_id="task-check", queue_manager=manager)

    assert payload == {
        "status": TaskStatus.RUNNING,
        "cancel_requested": False,
        "cancel_locked": True,
        "execution_phase": "preparing",
    }
    assert redis.calls[failure_name] == 2


@pytest.mark.asyncio
async def test_update_task_heartbeat_retries_transient_setex_failure():
    redis = _FlakyRedis({"setex": 1})
    manager = QueueManager(redis)

    await manager.update_task_heartbeat("task-heartbeat")

    assert redis.values[manager._task_heartbeat_key("task-heartbeat")] == "1"
    assert redis.calls["setex"] == 2


@pytest.mark.asyncio
async def test_update_status_payload_retries_transient_persist_read_and_publish():
    redis = _FlakyRedis({"hgetall": 1, "publish": 1})
    manager = QueueManager(redis)
    task_key = manager._task_key("task-running")
    redis.hashes[task_key] = {
        "task_id": "task-running",
        "type": TaskType.IMG2IMG,
        "status": TaskStatus.RUNNING,
    }

    payload = await update_status_payload(
        task_id="task-running",
        agent_id="agent-1",
        status="running",
        progress=0.75,
        error="",
        queue_manager=manager,
        set_current=False,
    )

    assert payload == {"status": "ok"}
    assert redis.hashes[task_key]["worker_id"] == "agent-1"
    assert redis.hashes[task_key]["progress"] == 0.75
    assert json.loads(redis.published[-1][1]) == {
        "status": "running",
        "progress": 0.75,
    }
    assert redis.calls["hgetall"] == 2
    assert redis.calls["publish"] == 2


@pytest.mark.asyncio
async def test_persist_task_update_retries_transient_hset_failure():
    redis = _FlakyRedis({"hset": 1})
    manager = QueueManager(redis)
    task_key = manager._task_key("task-progress")
    redis.hashes[task_key] = {
        "task_id": "task-progress",
        "type": TaskType.IMG2IMG,
        "status": TaskStatus.RUNNING,
    }

    await manager.update_progress("task-progress", 0.5)

    assert redis.hashes[task_key]["progress"] == 0.5
    assert json.loads(redis.published[-1][1]) == {
        "status": "running",
        "progress": 0.5,
    }
    assert redis.calls["hset"] == 2


@pytest.mark.asyncio
async def test_dequeue_task_does_not_retry_zpopmin_transient_failure():
    redis = _FlakyRedis({"zpopmin": 1})
    manager = QueueManager(redis)
    redis.sorted_sets[manager.pending_key] = {"task-a": 1.0}

    with pytest.raises(ConnectionResetError):
        await manager.dequeue_task()

    assert redis.calls["zpopmin"] == 1
    assert redis.sorted_sets[manager.pending_key] == {"task-a": 1.0}


@pytest.mark.asyncio
async def test_dequeue_task_respects_allowed_types_and_marks_task_running():
    redis = _FakeRedis()
    manager = QueueManager(redis)
    task_a = f"{manager.task_prefix}task-a"
    task_b = f"{manager.task_prefix}task-b"

    await redis.hset(task_a, mapping={"type": TaskType.IMG2IMG, "status": TaskStatus.PENDING})
    await redis.hset(task_b, mapping={"type": TaskType.LTX_VIDEO, "status": TaskStatus.PENDING})
    await redis.zadd(manager.pending_key, {"task-a": 1.0, "task-b": 2.0})

    result = await manager.dequeue_task(allowed_types=[TaskType.LTX_VIDEO])

    assert result == ("task-b", 2.0)
    assert await redis.sismember(manager.running_key, "task-b")
    assert redis.hashes[task_b]["status"] == TaskStatus.RUNNING
    assert "comfy:task_heartbeat:task-b" in redis.values
    assert "task-b" not in redis.sorted_sets[manager.pending_key]


@pytest.mark.asyncio
async def test_dequeue_task_uses_priority_score_across_allowed_types():
    redis = _FakeRedis()
    manager = QueueManager(redis)
    lower_priority_task = f"{manager.task_prefix}lower-priority"
    higher_priority_task = f"{manager.task_prefix}higher-priority"

    await redis.hset(
        lower_priority_task,
        mapping={"type": TaskType.IMG2IMG, "status": TaskStatus.PENDING},
    )
    await redis.hset(
        higher_priority_task,
        mapping={"type": TaskType.LTX_VIDEO, "status": TaskStatus.PENDING},
    )
    await redis.zadd(
        manager.pending_key,
        {"lower-priority": 20.0, "higher-priority": 10.0},
    )

    result = await manager.dequeue_task(
        allowed_types=[TaskType.IMG2IMG, TaskType.LTX_VIDEO]
    )

    assert result == ("higher-priority", 10.0)
    assert "lower-priority" in redis.sorted_sets[manager.pending_key]


@pytest.mark.asyncio
async def test_dequeue_task_prefers_preferred_type_over_lower_score_fallback():
    redis = _FakeRedis()
    manager = QueueManager(redis)
    await redis.hset(
        f"{manager.task_prefix}fallback",
        mapping={"type": TaskType.IMG2IMG, "status": TaskStatus.PENDING},
    )
    await redis.hset(
        f"{manager.task_prefix}preferred",
        mapping={"type": TaskType.SCAIL2_FACE_SWAP_V2, "status": TaskStatus.PENDING},
    )
    await redis.zadd(
        manager.pending_key,
        {"fallback": 1.0, "preferred": 20.0},
    )

    result = await manager.dequeue_task(
        allowed_types=[TaskType.IMG2IMG, TaskType.SCAIL2_FACE_SWAP_V2],
        preferred_types=[TaskType.SCAIL2_FACE_SWAP_V2],
    )

    assert result == ("preferred", 20.0)
    assert "fallback" in redis.sorted_sets[manager.pending_key]


@pytest.mark.asyncio
async def test_dequeue_task_uses_first_fallback_when_no_preferred_is_pending():
    redis = _FakeRedis()
    manager = QueueManager(redis)
    await redis.hset(
        f"{manager.task_prefix}fallback-a",
        mapping={"type": TaskType.IMG2IMG, "status": TaskStatus.PENDING},
    )
    await redis.hset(
        f"{manager.task_prefix}fallback-b",
        mapping={"type": TaskType.LTX_VIDEO, "status": TaskStatus.PENDING},
    )
    await redis.zadd(
        manager.pending_key,
        {"fallback-a": 2.0, "fallback-b": 3.0},
    )

    result = await manager.dequeue_task(
        allowed_types=[TaskType.IMG2IMG, TaskType.LTX_VIDEO],
        preferred_types=[TaskType.SCAIL2_FACE_SWAP_V2],
    )

    assert result == ("fallback-a", 2.0)
    assert "fallback-b" in redis.sorted_sets[manager.pending_key]


@pytest.mark.asyncio
async def test_preferred_dequeue_does_not_retry_atomic_claim_failure():
    redis = _FlakyRedis({"eval": 1})
    manager = QueueManager(redis)

    with pytest.raises(ConnectionResetError):
        await manager.dequeue_task(
            allowed_types=[TaskType.IMG2IMG],
            preferred_types=[TaskType.IMG2IMG],
        )

    assert redis.calls["eval"] == 1


@pytest.mark.asyncio
async def test_concurrent_preferred_dequeue_never_claims_same_task_twice():
    redis = _FakeRedis()
    first_manager = QueueManager(redis)
    second_manager = QueueManager(redis)
    for task_id in ("preferred-a", "preferred-b"):
        await redis.hset(
            f"{first_manager.task_prefix}{task_id}",
            mapping={
                "type": TaskType.SCAIL2_FACE_SWAP_V2,
                "status": TaskStatus.PENDING,
            },
        )
    await redis.zadd(
        first_manager.pending_key,
        {"preferred-a": 1.0, "preferred-b": 2.0},
    )

    results = await asyncio.gather(
        first_manager.dequeue_task(
            allowed_types=[TaskType.IMG2IMG, TaskType.SCAIL2_FACE_SWAP_V2],
            preferred_types=[TaskType.SCAIL2_FACE_SWAP_V2],
        ),
        second_manager.dequeue_task(
            allowed_types=[TaskType.IMG2IMG, TaskType.SCAIL2_FACE_SWAP_V2],
            preferred_types=[TaskType.SCAIL2_FACE_SWAP_V2],
        ),
    )

    assert {result[0] for result in results if result} == {
        "preferred-a",
        "preferred-b",
    }


@pytest.mark.asyncio
async def test_dequeue_task_with_cancel_lock_marks_task_uncancellable_phase():
    redis = _FakeRedis()
    manager = QueueManager(redis)
    task_key = f"{manager.task_prefix}task-lock"

    await redis.hset(task_key, mapping={"type": TaskType.IMG2IMG, "status": TaskStatus.PENDING})
    await redis.zadd(manager.pending_key, {"task-lock": 1.0})

    result = await manager.dequeue_task(cancel_lock=True)

    assert result == ("task-lock", 1.0)
    stored = redis.hashes[task_key]
    assert stored["status"] == TaskStatus.RUNNING
    assert stored["cancel_locked"] == 1
    assert stored["execution_phase"] == "preparing"
    assert stored["cancel_requested"] == 0
    assert stored["cancel_requested_at"] == ""
    assert stored["cancel_locked_at"]


@pytest.mark.asyncio
async def test_peek_pending_tasks_respects_allowed_types_without_mutating_queue_state():
    redis = _FakeRedis()
    manager = QueueManager(redis)
    task_a = f"{manager.task_prefix}task-a"
    task_b = f"{manager.task_prefix}task-b"

    await redis.hset(task_a, mapping={"task_id": "task-a", "type": TaskType.IMG2IMG, "status": TaskStatus.PENDING})
    await redis.hset(task_b, mapping={"task_id": "task-b", "type": TaskType.LTX_VIDEO, "status": TaskStatus.PENDING})
    await redis.zadd(manager.pending_key, {"task-a": 1.0, "task-b": 2.0})

    result = await manager.peek_pending_tasks(
        allowed_types=[TaskType.LTX_VIDEO],
        limit=1,
    )

    assert result == [{"task_id": "task-b", "type": TaskType.LTX_VIDEO, "status": TaskStatus.PENDING}]
    assert redis.sorted_sets[manager.pending_key] == {"task-a": 1.0, "task-b": 2.0}
    assert redis.sets.get(manager.running_key, set()) == set()
    assert manager._task_heartbeat_key("task-b") not in redis.values


@pytest.mark.asyncio
async def test_peek_pending_tasks_prefers_preferred_without_mutating_queue_state():
    redis = _FakeRedis()
    manager = QueueManager(redis)
    await redis.hset(
        f"{manager.task_prefix}fallback",
        mapping={
            "task_id": "fallback",
            "type": TaskType.IMG2IMG,
            "status": TaskStatus.PENDING,
        },
    )
    await redis.hset(
        f"{manager.task_prefix}preferred",
        mapping={
            "task_id": "preferred",
            "type": TaskType.SCAIL2_FACE_SWAP_V2,
            "status": TaskStatus.PENDING,
        },
    )
    await redis.zadd(
        manager.pending_key,
        {"fallback": 1.0, "preferred": 20.0},
    )

    result = await manager.peek_pending_tasks(
        allowed_types=[TaskType.IMG2IMG, TaskType.SCAIL2_FACE_SWAP_V2],
        preferred_types=[TaskType.SCAIL2_FACE_SWAP_V2],
        limit=1,
    )

    assert result[0]["task_id"] == "preferred"
    assert redis.sorted_sets[manager.pending_key] == {
        "fallback": 1.0,
        "preferred": 20.0,
    }


@pytest.mark.asyncio
async def test_peek_pending_tasks_skips_non_pending_tasks_left_in_pending_zset():
    redis = _FakeRedis()
    manager = QueueManager(redis)

    await redis.hset(
        f"{manager.task_prefix}task-cancelled",
        mapping={"task_id": "task-cancelled", "type": TaskType.IMG2IMG, "status": TaskStatus.CANCELLED},
    )
    await redis.hset(
        f"{manager.task_prefix}task-pending",
        mapping={"task_id": "task-pending", "type": TaskType.IMG2IMG, "status": TaskStatus.PENDING},
    )
    await redis.zadd(
        manager.pending_key,
        {"task-cancelled": 1.0, "task-pending": 2.0, "task-missing": 3.0},
    )

    result = await manager.peek_pending_tasks(
        allowed_types=[TaskType.IMG2IMG],
        limit=1,
    )

    assert result == [{"task_id": "task-pending", "type": TaskType.IMG2IMG, "status": TaskStatus.PENDING}]
    assert "task-cancelled" in redis.sorted_sets[manager.pending_key]
    assert "task-pending" in redis.sorted_sets[manager.pending_key]


@pytest.mark.asyncio
async def test_dequeue_task_without_type_filter_pops_first_pending_task():
    redis = _FakeRedis()
    manager = QueueManager(redis)
    task_a = f"{manager.task_prefix}task-a"
    task_b = f"{manager.task_prefix}task-b"

    await redis.hset(task_a, mapping={"type": TaskType.IMG2IMG, "status": TaskStatus.PENDING})
    await redis.hset(task_b, mapping={"type": TaskType.LTX_VIDEO, "status": TaskStatus.PENDING})
    await redis.zadd(manager.pending_key, {"task-a": 1.0, "task-b": 2.0})

    result = await manager.dequeue_task()

    assert result == ("task-a", 1.0)
    assert await redis.sismember(manager.running_key, "task-a")
    assert redis.hashes[task_a]["status"] == TaskStatus.RUNNING
    assert "task-a" not in redis.sorted_sets[manager.pending_key]


@pytest.mark.asyncio
async def test_agent_control_state_blocks_pop_when_draining():
    redis = _FakeRedis()
    manager = QueueManager(redis)

    control = await manager.set_agent_control_state(
        "agent-1",
        "draining",
        reason="model sync",
        ttl_seconds=120,
    )
    enabled, reason = await manager.is_agent_pop_enabled("agent-1")

    assert control["state"] == "draining"
    assert enabled is False
    assert reason == "model sync"

    await manager.set_agent_control_state("agent-1", "enabled")
    enabled, reason = await manager.is_agent_pop_enabled("agent-1")

    assert enabled is True
    assert reason == ""


@pytest.mark.asyncio
async def test_worker_info_includes_gpu_pool_metadata():
    redis = _FakeRedis()
    manager = QueueManager(redis)

    await manager.update_agent_heartbeat(
        "agent-1",
        "wan22_video_v2",
        "idle",
        metadata={
            "node_id": "gpu-252",
            "provider": "lan_ssh",
            "gpu_index": "1",
            "runtime_profile": "wan22_video_v2",
            "image_ref": "192.168.1.115:5000/allbot/comfy-cu128-wan22:baseline",
            "model_bundle_versions": '{"wan22_video_v2_baseline":"2026-06-10"}',
            "pool_managed": "true",
        },
    )

    workers = await manager.get_all_workers()

    assert workers == [
        {
            "agent_id": "agent-1",
            "types": "wan22_video_v2",
            "status": "idle",
            "last_seen": workers[0]["last_seen"],
            "health_reason": "",
            "last_error": "",
            "last_error_at": None,
            "consecutive_failures": 0,
            "quarantined_until": None,
            "node_id": "gpu-252",
            "provider": "lan_ssh",
            "gpu_index": 1,
            "runtime_profile": "wan22_video_v2",
            "image_ref": "192.168.1.115:5000/allbot/comfy-cu128-wan22:baseline",
            "model_bundle_versions": {"wan22_video_v2_baseline": "2026-06-10"},
            "pool_managed": True,
        }
    ]


@pytest.mark.asyncio
async def test_activate_dequeued_task_returns_none_when_no_task():
    redis = _FakeRedis()
    manager = QueueManager(redis)

    assert await manager._activate_dequeued_task(None) is None


@pytest.mark.asyncio
async def test_activate_dequeued_task_marks_task_running_and_returns_tuple():
    redis = _FakeRedis()
    manager = QueueManager(redis)
    task_key = f"{manager.task_prefix}task-activate"

    await redis.hset(task_key, mapping={"type": TaskType.IMG2IMG, "status": TaskStatus.PENDING})

    result = await manager._activate_dequeued_task(("task-activate", 3.5))

    assert result == ("task-activate", 3.5)
    assert await redis.sismember(manager.running_key, "task-activate")
    assert redis.hashes[task_key]["status"] == TaskStatus.RUNNING
    assert manager._task_heartbeat_key("task-activate") in redis.values


@pytest.mark.asyncio
async def test_cancel_task_cancels_pending_task_and_publishes_event():
    redis = _FakeRedis()
    manager = QueueManager(redis)
    task_key = f"{manager.task_prefix}task-1"

    await redis.hset(task_key, mapping={"status": TaskStatus.PENDING, "type": TaskType.IMG2IMG})
    await redis.zadd(manager.pending_key, {"task-1": 1.0})

    result = await manager.cancel_task("task-1")

    assert result == {
        "state": "cancelled",
        "task_id": "task-1",
        "message": "任务已从排队队列移除",
    }
    assert redis.hashes[task_key]["status"] == TaskStatus.CANCELLED
    assert redis.hashes[task_key]["cancel_requested"] == 0
    assert redis.hashes[task_key]["cancel_requested_at"] == ""
    assert ("comfy:task_events:task-1", json.dumps({"status": "cancelled"})) in redis.published


@pytest.mark.asyncio
async def test_cancel_task_retries_transient_pending_zrem_failure():
    redis = _FlakyRedis({"zrem": 1})
    manager = QueueManager(redis)
    task_key = f"{manager.task_prefix}task-retry-cancel"

    await redis.hset(
        task_key,
        mapping={"status": TaskStatus.PENDING, "type": TaskType.IMG2IMG},
    )
    await redis.zadd(manager.pending_key, {"task-retry-cancel": 1.0})

    result = await manager.cancel_task("task-retry-cancel")

    assert result["state"] == "cancelled"
    assert redis.calls["zrem"] == 2
    assert redis.hashes[task_key]["status"] == TaskStatus.CANCELLED


@pytest.mark.asyncio
async def test_cancel_task_requests_running_task_cancellation():
    redis = _FakeRedis()
    manager = QueueManager(redis)
    task_key = f"{manager.task_prefix}task-2"

    await redis.hset(task_key, mapping={"status": TaskStatus.RUNNING, "type": TaskType.LTX_VIDEO})
    await redis.sadd(manager.running_key, "task-2")

    result = await manager.cancel_task("task-2")

    assert result == {
        "state": "cancellation_requested",
        "task_id": "task-2",
        "message": "任务已请求取消，等待执行端确认",
        "cancel_requested": True,
        "cancel_requested_at": result["cancel_requested_at"],
    }
    assert redis.hashes[task_key]["status"] == TaskStatus.RUNNING
    assert redis.hashes[task_key]["cancel_requested"] == 1
    assert redis.hashes[task_key]["cancel_requested_at"]
    payload = json.loads(redis.published[-1][1])
    assert payload == {
        "status": "running",
        "cancel_requested": True,
        "message": "已请求取消，等待执行端确认",
    }


@pytest.mark.asyncio
async def test_cancel_task_rejects_cancel_locked_running_task():
    redis = _FakeRedis()
    manager = QueueManager(redis)
    task_key = f"{manager.task_prefix}task-locked"

    await redis.hset(
        task_key,
        mapping={
            "status": TaskStatus.RUNNING,
            "type": TaskType.IMG2IMG,
            "cancel_locked": 1,
        },
    )
    await redis.sadd(manager.running_key, "task-locked")

    result = await manager.cancel_task("task-locked")

    assert result == {
        "state": "not_cancellable",
        "task_id": "task-locked",
        "message": "任务已进入输入准备或执行阶段，无法再取消",
        "reason": "cancel_locked",
        "cancel_locked": True,
    }
    assert redis.hashes[task_key].get("cancel_requested") is None


@pytest.mark.asyncio
async def test_cancel_running_task_marks_cancelled_removes_running_and_publishes_event():
    redis = _FakeRedis()
    manager = QueueManager(redis)
    task_key = f"{manager.task_prefix}task-running-cancelled"

    await redis.hset(
        task_key,
        mapping={
            "status": TaskStatus.RUNNING,
            "type": TaskType.IMG2IMG,
            "cancel_requested": 1,
            "cancel_requested_at": "123.0",
        },
    )
    await redis.sadd(manager.running_key, "task-running-cancelled")

    result = await manager.cancel_running_task("task-running-cancelled")

    assert result == {
        "state": "cancelled",
        "task_id": "task-running-cancelled",
        "message": "任务已取消",
    }
    assert redis.hashes[task_key]["status"] == TaskStatus.CANCELLED
    assert redis.hashes[task_key]["cancel_requested"] == 0
    assert redis.hashes[task_key]["cancel_requested_at"] == ""
    assert "task-running-cancelled" not in redis.sets[manager.running_key]
    assert (
        "comfy:task_events:task-running-cancelled",
        json.dumps({"status": "cancelled"}),
    ) in redis.published


@pytest.mark.asyncio
async def test_cancel_task_returns_terminal_state_for_done_task():
    redis = _FakeRedis()
    manager = QueueManager(redis)
    task_key = f"{manager.task_prefix}task-3"

    await redis.hset(task_key, mapping={"status": TaskStatus.DONE, "type": TaskType.FACE_VIDEO})

    result = await manager.cancel_task("task-3")

    assert result == {
        "state": "not_cancellable",
        "task_id": "task-3",
        "message": "任务已结束，无法再取消",
    }


@pytest.mark.asyncio
async def test_check_zombie_tasks_fails_running_task_without_heartbeat():
    redis = _FakeRedis()
    manager = QueueManager(redis)
    task_key = f"{manager.task_prefix}task-zombie"

    await redis.hset(task_key, mapping={"status": TaskStatus.RUNNING, "type": TaskType.VIDEO_EDIT})
    await redis.sadd(manager.running_key, "task-zombie")

    await manager.check_zombie_tasks()

    assert redis.hashes[task_key]["status"] == TaskStatus.ERROR
    assert redis.hashes[task_key]["error_msg"] == "Task execution timed out (Worker heartbeat lost)"
    payload = json.loads(redis.published[-1][1])
    assert payload["status"] == "error"
    assert payload["error_msg"] == "Task execution timed out (Worker heartbeat lost)"
    assert payload["task_type"] == TaskType.VIDEO_EDIT


@pytest.mark.asyncio
async def test_check_zombie_tasks_keeps_running_task_with_heartbeat():
    redis = _FakeRedis()
    manager = QueueManager(redis)
    task_key = f"{manager.task_prefix}task-alive"

    await redis.hset(task_key, mapping={"status": TaskStatus.RUNNING, "type": TaskType.VIDEO_EDIT})
    await redis.sadd(manager.running_key, "task-alive")
    await redis.setex(manager._task_heartbeat_key("task-alive"), 300, "1")

    await manager.check_zombie_tasks()

    assert redis.hashes[task_key]["status"] == TaskStatus.RUNNING
    assert redis.published == []


@pytest.mark.asyncio
async def test_get_queue_metrics_by_type_counts_known_and_unknown_types():
    redis = _FakeRedis()
    manager = QueueManager(redis)
    task_a = f"{manager.task_prefix}task-a"
    task_b = f"{manager.task_prefix}task-b"
    task_c = f"{manager.task_prefix}task-c"

    await redis.hset(task_a, mapping={"type": TaskType.IMG2IMG})
    await redis.hset(task_b, mapping={"type": TaskType.LTX_VIDEO})
    await redis.hset(task_c, mapping={"type": "custom_unknown"})
    await redis.zadd(manager.pending_key, {"task-a": 1.0, "task-b": 2.0, "task-c": 3.0})

    counts = await manager.get_queue_metrics_by_type()

    assert counts[TaskType.IMG2IMG.value] == 1
    assert counts[TaskType.LTX_VIDEO.value] == 1
    assert counts["custom_unknown"] == 1


@pytest.mark.asyncio
async def test_get_all_workers_enriches_running_task_details():
    redis = _FakeRedis()
    manager = QueueManager(redis)
    worker_key = f"{manager.agent_heartbeat_prefix}agent-1"
    task_key = f"{manager.task_prefix}task-1"

    await redis.hset(
        worker_key,
        mapping={
            "types": "ltx_video",
            "status": "running",
            "last_seen": "123.0",
            "current_task_id": "task-1",
        },
    )
    await redis.hset(
        task_key,
        mapping={
            "type": TaskType.LTX_VIDEO,
            "progress": "0.5",
            "created_at": "99.0",
        },
    )

    workers = await manager.get_all_workers()

    assert workers == [
        {
            "types": "ltx_video",
            "status": "running",
            "last_seen": "123.0",
            "current_task_id": "task-1",
            "agent_id": "agent-1",
            "current_task_type": TaskType.LTX_VIDEO,
            "current_task_progress": 0.5,
            "current_task_created_at": 99.0,
        }
    ]


@pytest.mark.asyncio
async def test_get_all_workers_ignores_partial_agent_task_binding_without_heartbeat():
    redis = _FakeRedis()
    manager = QueueManager(redis)
    worker_key = f"{manager.agent_heartbeat_prefix}agent-partial"

    await redis.hset(worker_key, mapping={"current_task_id": "task-1"})

    assert await manager.get_all_workers() == []


@pytest.mark.asyncio
async def test_clear_agent_current_task_compare_and_clear_preserves_newer_task():
    redis = _FakeRedis()
    manager = QueueManager(redis)
    worker_key = f"{manager.agent_heartbeat_prefix}agent-1"

    await redis.hset(worker_key, mapping={"current_task_id": "task-new"})

    await manager.clear_agent_current_task("agent-1", task_id="task-old")

    assert redis.hashes[worker_key]["current_task_id"] == "task-new"

    await manager.clear_agent_current_task("agent-1", task_id="task-new")

    assert "current_task_id" not in redis.hashes[worker_key]


@pytest.mark.asyncio
async def test_agent_task_delivery_claim_replays_until_worker_status_binds_task():
    redis = _FakeRedis()
    manager = QueueManager(redis)

    await manager.reserve_agent_task_delivery("task-1", "agent-1")

    assert await manager.get_pending_agent_task_claim("agent-1") == "task-1"

    await manager.bind_agent_task("task-1", "agent-1")

    assert await manager.get_pending_agent_task_claim("agent-1") is None


@pytest.mark.asyncio
async def test_get_active_workers_count_counts_agent_heartbeat_keys_only():
    redis = _FakeRedis()
    manager = QueueManager(redis)

    await redis.hset(f"{manager.agent_heartbeat_prefix}agent-1", mapping={"status": "idle"})
    await redis.hset(f"{manager.agent_heartbeat_prefix}agent-2", mapping={"status": "running"})
    await redis.hset(f"{manager.task_prefix}task-1", mapping={"status": TaskStatus.RUNNING})

    count = await manager.get_active_workers_count()

    assert count == 2


@pytest.mark.asyncio
async def test_update_agent_heartbeat_uses_agent_key_helper():
    redis = _FakeRedis()
    manager = QueueManager(redis)

    await manager.update_agent_heartbeat("agent-9", "img2img", "idle")

    key = manager._agent_heartbeat_key("agent-9")
    assert redis.hashes[key]["types"] == "img2img"
    assert redis.hashes[key]["status"] == "idle"


@pytest.mark.asyncio
async def test_update_agent_heartbeat_persists_and_clears_health_fields():
    redis = _FakeRedis()
    manager = QueueManager(redis)

    await manager.update_agent_heartbeat(
        "agent-health",
        "ltx_video",
        "error",
        health_reason="comfy_probe_failed",
        last_error="ComfyUI /system_stats probe failed",
        last_error_at=123.0,
        consecutive_failures=3,
        quarantined_until=456.0,
    )

    key = manager._agent_heartbeat_key("agent-health")
    assert redis.hashes[key]["status"] == "error"
    assert redis.hashes[key]["health_reason"] == "comfy_probe_failed"
    assert redis.hashes[key]["last_error"] == "ComfyUI /system_stats probe failed"
    assert redis.hashes[key]["last_error_at"] == 123.0
    assert redis.hashes[key]["consecutive_failures"] == 3
    assert redis.hashes[key]["quarantined_until"] == 456.0

    workers = await manager.get_all_workers()
    assert workers[0]["last_error_at"] == 123.0
    assert workers[0]["consecutive_failures"] == 3
    assert workers[0]["quarantined_until"] == 456.0

    await manager.update_agent_heartbeat("agent-health", "ltx_video", "idle")

    assert redis.hashes[key]["status"] == "idle"
    assert redis.hashes[key]["health_reason"] == ""
    assert redis.hashes[key]["last_error"] == ""
    assert redis.hashes[key]["last_error_at"] == ""
    assert redis.hashes[key]["consecutive_failures"] == 0
    assert redis.hashes[key]["quarantined_until"] == ""


@pytest.mark.asyncio
async def test_complete_task_marks_done_removes_running_and_publishes_task_type():
    redis = _FakeRedis()
    manager = QueueManager(redis)
    task_key = f"{manager.task_prefix}task-done"

    await redis.hset(
        task_key,
        mapping={
            "type": TaskType.LTX_VIDEO,
            "status": TaskStatus.RUNNING,
            "worker_id": "worker-1",
            "created_at": 123.0,
        },
    )
    await redis.sadd(manager.running_key, "task-done")

    await manager.complete_task("task-done", "outputs/result.mp4")

    assert redis.hashes[task_key]["status"] == TaskStatus.DONE
    assert redis.hashes[task_key]["result_path"] == "outputs/result.mp4"
    assert redis.hashes[task_key]["progress"] == 1.0
    assert redis.hashes[task_key]["cancel_requested"] == 0
    assert redis.hashes[task_key]["cancel_locked"] == 0
    assert redis.hashes[task_key]["execution_phase"] == ""
    assert "task-done" not in redis.sets[manager.running_key]
    assert (
        "comfy:task_events:task-done",
        json.dumps(
            {
                "status": "done",
                    "result_path": "outputs/result.mp4",
                    "extra_outputs": None,
                    "result_kind": "media",
                    "result_text": None,
                    "result_meta": None,
                    "progress": 1.0,
                "task_type": TaskType.LTX_VIDEO,
                "worker_id": "worker-1",
                "created_at": 123.0,
            }
        ),
    ) in redis.published


@pytest.mark.asyncio
async def test_complete_task_falls_back_to_edit_when_type_missing():
    redis = _FakeRedis()
    manager = QueueManager(redis)
    task_key = f"{manager.task_prefix}task-done-fallback"

    await redis.hset(task_key, mapping={"status": TaskStatus.RUNNING})
    await redis.sadd(manager.running_key, "task-done-fallback")

    await manager.complete_task("task-done-fallback", "outputs/result.png")

    payload = json.loads(redis.published[-1][1])
    assert payload["status"] == "done"
    assert payload["task_type"] == "edit"


@pytest.mark.asyncio
async def test_fail_task_marks_error_removes_running_and_publishes_error():
    redis = _FakeRedis()
    manager = QueueManager(redis)
    task_key = f"{manager.task_prefix}task-error"

    await redis.hset(
        task_key,
        mapping={
            "status": TaskStatus.RUNNING,
            "cancel_requested": 1,
            "type": TaskType.IMG2IMG,
            "worker_id": "worker-2",
            "created_at": 456.0,
        },
    )
    await redis.sadd(manager.running_key, "task-error")

    await manager.fail_task("task-error", "boom")

    assert redis.hashes[task_key]["status"] == TaskStatus.ERROR
    assert redis.hashes[task_key]["error_msg"] == "boom"
    assert redis.hashes[task_key]["cancel_requested"] == 0
    assert redis.hashes[task_key]["cancel_locked"] == 0
    assert redis.hashes[task_key]["execution_phase"] == ""
    assert "task-error" not in redis.sets[manager.running_key]
    assert (
        "comfy:task_events:task-error",
        json.dumps(
            {
                "status": "error",
                "error_msg": "boom",
                "task_type": TaskType.IMG2IMG,
                "worker_id": "worker-2",
                "created_at": 456.0,
            }
        ),
    ) in redis.published


@pytest.mark.asyncio
async def test_update_progress_persists_progress_and_publishes_running_event():
    redis = _FakeRedis()
    manager = QueueManager(redis)
    task_key = f"{manager.task_prefix}task-progress"

    await redis.hset(task_key, mapping={"status": TaskStatus.RUNNING, "progress": 0.1})

    await manager.update_progress("task-progress", 0.75)

    assert redis.hashes[task_key]["progress"] == 0.75
    assert (
        "comfy:task_events:task-progress",
        json.dumps({"status": "running", "progress": 0.75}),
    ) in redis.published


@pytest.mark.asyncio
async def test_get_queue_position_returns_sorted_rank():
    redis = _FakeRedis()
    manager = QueueManager(redis)

    await redis.zadd(manager.pending_key, {"task-a": 5.0, "task-b": 1.0, "task-c": 3.0})

    assert await manager.get_queue_position("task-b") == 0
    assert await manager.get_queue_position("task-c") == 1
    assert await manager.get_queue_position("task-a") == 2
    assert await manager.get_queue_position("missing-task") is None


@pytest.mark.asyncio
async def test_get_queue_position_by_type_returns_sorted_rank_within_task_type():
    redis = _FakeRedis()
    manager = QueueManager(redis)

    await redis.zadd(
        manager.pending_key,
        {"task-a": 1.0, "task-b": 2.0, "task-c": 3.0, "task-d": 4.0},
    )
    await redis.hset(f"{manager.task_prefix}task-a", mapping={"type": TaskType.IMG2IMG})
    await redis.hset(f"{manager.task_prefix}task-b", mapping={"type": TaskType.FACE_SWAP})
    await redis.hset(f"{manager.task_prefix}task-c", mapping={"type": TaskType.IMG2IMG})
    await redis.hset(f"{manager.task_prefix}task-d", mapping={"type": TaskType.IMG2IMG})

    assert await manager.get_queue_position_by_type("task-a") == 0
    assert await manager.get_queue_position_by_type("task-c") == 1
    assert await manager.get_queue_position_by_type("task-d") == 2
    assert await manager.get_queue_position_by_type("task-b") == 0
    assert await manager.get_queue_position_by_type("missing-task") is None


@pytest.mark.asyncio
async def test_get_queue_size_returns_pending_count():
    redis = _FakeRedis()
    manager = QueueManager(redis)

    await redis.zadd(manager.pending_key, {"task-a": 1.0, "task-b": 2.0})

    assert await manager.get_queue_size() == 2


@pytest.mark.asyncio
async def test_get_queue_metrics_by_type_details_tracks_max_pending_wait(monkeypatch):
    monkeypatch.setattr(queue_manager_module.time, "time", lambda: 2000.0)
    redis = _FakeRedis()
    manager = QueueManager(redis)

    await redis.hset(
        manager._task_key("free-old"),
        mapping={
            "type": TaskType.IMG2IMG,
            "created_at": "1800",
            "priority": "0",
        },
    )
    await redis.hset(
        manager._task_key("free-new"),
        mapping={
            "type": TaskType.IMG2IMG,
            "created_at": "1900",
            "priority": "0",
        },
    )
    await redis.hset(
        manager._task_key("paid"),
        mapping={
            "type": TaskType.IMG2IMG,
            "created_at": "1950",
            "priority": "40",
        },
    )
    await redis.zadd(
        manager.pending_key,
        {"free-old": 1.0, "free-new": 2.0, "paid": 3.0},
    )

    details = await manager.get_queue_metrics_by_type_details()

    assert details["img2img"] == {
        "pending_count": 3,
        "max_pending_wait_seconds": 200,
    }


@pytest.mark.asyncio
async def test_update_task_heartbeat_uses_task_heartbeat_key():
    redis = _FakeRedis()
    manager = QueueManager(redis)

    await manager.update_task_heartbeat("task-heartbeat")

    heartbeat_key = manager._task_heartbeat_key("task-heartbeat")
    assert redis.values[heartbeat_key] == "1"
