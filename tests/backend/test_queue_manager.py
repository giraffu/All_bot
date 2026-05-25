import json

import pytest
from asgi_correlation_id import correlation_id

from app.models import TaskStatus, TaskType
from app.queue_manager import QueueManager


class _FakePipeline:
    def __init__(self, redis):
        self._redis = redis
        self._ops = []

    def hget(self, key, field):
        self._ops.append((key, field))
        return self

    async def execute(self):
        return [await self._redis.hget(key, field) for key, field in self._ops]


class _FakeRedis:
    def __init__(self):
        self.hashes = {}
        self.sorted_sets = {}
        self.sets = {}
        self.values = {}
        self.published = []

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

    def pipeline(self):
        return _FakePipeline(self)


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
    assert payload == {
        "status": "error",
        "error_msg": "Task execution timed out (Worker heartbeat lost)",
    }


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
async def test_complete_task_marks_done_removes_running_and_publishes_task_type():
    redis = _FakeRedis()
    manager = QueueManager(redis)
    task_key = f"{manager.task_prefix}task-done"

    await redis.hset(task_key, mapping={"type": TaskType.LTX_VIDEO, "status": TaskStatus.RUNNING})
    await redis.sadd(manager.running_key, "task-done")

    await manager.complete_task("task-done", "outputs/result.mp4")

    assert redis.hashes[task_key]["status"] == TaskStatus.DONE
    assert redis.hashes[task_key]["result_path"] == "outputs/result.mp4"
    assert redis.hashes[task_key]["progress"] == 1.0
    assert redis.hashes[task_key]["cancel_requested"] == 0
    assert "task-done" not in redis.sets[manager.running_key]
    assert (
        "comfy:task_events:task-done",
        json.dumps(
            {
                "status": "done",
                "result_path": "outputs/result.mp4",
                "progress": 1.0,
                "task_type": TaskType.LTX_VIDEO,
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

    await redis.hset(task_key, mapping={"status": TaskStatus.RUNNING, "cancel_requested": 1})
    await redis.sadd(manager.running_key, "task-error")

    await manager.fail_task("task-error", "boom")

    assert redis.hashes[task_key]["status"] == TaskStatus.ERROR
    assert redis.hashes[task_key]["error_msg"] == "boom"
    assert redis.hashes[task_key]["cancel_requested"] == 0
    assert "task-error" not in redis.sets[manager.running_key]
    assert (
        "comfy:task_events:task-error",
        json.dumps({"status": "error", "error_msg": "boom"}),
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
async def test_get_queue_size_returns_pending_count():
    redis = _FakeRedis()
    manager = QueueManager(redis)

    await redis.zadd(manager.pending_key, {"task-a": 1.0, "task-b": 2.0})

    assert await manager.get_queue_size() == 2


@pytest.mark.asyncio
async def test_update_task_heartbeat_uses_task_heartbeat_key():
    redis = _FakeRedis()
    manager = QueueManager(redis)

    await manager.update_task_heartbeat("task-heartbeat")

    heartbeat_key = manager._task_heartbeat_key("task-heartbeat")
    assert redis.values[heartbeat_key] == "1"
