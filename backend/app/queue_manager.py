import json
from typing import Any, Dict, Optional, Tuple

from app.models import TaskStatus, TaskType
from app.queue_manager_flow_helpers import (
    build_worker_info_flow,
    build_enqueued_task_payload,
    build_cancel_result,
    cancel_running_task_flow,
    check_zombie_tasks_flow,
    cancel_pending_task_flow,
    complete_task_flow,
    cancel_task_flow,
    dequeue_task_flow,
    fail_task_flow,
    fail_zombie_task_if_needed_flow,
    find_next_allowed_task_flow,
    get_active_workers_count_flow,
    get_all_workers_flow,
    get_queue_metrics_by_type_flow,
    has_task_heartbeat_flow,
    iter_running_task_ids_flow,
    request_running_task_cancellation_flow,
    scan_agent_heartbeat_keys_flow,
    update_progress_flow,
    update_agent_heartbeat_flow,
)
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

    @staticmethod
    def _maybe_parse_json_dict(value: Any) -> dict[str, Any] | None:
        if isinstance(value, dict):
            return value
        if not value:
            return None
        if not isinstance(value, str):
            return None
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return None
        return parsed if isinstance(parsed, dict) else None

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
        existing_task_data = self._decode_redis_dict(
            await self.redis.hgetall(self._task_key(task_id))
        )
        merged_task_data = {**existing_task_data, **task_mapping}
        enriched_event_payload = dict(event_payload)
        if enriched_event_payload.get("status") in {"done", "error"}:
            task_type = merged_task_data.get("type")
            if task_type and "task_type" not in enriched_event_payload:
                enriched_event_payload["task_type"] = task_type

            worker_id = merged_task_data.get("worker_id")
            if worker_id and "worker_id" not in enriched_event_payload:
                enriched_event_payload["worker_id"] = worker_id

            created_at = merged_task_data.get("created_at")
            if created_at not in (None, "") and "created_at" not in enriched_event_payload:
                try:
                    enriched_event_payload["created_at"] = float(created_at)
                except (TypeError, ValueError):
                    enriched_event_payload["created_at"] = created_at

        await self.redis.hset(self._task_key(task_id), mapping=task_mapping)
        if remove_from_running:
            await self.redis.srem(self.running_key, task_id)
        await self._publish_task_event(task_id, enriched_event_payload)

    async def _get_task_type(self, task_id: str) -> Optional[str]:
        task_type_bytes = await self.redis.hget(self._task_key(task_id), "type")
        if not task_type_bytes:
            return None
        return self._decode_redis_value(task_type_bytes)

    def _build_cancel_result(
        self, state: str, task_id: str, message: str, **extra_fields: Any
    ) -> Dict[str, Any]:
        return build_cancel_result(state, task_id, message, **extra_fields)

    async def _cancel_pending_task(self, task_id: str) -> Dict[str, Any]:
        return await cancel_pending_task_flow(
            task_id=task_id,
            persist_task_update_func=self._persist_task_update,
            build_cancel_result_func=self._build_cancel_result,
            cancelled_status=TaskStatus.CANCELLED,
        )

    async def _request_running_task_cancellation(self, task_id: str) -> Dict[str, Any]:
        return await request_running_task_cancellation_flow(
            task_id=task_id,
            persist_task_update_func=self._persist_task_update,
            build_cancel_result_func=self._build_cancel_result,
        )

    async def _cancel_running_task(self, task_id: str) -> Dict[str, Any]:
        return await cancel_running_task_flow(
            task_id=task_id,
            persist_task_update_func=self._persist_task_update,
            build_cancel_result_func=self._build_cancel_result,
            cancelled_status=TaskStatus.CANCELLED,
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
        return await find_next_allowed_task_flow(
            allowed_types=allowed_types,
            zrange_func=self.redis.zrange,
            pending_key=self.pending_key,
            decode_redis_value_func=self._decode_redis_value,
            get_task_type_func=self._get_task_type,
            zrem_func=self.redis.zrem,
            batch_size=batch_size,
        )

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
        return await build_worker_info_flow(
            agent_id=agent_id,
            raw_data=raw_data,
            decode_redis_dict_func=self._decode_redis_dict,
            get_task_status_func=self.get_task_status,
        )

    async def _iter_running_task_ids(self) -> list[str]:
        return await iter_running_task_ids_flow(
            smembers_func=self.redis.smembers,
            running_key=self.running_key,
            decode_redis_value_func=self._decode_redis_value,
        )

    async def _has_task_heartbeat(self, task_id: str) -> bool:
        return await has_task_heartbeat_flow(
            task_id=task_id,
            exists_func=self.redis.exists,
            task_heartbeat_key_func=self._task_heartbeat_key,
        )

    async def _fail_zombie_task_if_needed(self, task_id: str) -> bool:
        return await fail_zombie_task_if_needed_flow(
            task_id=task_id,
            has_task_heartbeat_func=self._has_task_heartbeat,
            fail_task_func=self.fail_task,
        )

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
        return await scan_agent_heartbeat_keys_flow(
            scan_func=self.redis.scan,
            agent_heartbeat_pattern_func=self._agent_heartbeat_pattern,
        )

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
            "extra_outputs": "",
            "trace_id": trace_id,
        }

    def _calculate_enqueue_score(self, *, current_time: float, priority: int) -> float:
        return current_time - (priority * 60)

    async def enqueue_task(
        self, task_type: TaskType, params: Dict[str, Any], priority: int, task_id: str
    ) -> str:
        task_key = self._task_key(task_id)
        task_data, score = build_enqueued_task_payload(
            params=params,
            build_enqueued_task_data_func=self._build_enqueued_task_data,
            calculate_enqueue_score_func=self._calculate_enqueue_score,
            task_id=task_id,
            task_type=task_type,
            priority=priority,
        )

        # Save task details
        await self.redis.hset(task_key, mapping=task_data)
        await self.redis.expire(task_key, self.ttl)

        # Add to priority queue
        # Priority acceleration: Each priority level equals 60 seconds earlier enqueue time.
        # This prevents starvation: a low priority task waiting >60s will beat a new high priority task.
        await self.redis.zadd(self.pending_key, {task_id: score})

        return task_id

    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        task_key = self._task_key(task_id)
        if not await self.redis.exists(task_key):
            return None

        data = await self.redis.hgetall(task_key)
        return self._decode_redis_dict(data)

    async def peek_pending_tasks(
        self,
        allowed_types: Optional[list[str]] = None,
        *,
        limit: int = 1,
        batch_size: int = 50,
    ) -> list[Dict[str, Any]]:
        if limit <= 0:
            return []

        matched_tasks: list[Dict[str, Any]] = []
        offset = 0
        allowed_type_set = set(allowed_types or [])

        while len(matched_tasks) < limit:
            tasks_with_scores = await self.redis.zrange(
                self.pending_key,
                offset,
                offset + batch_size - 1,
                withscores=True,
            )
            if not tasks_with_scores:
                break

            for task_id_raw, _score in tasks_with_scores:
                task_id = self._decode_redis_value(task_id_raw)
                task_details = await self.get_task_status(task_id)
                if not task_details:
                    continue
                if task_details.get("status") != TaskStatus.PENDING:
                    continue
                task_type = task_details.get("type")
                if allowed_type_set and task_type not in allowed_type_set:
                    continue

                matched_tasks.append(task_details)
                if len(matched_tasks) >= limit:
                    break

            offset += batch_size

        return matched_tasks

    async def dequeue_task(
        self, allowed_types: Optional[list[str]] = None
    ) -> Optional[Tuple[str, float]]:
        return await dequeue_task_flow(
            allowed_types=allowed_types,
            pop_next_pending_task_func=self._pop_next_pending_task,
            find_next_allowed_task_func=self._find_next_allowed_task,
            activate_dequeued_task_func=self._activate_dequeued_task,
        )

    async def _mark_task_running(self, task_id: str):
        # Move to running set
        await self.redis.sadd(self.running_key, task_id)
        # Update status
        task_key = self._task_key(task_id)
        await self.redis.hset(task_key, "status", TaskStatus.RUNNING)
        # Initialize heartbeat to prevent immediate zombie detection
        await self.update_task_heartbeat(task_id)

    async def complete_task(
        self,
        task_id: str,
        result_path: str,
        *,
        extra_outputs: dict[str, Any] | None = None,
    ):
        await complete_task_flow(
            task_id=task_id,
            result_path=result_path,
            extra_outputs=extra_outputs,
            get_task_type_func=self._get_task_type,
            persist_task_update_func=self._persist_task_update,
            done_status=TaskStatus.DONE,
        )

    async def fail_task(self, task_id: str, error_msg: str):
        await fail_task_flow(
            task_id=task_id,
            error_msg=error_msg,
            persist_task_update_func=self._persist_task_update,
            error_status=TaskStatus.ERROR,
        )

    async def update_progress(self, task_id: str, progress: float):
        await update_progress_flow(
            task_id=task_id,
            progress=progress,
            persist_task_update_func=self._persist_task_update,
        )

    async def cancel_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        return await cancel_task_flow(
            task_id=task_id,
            task_key=self._task_key(task_id),
            exists_func=self.redis.exists,
            zrem_func=lambda task_id: self.redis.zrem(self.pending_key, task_id),
            cancel_pending_task_func=self._cancel_pending_task,
            request_running_task_cancellation_func=(
                self._request_running_task_cancellation
            ),
            sismember_func=lambda task_id: self.redis.sismember(self.running_key, task_id),
            get_task_status_func=self.get_task_status,
            build_cancel_result_func=self._build_cancel_result,
            cancelled_status=TaskStatus.CANCELLED,
        )

    async def cancel_running_task(self, task_id: str) -> Dict[str, Any]:
        return await self._cancel_running_task(task_id)

    async def get_queue_position(self, task_id: str) -> Optional[int]:
        return await self.redis.zrank(self.pending_key, task_id)

    async def get_queue_size(self) -> int:
        return await self.redis.zcard(self.pending_key)

    async def get_active_workers_count(self) -> int:
        return await get_active_workers_count_flow(
            scan_agent_heartbeat_keys_func=self._scan_agent_heartbeat_keys,
        )

    async def get_all_workers(self) -> list[Dict[str, Any]]:
        return await get_all_workers_flow(
            scan_agent_heartbeat_keys_func=self._scan_agent_heartbeat_keys,
            decode_redis_value_func=self._decode_redis_value,
            agent_heartbeat_prefix=self.agent_heartbeat_prefix,
            hgetall_func=self.redis.hgetall,
            build_worker_info_func=self._build_worker_info,
        )

    async def update_task_heartbeat(self, task_id: str):
        await self.redis.setex(self._task_heartbeat_key(task_id), 300, "1")  # Expire after 5 mins

    async def check_zombie_tasks(self):
        """Finds running tasks that haven't sent a heartbeat recently and marks them as failed."""
        await check_zombie_tasks_flow(
            iter_running_task_ids_func=self._iter_running_task_ids,
            fail_zombie_task_if_needed_func=self._fail_zombie_task_if_needed,
        )

    async def update_agent_heartbeat(
        self,
        agent_id: str,
        types: str,
        status: str,
        *,
        health_reason: str = "",
        last_error: str = "",
        last_error_at: float | str | None = None,
        consecutive_failures: int | str | None = None,
        quarantined_until: float | str | None = None,
    ):
        await update_agent_heartbeat_flow(
            agent_id=agent_id,
            types=types,
            status=status,
            health_reason=health_reason,
            last_error=last_error,
            last_error_at=last_error_at,
            consecutive_failures=consecutive_failures,
            quarantined_until=quarantined_until,
            agent_heartbeat_key_func=self._agent_heartbeat_key,
            hset_func=self.redis.hset,
            expire_func=self.redis.expire,
        )

    async def bind_agent_task(self, task_id: str, agent_id: str):
        await self.redis.hset(self._task_key(task_id), "worker_id", agent_id)
        await self.redis.hset(
            self._agent_heartbeat_key(agent_id),
            "current_task_id",
            task_id,
        )

    async def clear_agent_current_task(self, agent_id: str):
        await self.redis.hdel(
            self._agent_heartbeat_key(agent_id),
            "current_task_id",
        )

    async def get_queue_metrics_by_type(self) -> Dict[str, int]:
        return await get_queue_metrics_by_type_flow(
            zrange_func=self.redis.zrange,
            pending_key=self.pending_key,
            initialize_type_counts_func=self._initialize_type_counts,
            fetch_pending_task_types_func=self._fetch_pending_task_types,
            accumulate_type_counts_func=self._accumulate_type_counts,
        )
