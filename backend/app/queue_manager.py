import json
import time
from typing import Any, Dict, Optional, Tuple

from app.models import TaskStatus, TaskType
from asgi_correlation_id import correlation_id
from redis.asyncio import Redis


class QueueManager:
    def __init__(self, redis: Redis):
        self.redis = redis
        self.pending_key = "comfy:queue:pending"
        self.running_key = "comfy:queue:running"
        self.task_prefix = "comfy:task:"
        self.agent_heartbeat_prefix = "comfy:agent:heartbeat:"
        self.ttl = 86400  # 24 hours

    @staticmethod
    def _decode_redis_value(value: Any) -> Any:
        return value.decode() if isinstance(value, bytes) else value

    @classmethod
    def _decode_redis_dict(cls, data: Dict[Any, Any]) -> Dict[str, Any]:
        return {
            str(cls._decode_redis_value(k)): cls._decode_redis_value(v)
            for k, v in data.items()
        }

    @staticmethod
    def _as_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in {"1", "true", "yes", "on"}
        return bool(value)

    def _task_key(self, task_id: str) -> str:
        return f"{self.task_prefix}{task_id}"

    def _task_event_channel(self, task_id: str) -> str:
        return f"comfy:task_events:{task_id}"

    def _task_heartbeat_key(self, task_id: str) -> str:
        return f"comfy:task_heartbeat:{task_id}"

    def _agent_heartbeat_pattern(self) -> str:
        return f"{self.agent_heartbeat_prefix}*"

    def _agent_heartbeat_key(self, agent_id: str) -> str:
        return f"{self.agent_heartbeat_prefix}{agent_id}"

    async def _publish_task_event(self, task_id: str, payload: Dict[str, Any]) -> None:
        await self.redis.publish(self._task_event_channel(task_id), json.dumps(payload))

    async def _persist_task_update(
        self,
        task_id: str,
        *,
        task_mapping: Dict[str, Any],
        event_payload: Dict[str, Any],
        remove_from_running: bool = False,
    ) -> None:
        await self.redis.hset(self._task_key(task_id), mapping=task_mapping)
        if remove_from_running:
            await self.redis.srem(self.running_key, task_id)
        await self._publish_task_event(task_id, event_payload)

    async def _get_task_type(self, task_id: str) -> Optional[str]:
        task_type_bytes = await self.redis.hget(self._task_key(task_id), "type")
        if not task_type_bytes:
            return None
        return self._decode_redis_value(task_type_bytes)

    def _build_cancel_result(
        self, state: str, task_id: str, message: str, **extra_fields: Any
    ) -> Dict[str, Any]:
        return {
            "state": state,
            "task_id": task_id,
            "message": message,
            **extra_fields,
        }

    async def _cancel_pending_task(self, task_id: str) -> Dict[str, Any]:
        await self._persist_task_update(
            task_id,
            task_mapping={
                "status": TaskStatus.CANCELLED,
                "cancel_requested": 0,
                "cancel_requested_at": "",
            },
            event_payload={"status": "cancelled"},
            remove_from_running=True,
        )
        return self._build_cancel_result("cancelled", task_id, "任务已从排队队列移除")

    async def _request_running_task_cancellation(self, task_id: str) -> Dict[str, Any]:
        cancel_requested_at = time.time()
        await self._persist_task_update(
            task_id,
            task_mapping={
                "cancel_requested": 1,
                "cancel_requested_at": cancel_requested_at,
            },
            event_payload={
                "status": "running",
                "cancel_requested": True,
                "message": "已请求取消，等待执行端确认",
            },
        )
        return self._build_cancel_result(
            "cancellation_requested",
            task_id,
            "任务已请求取消，等待执行端确认",
            cancel_requested=True,
            cancel_requested_at=cancel_requested_at,
        )

    async def _pop_next_pending_task(self) -> Optional[Tuple[str, float]]:
        result = await self.redis.zpopmin(self.pending_key)
        if not result:
            return None
        task_id, score = result[0]
        return self._decode_redis_value(task_id), score

    async def _find_next_allowed_task(
        self, allowed_types: list[str], *, batch_size: int = 50
    ) -> Optional[Tuple[str, float]]:
        offset = 0
        while True:
            tasks_with_scores = await self.redis.zrange(
                self.pending_key, offset, offset + batch_size - 1, withscores=True
            )
            if not tasks_with_scores:
                return None

            for task_id_bytes, score in tasks_with_scores:
                task_id = self._decode_redis_value(task_id_bytes)
                task_type = await self._get_task_type(task_id)
                if not task_type or task_type not in allowed_types:
                    continue

                # Atomically remove from pending and check if we succeeded (to avoid race conditions)
                removed = await self.redis.zrem(self.pending_key, task_id)
                if removed:
                    return task_id, score

            offset += batch_size

    async def _activate_dequeued_task(
        self, next_task: Optional[Tuple[str, float]]
    ) -> Optional[Tuple[str, float]]:
        if not next_task:
            return None
        task_id, score = next_task
        await self._mark_task_running(task_id)
        return task_id, score

    async def _build_worker_info(
        self, agent_id: str, raw_data: Dict[Any, Any]
    ) -> Dict[str, Any] | None:
        if not raw_data:
            return None

        worker_info = self._decode_redis_dict(raw_data)
        worker_info["agent_id"] = agent_id

        current_task_id = worker_info.get("current_task_id")
        if worker_info.get("status") == "running" and current_task_id:
            task_data = await self.get_task_status(current_task_id)
            if task_data:
                worker_info["current_task_type"] = task_data.get("type")
                worker_info["current_task_progress"] = float(task_data.get("progress", 0.0))
                worker_info["current_task_created_at"] = float(
                    task_data.get("created_at", 0.0)
                )

        return worker_info

    async def _iter_running_task_ids(self) -> list[str]:
        running_tasks = await self.redis.smembers(self.running_key)
        return [self._decode_redis_value(task_id) for task_id in running_tasks]

    async def _has_task_heartbeat(self, task_id: str) -> bool:
        return bool(await self.redis.exists(self._task_heartbeat_key(task_id)))

    async def _fail_zombie_task_if_needed(self, task_id: str) -> bool:
        if await self._has_task_heartbeat(task_id):
            return False
        await self.fail_task(task_id, "Task execution timed out (Worker heartbeat lost)")
        return True

    def _initialize_type_counts(self) -> Dict[str, int]:
        return {t.value: 0 for t in TaskType}

    async def _fetch_pending_task_types(self, task_ids: list[Any]) -> list[Any]:
        pipeline = self.redis.pipeline()
        for task_id in task_ids:
            task_id_str = self._decode_redis_value(task_id)
            pipeline.hget(self._task_key(task_id_str), "type")
        return await pipeline.execute()

    def _accumulate_type_counts(
        self, counts: Dict[str, int], task_types: list[Any]
    ) -> Dict[str, int]:
        for task_type in task_types:
            if not task_type:
                continue
            type_str = self._decode_redis_value(task_type)
            if type_str in counts:
                counts[type_str] += 1
            else:
                counts[type_str] = counts.get(type_str, 0) + 1
        return counts

    async def _scan_agent_heartbeat_keys(self) -> list[Any]:
        cursor = 0
        keys: list[Any] = []
        pattern = self._agent_heartbeat_pattern()
        while True:
            cursor, batch = await self.redis.scan(cursor, match=pattern, count=100)
            keys.extend(batch)
            if cursor == 0:
                break
        return keys

    def _build_enqueued_task_data(
        self,
        *,
        task_id: str,
        task_type: TaskType,
        priority: int,
        params: Dict[str, Any],
        trace_id: str,
        created_at: float,
    ) -> Dict[str, Any]:
        return {
            "task_id": task_id,
            "type": task_type,
            "status": TaskStatus.PENDING,
            "priority": priority,
            "params": json.dumps(params),
            "created_at": created_at,
            "progress": 0.0,
            "error_msg": "",
            "result_path": "",
            "trace_id": trace_id,
        }

    def _calculate_enqueue_score(self, *, current_time: float, priority: int) -> float:
        return current_time - (priority * 60)

    async def enqueue_task(
        self, task_type: TaskType, params: Dict[str, Any], priority: int, task_id: str
    ) -> str:
        task_key = self._task_key(task_id)

        trace_id = correlation_id.get() or ""
        # 显式注入 trace_id 到 params 中，用于全链路追踪
        params["trace_id"] = trace_id
        created_at = time.time()

        task_data = self._build_enqueued_task_data(
            task_id=task_id,
            task_type=task_type,
            priority=priority,
            params=params,
            trace_id=trace_id,
            created_at=created_at,
        )

        # Save task details
        await self.redis.hset(task_key, mapping=task_data)
        await self.redis.expire(task_key, self.ttl)

        # Add to priority queue
        # Priority acceleration: Each priority level equals 60 seconds earlier enqueue time.
        # This prevents starvation: a low priority task waiting >60s will beat a new high priority task.
        score = self._calculate_enqueue_score(current_time=created_at, priority=priority)
        await self.redis.zadd(self.pending_key, {task_id: score})

        return task_id

    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        task_key = self._task_key(task_id)
        if not await self.redis.exists(task_key):
            return None

        data = await self.redis.hgetall(task_key)
        return self._decode_redis_dict(data)

    async def dequeue_task(
        self, allowed_types: Optional[list[str]] = None
    ) -> Optional[Tuple[str, float]]:
        # If no types specified, pop the top task as before
        if not allowed_types:
            return await self._activate_dequeued_task(await self._pop_next_pending_task())

        # If specific types are allowed, find the highest priority task matching those types
        return await self._activate_dequeued_task(
            await self._find_next_allowed_task(allowed_types)
        )

    async def _mark_task_running(self, task_id: str):
        # Move to running set
        await self.redis.sadd(self.running_key, task_id)
        # Update status
        task_key = self._task_key(task_id)
        await self.redis.hset(task_key, "status", TaskStatus.RUNNING)
        # Initialize heartbeat to prevent immediate zombie detection
        await self.update_task_heartbeat(task_id)

    async def complete_task(self, task_id: str, result_path: str):
        # 先从 Redis 中读取 type
        task_type = await self._get_task_type(task_id) or "edit"

        await self._persist_task_update(
            task_id,
            task_mapping={
                "status": TaskStatus.DONE,
                "result_path": result_path,
                "progress": 1.0,
                "cancel_requested": 0,
            },
            event_payload={
                "status": "done",
                "result_path": result_path,
                "progress": 1.0,
                "task_type": task_type,
            },
            remove_from_running=True,
        )

    async def fail_task(self, task_id: str, error_msg: str):
        await self._persist_task_update(
            task_id,
            task_mapping={
                "status": TaskStatus.ERROR,
                "error_msg": error_msg,
                "cancel_requested": 0,
            },
            event_payload={"status": "error", "error_msg": error_msg},
            remove_from_running=True,
        )

    async def update_progress(self, task_id: str, progress: float):
        await self._persist_task_update(
            task_id,
            task_mapping={"progress": progress},
            event_payload={"status": "running", "progress": progress},
        )

    async def cancel_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        task_key = self._task_key(task_id)
        if not await self.redis.exists(task_key):
            return None

        removed_from_pending = await self.redis.zrem(self.pending_key, task_id)
        if removed_from_pending:
            return await self._cancel_pending_task(task_id)

        is_running = bool(await self.redis.sismember(self.running_key, task_id))
        if is_running:
            return await self._request_running_task_cancellation(task_id)

        task_data = await self.get_task_status(task_id)
        status = task_data.get("status") if task_data else None
        if status == TaskStatus.CANCELLED:
            return self._build_cancel_result("already_cancelled", task_id, "任务已取消")

        return self._build_cancel_result("not_cancellable", task_id, "任务已结束，无法再取消")

    async def get_queue_position(self, task_id: str) -> Optional[int]:
        return await self.redis.zrank(self.pending_key, task_id)

    async def get_queue_size(self) -> int:
        return await self.redis.zcard(self.pending_key)

    async def get_active_workers_count(self) -> int:
        # Get count of agents that have sent a heartbeat recently
        return len(await self._scan_agent_heartbeat_keys())

    async def get_all_workers(self) -> list[Dict[str, Any]]:
        workers = []
        for key in await self._scan_agent_heartbeat_keys():
            key_str = self._decode_redis_value(key)
            agent_id = key_str.replace(self.agent_heartbeat_prefix, "")
            data = await self.redis.hgetall(key)
            worker_info = await self._build_worker_info(agent_id, data)
            if worker_info:
                workers.append(worker_info)
        return workers

    async def update_task_heartbeat(self, task_id: str):
        await self.redis.setex(self._task_heartbeat_key(task_id), 300, "1")  # Expire after 5 mins

    async def check_zombie_tasks(self):
        """Finds running tasks that haven't sent a heartbeat recently and marks them as failed."""
        for task_id in await self._iter_running_task_ids():
            await self._fail_zombie_task_if_needed(task_id)

    async def update_agent_heartbeat(self, agent_id: str, types: str, status: str):
        key = self._agent_heartbeat_key(agent_id)
        data = {"types": types, "status": status, "last_seen": time.time()}
        await self.redis.hset(key, mapping=data)
        # Agent heartbeats every 10-15s, expire if no heartbeat for 30s
        await self.redis.expire(key, 30)

    async def get_queue_metrics_by_type(self) -> Dict[str, int]:
        task_ids = await self.redis.zrange(self.pending_key, 0, -1)

        # Initialize counts for all known types to 0
        counts = self._initialize_type_counts()

        if not task_ids:
            return counts

        task_types = await self._fetch_pending_task_types(task_ids)
        return self._accumulate_type_counts(counts, task_types)
