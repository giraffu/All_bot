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

    async def enqueue_task(
        self, task_type: TaskType, params: Dict[str, Any], priority: int, task_id: str
    ) -> str:
        task_key = f"{self.task_prefix}{task_id}"

        trace_id = correlation_id.get() or ""
        # 显式注入 trace_id 到 params 中，用于全链路追踪
        params["trace_id"] = trace_id

        # Create task metadata
        task_data = {
            "task_id": task_id,
            "type": task_type,
            "status": TaskStatus.PENDING,
            "priority": priority,
            "params": json.dumps(params),
            "created_at": time.time(),
            "progress": 0.0,
            "error_msg": "",
            "result_path": "",
            "trace_id": trace_id,
        }

        # Save task details
        await self.redis.hset(task_key, mapping=task_data)
        await self.redis.expire(task_key, self.ttl)

        # Add to priority queue
        # Priority acceleration: Each priority level equals 60 seconds earlier enqueue time.
        # This prevents starvation: a low priority task waiting >60s will beat a new high priority task.
        score = time.time() - (priority * 60)
        await self.redis.zadd(self.pending_key, {task_id: score})

        return task_id

    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        task_key = f"{self.task_prefix}{task_id}"
        if not await self.redis.exists(task_key):
            return None

        data = await self.redis.hgetall(task_key)
        return self._decode_redis_dict(data)

    async def dequeue_task(
        self, allowed_types: Optional[list[str]] = None
    ) -> Optional[Tuple[str, float]]:
        # If no types specified, pop the top task as before
        if not allowed_types:
            result = await self.redis.zpopmin(self.pending_key)
            if not result:
                return None
            task_id, score = result[0]
            task_id = task_id.decode() if isinstance(task_id, bytes) else task_id
            await self._mark_task_running(task_id)
            return task_id, score

        # If specific types are allowed, find the highest priority task matching those types
        # We fetch a batch of tasks to minimize Redis roundtrips
        batch_size = 50
        offset = 0
        while True:
            tasks_with_scores = await self.redis.zrange(
                self.pending_key, offset, offset + batch_size - 1, withscores=True
            )
            if not tasks_with_scores:
                return None

            for task_id_bytes, score in tasks_with_scores:
                task_id = (
                    task_id_bytes.decode()
                    if isinstance(task_id_bytes, bytes)
                    else task_id_bytes
                )
                task_key = f"{self.task_prefix}{task_id}"

                # Check task type
                task_type_bytes = await self.redis.hget(task_key, "type")
                if not task_type_bytes:
                    continue

                task_type = (
                    task_type_bytes.decode()
                    if isinstance(task_type_bytes, bytes)
                    else task_type_bytes
                )
                if task_type in allowed_types:
                    # Atomically remove from pending and check if we succeeded (to avoid race conditions)
                    removed = await self.redis.zrem(self.pending_key, task_id)
                    if removed:
                        await self._mark_task_running(task_id)
                        return task_id, score

            offset += batch_size

    async def _mark_task_running(self, task_id: str):
        # Move to running set
        await self.redis.sadd(self.running_key, task_id)
        # Update status
        task_key = f"{self.task_prefix}{task_id}"
        await self.redis.hset(task_key, "status", TaskStatus.RUNNING)
        # Initialize heartbeat to prevent immediate zombie detection
        await self.update_task_heartbeat(task_id)

    async def complete_task(self, task_id: str, result_path: str):
        task_key = f"{self.task_prefix}{task_id}"

        # 先从 Redis 中读取 type
        task_type_bytes = await self.redis.hget(task_key, "type")
        task_type = self._decode_redis_value(task_type_bytes) if task_type_bytes else "edit"

        await self.redis.hset(
            task_key,
            mapping={
                "status": TaskStatus.DONE,
                "result_path": result_path,
                "progress": 1.0,
                "cancel_requested": 0,
            },
        )
        await self.redis.srem(self.running_key, task_id)
        await self.redis.publish(
            f"comfy:task_events:{task_id}",
            json.dumps(
                {
                    "status": "done",
                    "result_path": result_path,
                    "progress": 1.0,
                    "task_type": task_type,
                }
            ),
        )

    async def fail_task(self, task_id: str, error_msg: str):
        task_key = f"{self.task_prefix}{task_id}"
        await self.redis.hset(
            task_key,
            mapping={
                "status": TaskStatus.ERROR,
                "error_msg": error_msg,
                "cancel_requested": 0,
            },
        )
        await self.redis.srem(self.running_key, task_id)
        await self.redis.publish(
            f"comfy:task_events:{task_id}",
            json.dumps({"status": "error", "error_msg": error_msg}),
        )

    async def update_progress(self, task_id: str, progress: float):
        task_key = f"{self.task_prefix}{task_id}"
        await self.redis.hset(task_key, "progress", progress)
        await self.redis.publish(
            f"comfy:task_events:{task_id}",
            json.dumps({"status": "running", "progress": progress}),
        )

    async def cancel_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        task_key = f"{self.task_prefix}{task_id}"
        if not await self.redis.exists(task_key):
            return None

        removed_from_pending = await self.redis.zrem(self.pending_key, task_id)
        if removed_from_pending:
            await self.redis.srem(self.running_key, task_id)
            await self.redis.hset(
                task_key,
                mapping={
                    "status": TaskStatus.CANCELLED,
                    "cancel_requested": 0,
                    "cancel_requested_at": "",
                },
            )
            await self.redis.publish(
                f"comfy:task_events:{task_id}", json.dumps({"status": "cancelled"})
            )
            return {
                "state": "cancelled",
                "task_id": task_id,
                "message": "任务已从排队队列移除",
            }

        is_running = bool(await self.redis.sismember(self.running_key, task_id))
        if is_running:
            cancel_requested_at = time.time()
            await self.redis.hset(
                task_key,
                mapping={
                    "cancel_requested": 1,
                    "cancel_requested_at": cancel_requested_at,
                },
            )
            await self.redis.publish(
                f"comfy:task_events:{task_id}",
                json.dumps(
                    {
                        "status": "running",
                        "cancel_requested": True,
                        "message": "已请求取消，等待执行端确认",
                    }
                ),
            )
            return {
                "state": "cancellation_requested",
                "task_id": task_id,
                "message": "任务已请求取消，等待执行端确认",
                "cancel_requested": True,
                "cancel_requested_at": cancel_requested_at,
            }

        task_data = await self.get_task_status(task_id)
        status = task_data.get("status") if task_data else None
        if status == TaskStatus.CANCELLED:
            return {
                "state": "already_cancelled",
                "task_id": task_id,
                "message": "任务已取消",
            }

        return {
            "state": "not_cancellable",
            "task_id": task_id,
            "message": "任务已结束，无法再取消",
        }

    async def get_queue_position(self, task_id: str) -> Optional[int]:
        return await self.redis.zrank(self.pending_key, task_id)

    async def get_queue_size(self) -> int:
        return await self.redis.zcard(self.pending_key)

    async def get_active_workers_count(self) -> int:
        # Get count of agents that have sent a heartbeat recently
        cursor = 0
        count = 0
        pattern = f"{self.agent_heartbeat_prefix}*"
        while True:
            cursor, keys = await self.redis.scan(cursor, match=pattern, count=100)
            count += len(keys)
            if cursor == 0:
                break
        return count

    async def get_all_workers(self) -> list[Dict[str, Any]]:
        cursor = 0
        workers = []
        pattern = f"{self.agent_heartbeat_prefix}*"
        while True:
            cursor, keys = await self.redis.scan(cursor, match=pattern, count=100)
            for key in keys:
                key_str = key.decode() if isinstance(key, bytes) else key
                agent_id = key_str.replace(self.agent_heartbeat_prefix, "")
                data = await self.redis.hgetall(key)
                if data:
                    worker_info = self._decode_redis_dict(data)
                    worker_info["agent_id"] = agent_id

                    # Fetch current task details if running
                    current_task_id = worker_info.get("current_task_id")
                    if worker_info.get("status") == "running" and current_task_id:
                        task_data = await self.get_task_status(current_task_id)
                        if task_data:
                            worker_info["current_task_type"] = task_data.get("type")
                            worker_info["current_task_progress"] = float(
                                task_data.get("progress", 0.0)
                            )
                            worker_info["current_task_created_at"] = float(
                                task_data.get("created_at", 0.0)
                            )

                    workers.append(worker_info)
            if cursor == 0:
                break
        return workers

    async def update_task_heartbeat(self, task_id: str):
        key = f"comfy:task_heartbeat:{task_id}"
        await self.redis.setex(key, 300, "1")  # Expire after 5 mins

    async def check_zombie_tasks(self):
        """Finds running tasks that haven't sent a heartbeat recently and marks them as failed."""
        running_tasks = await self.redis.smembers(self.running_key)
        for task_id_bytes in running_tasks:
            task_id = (
                task_id_bytes.decode()
                if isinstance(task_id_bytes, bytes)
                else task_id_bytes
            )
            key = f"comfy:task_heartbeat:{task_id}"
            if not await self.redis.exists(key):
                # It's a zombie!
                await self.fail_task(
                    task_id, "Task execution timed out (Worker heartbeat lost)"
                )

    async def update_agent_heartbeat(self, agent_id: str, types: str, status: str):
        key = f"{self.agent_heartbeat_prefix}{agent_id}"
        data = {"types": types, "status": status, "last_seen": time.time()}
        await self.redis.hset(key, mapping=data)
        # Agent heartbeats every 10-15s, expire if no heartbeat for 30s
        await self.redis.expire(key, 30)

    async def get_queue_metrics_by_type(self) -> Dict[str, int]:
        task_ids = await self.redis.zrange(self.pending_key, 0, -1)

        # Initialize counts for all known types to 0
        counts = {t.value: 0 for t in TaskType}

        if not task_ids:
            return counts

        # Use pipeline to fetch types efficiently
        pipeline = self.redis.pipeline()
        for task_id in task_ids:
            task_id_str = task_id.decode() if isinstance(task_id, bytes) else task_id
            task_key = f"{self.task_prefix}{task_id_str}"
            pipeline.hget(task_key, "type")

        types = await pipeline.execute()

        for t in types:
            if t:
                type_str = t.decode() if isinstance(t, bytes) else t
                if type_str in counts:
                    counts[type_str] += 1
                else:
                    counts[type_str] = counts.get(type_str, 0) + 1

        return counts
