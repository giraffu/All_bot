import asyncio
import hashlib
import json
import logging
import time
import uuid
from typing import Any, Dict, Optional, Tuple

from app.models import TaskStatus, TaskType
from app.queue_manager_flow_helpers import (
    build_cancel_result,
    build_enqueued_task_payload,
    build_worker_info_flow,
    cancel_pending_task_flow,
    cancel_running_task_flow,
    cancel_task_flow,
    check_zombie_tasks_flow,
    complete_task_flow,
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
    update_agent_heartbeat_flow,
    update_progress_flow,
)
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError
from src.services.task_text_stream_store import (
    append_text_delta,
    serialize_text_stream_event,
)

logger = logging.getLogger(__name__)

REDIS_TRANSIENT_RETRY_ATTEMPTS = 3
REDIS_TRANSIENT_RETRY_BASE_DELAY_SECONDS = 0.05
_REDIS_TRANSIENT_ERRORS = (
    RedisConnectionError,
    RedisTimeoutError,
    ConnectionError,
    ConnectionResetError,
    TimeoutError,
    OSError,
)

_CREATE_TASK_IF_ABSENT_SCRIPT = """
local existing_fingerprint = redis.call('HGET', KEYS[1], 'request_fingerprint')
if existing_fingerprint then
    if existing_fingerprint == ARGV[1] then
        return 0
    end
    return -1
end
if redis.call('EXISTS', KEYS[1]) == 1 then
    return -1
end

local task_data = cjson.decode(ARGV[2])
for field, value in pairs(task_data) do
    redis.call('HSET', KEYS[1], field, tostring(value))
end
redis.call('EXPIRE', KEYS[1], tonumber(ARGV[3]))
redis.call('ZADD', KEYS[2], tonumber(ARGV[4]), ARGV[5])
return 1
"""

_POP_PREFERRED_TASK_SCRIPT = """
local allowed_count = tonumber(ARGV[1])
local preferred_count = tonumber(ARGV[2])
local allowed = {}
local preferred = {}
for index = 1, allowed_count do
    allowed[ARGV[2 + index]] = true
end
for index = 1, preferred_count do
    preferred[ARGV[2 + allowed_count + index]] = true
end

local fallback_id = nil
local fallback_score = nil
local pending = redis.call('ZRANGE', KEYS[1], 0, -1, 'WITHSCORES')
for index = 1, #pending, 2 do
    local task_id = pending[index]
    local score = pending[index + 1]
    local task_type = redis.call('HGET', KEYS[2] .. task_id, 'type')
    if task_type and allowed[task_type] then
        if not fallback_id then
            fallback_id = task_id
            fallback_score = score
        end
        if preferred[task_type] then
            if redis.call('ZREM', KEYS[1], task_id) == 1 then
                return {task_id, score}
            end
            return {}
        end
    end
end

if fallback_id and redis.call('ZREM', KEYS[1], fallback_id) == 1 then
    return {fallback_id, fallback_score}
end
return {}
"""

_TRANSITION_TASK_TERMINAL_SCRIPT = """
local current = redis.call('HGET', KEYS[1], 'status')
if not current then return -1 end
if current == 'done' or current == 'error' or current == 'cancelled' then
    return 0
end
local task_data = cjson.decode(ARGV[1])
for field, value in pairs(task_data) do
    redis.call('HSET', KEYS[1], field, tostring(value))
end
if ARGV[2] == '1' then redis.call('SREM', KEYS[2], ARGV[3]) end
return 1
"""


class TaskAdmissionConflictError(RuntimeError):
    pass


class QueueManager:
    def __init__(self, redis: Redis):
        self.redis = redis
        self.pending_key = "comfy:queue:pending"
        self.running_key = "comfy:queue:running"
        self.task_prefix = "comfy:task:"
        self.agent_heartbeat_prefix = "comfy:agent:heartbeat:"
        self.agent_control_prefix = "comfy:agent:control:"
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

    def _agent_control_key(self, agent_id: str) -> str:
        return f"{self.agent_control_prefix}{agent_id}"

    async def _retry_redis_call(self, operation_name: str, redis_call, *args, **kwargs):
        for attempt in range(1, REDIS_TRANSIENT_RETRY_ATTEMPTS + 1):
            try:
                return await redis_call(*args, **kwargs)
            except _REDIS_TRANSIENT_ERRORS as exc:
                if attempt >= REDIS_TRANSIENT_RETRY_ATTEMPTS:
                    raise
                logger.warning(
                    "Transient Redis error during %s (attempt %s/%s): %s",
                    operation_name,
                    attempt,
                    REDIS_TRANSIENT_RETRY_ATTEMPTS,
                    exc,
                )
                await asyncio.sleep(REDIS_TRANSIENT_RETRY_BASE_DELAY_SECONDS * attempt)

    async def _single_redis_call(self, operation_name: str, redis_call, *args, **kwargs):
        try:
            return await redis_call(*args, **kwargs)
        except _REDIS_TRANSIENT_ERRORS as exc:
            logger.warning(
                "Transient Redis error during non-retried %s: %s",
                operation_name,
                exc,
            )
            raise

    async def _publish_task_event(self, task_id: str, payload: Dict[str, Any]) -> None:
        await self._retry_redis_call(
            "publish_task_event",
            self.redis.publish,
            self._task_event_channel(task_id),
            json.dumps(payload),
        )

    async def append_task_text_delta(
        self,
        *,
        task_id: str,
        agent_id: str,
        attempt_id: str,
        sequence: int,
        field: str,
        delta: str,
    ) -> dict[str, Any]:
        # Validate UUID at the protocol boundary even when this method is called directly.
        uuid.UUID(attempt_id)
        result = await append_text_delta(
            self.redis,
            task_key=self._task_key(task_id),
            task_id=task_id,
            agent_id=agent_id,
            attempt_id=attempt_id,
            sequence=sequence,
            field=field,
            delta=delta,
            updated_at=time.time(),
        )
        if result.accepted:
            payload = {
                "event_type": "text_delta",
                "schema_version": "allbot.text_stream.v1",
                "attempt_id": attempt_id,
                "sequence": sequence,
                "field": field,
                "delta": delta,
            }
            await self._retry_redis_call(
                "publish_task_text_delta",
                self.redis.publish,
                self._task_event_channel(task_id),
                serialize_text_stream_event(payload),
            )
        return {
            "status": "ok",
            "accepted": result.accepted,
            "last_sequence": result.last_sequence,
        }

    async def _persist_task_update(
        self,
        task_id: str,
        *,
        task_mapping: Dict[str, Any],
        event_payload: Dict[str, Any],
        remove_from_running: bool = False,
    ) -> None:
        existing_task_data = self._decode_redis_dict(
            await self._retry_redis_call(
                "persist_task_update_hgetall",
                self.redis.hgetall,
                self._task_key(task_id),
            )
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

        is_terminal = enriched_event_payload.get("status") in {"done", "error"}
        if is_terminal:
            normalized_mapping = {
                key: "" if value is None else value for key, value in task_mapping.items()
            }
            transitioned = await self._retry_redis_call(
                "persist_task_terminal_transition",
                self.redis.eval,
                _TRANSITION_TASK_TERMINAL_SCRIPT,
                2,
                self._task_key(task_id),
                self.running_key,
                json.dumps(normalized_mapping, default=str),
                "1" if remove_from_running else "0",
                task_id,
            )
            if int(transitioned) <= 0:
                return
        else:
            await self._retry_redis_call(
                "persist_task_update_hset",
                self.redis.hset,
                self._task_key(task_id),
                mapping=task_mapping,
            )
            if remove_from_running:
                await self._retry_redis_call(
                    "persist_task_update_srem",
                    self.redis.srem,
                    self.running_key,
                    task_id,
                )
        await self._publish_task_event(task_id, enriched_event_payload)

    async def _get_task_type(self, task_id: str) -> Optional[str]:
        task_type_bytes = await self._retry_redis_call(
            "get_task_type",
            self.redis.hget,
            self._task_key(task_id),
            "type",
        )
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
        result = await self._single_redis_call(
            "pop_next_pending_task",
            self.redis.zpopmin,
            self.pending_key,
        )
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

    async def _pop_preferred_or_fallback_task(
        self,
        *,
        allowed_types: list[str],
        preferred_types: list[str],
    ) -> Optional[Tuple[str, float]]:
        result = await self._single_redis_call(
            "pop_preferred_or_fallback_task",
            self.redis.eval,
            _POP_PREFERRED_TASK_SCRIPT,
            2,
            self.pending_key,
            self.task_prefix,
            len(allowed_types),
            len(preferred_types),
            *allowed_types,
            *preferred_types,
        )
        if not result:
            return None
        task_id, score = result
        return self._decode_redis_value(task_id), float(score)

    async def _activate_dequeued_task(
        self,
        next_task: Optional[Tuple[str, float]],
        *,
        cancel_lock: bool = False,
    ) -> Optional[Tuple[str, float]]:
        if not next_task:
            return None
        task_id, score = next_task
        await self._mark_task_running(task_id, cancel_lock=cancel_lock)
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
        async def execute_pipeline():
            pipeline = self.redis.pipeline()
            for task_id in task_ids:
                task_id_str = self._decode_redis_value(task_id)
                pipeline.hget(self._task_key(task_id_str), "type")
            return await pipeline.execute()

        return await self._retry_redis_call(
            "fetch_pending_task_types",
            execute_pipeline,
        )

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

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        if value in (None, ""):
            return None
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _task_type_key(value: Any) -> str:
        value = QueueManager._decode_redis_value(value)
        if isinstance(value, TaskType):
            return value.value
        return str(value or "").strip()

    @staticmethod
    def _empty_queue_metrics_detail() -> dict[str, Any]:
        return {
            "pending_count": 0,
            "max_pending_wait_seconds": None,
        }

    @staticmethod
    def _update_wait_max(
        detail: dict[str, Any],
        field: str,
        wait_seconds: int,
    ) -> None:
        current = detail.get(field)
        if current is None or wait_seconds > current:
            detail[field] = wait_seconds

    async def _scan_agent_heartbeat_keys(self) -> list[Any]:
        return await scan_agent_heartbeat_keys_flow(
            scan_func=lambda *args, **kwargs: self._retry_redis_call(
                "scan_agent_heartbeat_keys",
                self.redis.scan,
                *args,
                **kwargs,
            ),
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
            "result_kind": "",
            "result_text": "",
            "result_meta": "",
            "trace_id": trace_id,
        }

    def _calculate_enqueue_score(self, *, current_time: float, priority: int) -> float:
        return current_time - (priority * 60)

    @staticmethod
    def _request_fingerprint(
        *,
        task_type: TaskType,
        params: Dict[str, Any],
        priority: int,
    ) -> str:
        canonical_params = {
            key: value
            for key, value in params.items()
            if key != "trace_id"
        }
        encoded = json.dumps(
            {
                "task_type": task_type.value,
                "priority": int(priority),
                "params": canonical_params,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    async def enqueue_task(
        self, task_type: TaskType, params: Dict[str, Any], priority: int, task_id: str
    ) -> str:
        task_key = self._task_key(task_id)
        request_fingerprint = self._request_fingerprint(
            task_type=task_type,
            params=params,
            priority=priority,
        )
        task_data, score = build_enqueued_task_payload(
            params=dict(params),
            build_enqueued_task_data_func=self._build_enqueued_task_data,
            calculate_enqueue_score_func=self._calculate_enqueue_score,
            task_id=task_id,
            task_type=task_type,
            priority=priority,
        )
        task_data["request_fingerprint"] = request_fingerprint
        admission_result = await self._retry_redis_call(
            "enqueue_task_create_if_absent",
            self.redis.eval,
            _CREATE_TASK_IF_ABSENT_SCRIPT,
            2,
            task_key,
            self.pending_key,
            request_fingerprint,
            json.dumps(task_data, default=str),
            str(self.ttl),
            str(score),
            task_id,
        )
        if admission_result == -1:
            raise TaskAdmissionConflictError(
                f"task_id {task_id} already exists with different parameters"
            )

        return task_id

    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        task_key = self._task_key(task_id)
        if not await self._retry_redis_call(
            "get_task_status_exists",
            self.redis.exists,
            task_key,
        ):
            return None

        data = await self._retry_redis_call(
            "get_task_status_hgetall",
            self.redis.hgetall,
            task_key,
        )
        return self._decode_redis_dict(data)

    async def peek_pending_tasks(
        self,
        allowed_types: Optional[list[str]] = None,
        preferred_types: Optional[list[str]] = None,
        *,
        limit: int = 1,
        batch_size: int = 50,
    ) -> list[Dict[str, Any]]:
        if limit <= 0:
            return []

        if not preferred_types:
            return await self._peek_pending_tasks_in_score_order(
                allowed_types=allowed_types,
                limit=limit,
                batch_size=batch_size,
            )

        preferred_set = set(preferred_types)
        preferred_matches: list[Dict[str, Any]] = []
        fallback_matches: list[Dict[str, Any]] = []
        offset = 0
        allowed_type_set = set(allowed_types or [])
        while len(preferred_matches) < limit:
            tasks_with_scores = await self._retry_redis_call(
                "peek_pending_tasks_zrange",
                self.redis.zrange,
                self.pending_key,
                offset,
                offset + batch_size - 1,
                withscores=True,
            )
            if not tasks_with_scores:
                break
            for task_id_raw, _score in tasks_with_scores:
                task_details = await self.get_task_status(
                    self._decode_redis_value(task_id_raw)
                )
                if not task_details or task_details.get("status") != TaskStatus.PENDING:
                    continue
                task_type = task_details.get("type")
                if allowed_type_set and task_type not in allowed_type_set:
                    continue
                target = (
                    preferred_matches
                    if task_type in preferred_set
                    else fallback_matches
                )
                if len(target) < limit:
                    target.append(task_details)
            offset += batch_size
        return (preferred_matches + fallback_matches)[:limit]

    async def _peek_pending_tasks_in_score_order(
        self,
        *,
        allowed_types: Optional[list[str]],
        limit: int,
        batch_size: int,
    ) -> list[Dict[str, Any]]:
        matched_tasks: list[Dict[str, Any]] = []
        offset = 0
        allowed_type_set = set(allowed_types or [])

        while len(matched_tasks) < limit:
            tasks_with_scores = await self._retry_redis_call(
                "peek_pending_tasks_zrange",
                self.redis.zrange,
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
        self,
        allowed_types: Optional[list[str]] = None,
        preferred_types: Optional[list[str]] = None,
        *,
        cancel_lock: bool = False,
    ) -> Optional[Tuple[str, float]]:
        if preferred_types:
            next_task = await self._pop_preferred_or_fallback_task(
                allowed_types=list(allowed_types or []),
                preferred_types=preferred_types,
            )
            return await self._activate_dequeued_task(
                next_task,
                cancel_lock=cancel_lock,
            )
        return await dequeue_task_flow(
            allowed_types=allowed_types,
            pop_next_pending_task_func=self._pop_next_pending_task,
            find_next_allowed_task_func=self._find_next_allowed_task,
            activate_dequeued_task_func=self._activate_dequeued_task,
            cancel_lock=cancel_lock,
        )

    async def _mark_task_running(self, task_id: str, *, cancel_lock: bool = False):
        # Move to running set
        await self._retry_redis_call(
            "mark_task_running_sadd",
            self.redis.sadd,
            self.running_key,
            task_id,
        )
        task_key = self._task_key(task_id)
        task_mapping: dict[str, Any] = {"status": TaskStatus.RUNNING}
        if cancel_lock:
            task_mapping.update(
                {
                    "cancel_locked": 1,
                    "cancel_locked_at": time.time(),
                    "execution_phase": "preparing",
                    "cancel_requested": 0,
                    "cancel_requested_at": "",
                }
            )
        await self._retry_redis_call(
            "mark_task_running_hset",
            self.redis.hset,
            task_key,
            mapping=task_mapping,
        )
        # Initialize heartbeat to prevent immediate zombie detection
        await self.update_task_heartbeat(task_id)

    async def complete_task(
        self,
        task_id: str,
        result_path: str,
        *,
        extra_outputs: dict[str, Any] | None = None,
        result_kind: str | None = None,
        result_text: str | None = None,
        result_meta: dict[str, Any] | None = None,
    ):
        await complete_task_flow(
            task_id=task_id,
            result_path=result_path,
            extra_outputs=extra_outputs,
            result_kind=result_kind,
            result_text=result_text,
            result_meta=result_meta,
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

    async def update_task_runtime_metadata(
        self,
        task_id: str,
        *,
        progress: float | None = None,
        execution_phase: str | None = None,
        cancel_locked: bool | None = None,
    ) -> None:
        task_mapping: dict[str, Any] = {}
        event_payload: dict[str, Any] = {"status": "running"}
        if progress is not None:
            task_mapping["progress"] = progress
            event_payload["progress"] = progress
        if execution_phase is not None:
            task_mapping["execution_phase"] = execution_phase
            event_payload["execution_phase"] = execution_phase
        if cancel_locked is not None:
            task_mapping["cancel_locked"] = 1 if cancel_locked else 0
            event_payload["cancel_locked"] = cancel_locked
        if not task_mapping:
            return
        await self._persist_task_update(
            task_id,
            task_mapping=task_mapping,
            event_payload=event_payload,
        )

    async def cancel_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        return await cancel_task_flow(
            task_id=task_id,
            task_key=self._task_key(task_id),
            exists_func=lambda *args, **kwargs: self._retry_redis_call(
                "cancel_task_exists",
                self.redis.exists,
                *args,
                **kwargs,
            ),
            zrem_func=lambda task_id: self._retry_redis_call(
                "cancel_task_zrem",
                self.redis.zrem,
                self.pending_key,
                task_id,
            ),
            cancel_pending_task_func=self._cancel_pending_task,
            request_running_task_cancellation_func=(
                self._request_running_task_cancellation
            ),
            sismember_func=lambda task_id: self._retry_redis_call(
                "cancel_task_sismember",
                self.redis.sismember,
                self.running_key,
                task_id,
            ),
            get_task_status_func=self.get_task_status,
            build_cancel_result_func=self._build_cancel_result,
            cancelled_status=TaskStatus.CANCELLED,
        )

    async def cancel_running_task(self, task_id: str) -> Dict[str, Any]:
        return await self._cancel_running_task(task_id)

    async def get_queue_position(self, task_id: str) -> Optional[int]:
        return await self._retry_redis_call(
            "get_queue_position",
            self.redis.zrank,
            self.pending_key,
            task_id,
        )

    async def get_queue_position_by_type(self, task_id: str) -> Optional[int]:
        global_pos = await self.get_queue_position(task_id)
        if global_pos is None:
            return None

        target_task_type = await self._get_task_type(task_id)
        if not target_task_type:
            return None

        pending_task_ids = await self._retry_redis_call(
            "get_queue_position_by_type_zrange",
            self.redis.zrange,
            self.pending_key,
            0,
            global_pos,
        )
        pending_task_types = await self._fetch_pending_task_types(pending_task_ids)

        type_position = 0
        for pending_task_id, pending_task_type in zip(pending_task_ids, pending_task_types):
            pending_task_id = self._decode_redis_value(pending_task_id)
            if pending_task_id == task_id:
                return type_position
            if (
                pending_task_type
                and self._decode_redis_value(pending_task_type) == target_task_type
            ):
                type_position += 1
        return None

    async def get_queue_size(self) -> int:
        return await self._retry_redis_call(
            "get_queue_size",
            self.redis.zcard,
            self.pending_key,
        )

    async def get_active_workers_count(self) -> int:
        return await get_active_workers_count_flow(
            scan_agent_heartbeat_keys_func=self._scan_agent_heartbeat_keys,
        )

    async def get_all_workers(self) -> list[Dict[str, Any]]:
        return await get_all_workers_flow(
            scan_agent_heartbeat_keys_func=self._scan_agent_heartbeat_keys,
            decode_redis_value_func=self._decode_redis_value,
            agent_heartbeat_prefix=self.agent_heartbeat_prefix,
            hgetall_func=lambda *args, **kwargs: self._retry_redis_call(
                "get_all_workers_hgetall",
                self.redis.hgetall,
                *args,
                **kwargs,
            ),
            build_worker_info_func=self._build_worker_info,
        )

    async def update_task_heartbeat(self, task_id: str):
        await self._retry_redis_call(
            "update_task_heartbeat",
            self.redis.setex,
            self._task_heartbeat_key(task_id),
            300,
            "1",
        )  # Expire after 5 mins

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
        metadata: dict[str, Any] | None = None,
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
            metadata=metadata,
            agent_heartbeat_key_func=self._agent_heartbeat_key,
            hset_func=lambda *args, **kwargs: self._retry_redis_call(
                "update_agent_heartbeat_hset",
                self.redis.hset,
                *args,
                **kwargs,
            ),
            expire_func=lambda *args, **kwargs: self._retry_redis_call(
                "update_agent_heartbeat_expire",
                self.redis.expire,
                *args,
                **kwargs,
            ),
        )

    async def get_agent_control_state(self, agent_id: str) -> dict[str, Any]:
        data = self._decode_redis_dict(
            await self._retry_redis_call(
                "get_agent_control_state",
                self.redis.hgetall,
                self._agent_control_key(agent_id),
            )
        )
        state = str(data.get("state") or "enabled").strip().lower()
        if state not in {"enabled", "draining", "disabled"}:
            state = "enabled"
        data["state"] = state
        return data

    async def set_agent_control_state(
        self,
        agent_id: str,
        state: str,
        *,
        reason: str = "",
        ttl_seconds: int | None = None,
    ) -> dict[str, Any]:
        normalized_state = state.strip().lower()
        if normalized_state not in {"enabled", "draining", "disabled"}:
            raise ValueError("agent control state must be enabled, draining, or disabled")
        key = self._agent_control_key(agent_id)
        if normalized_state == "enabled":
            await self._retry_redis_call(
                "set_agent_control_enabled",
                self.redis.hdel,
                key,
                "state",
                "reason",
                "updated_at",
            )
            return {"agent_id": agent_id, "state": "enabled", "reason": ""}
        payload = {
            "state": normalized_state,
            "reason": reason,
            "updated_at": time.time(),
        }
        await self._retry_redis_call(
            "set_agent_control_hset",
            self.redis.hset,
            key,
            mapping=payload,
        )
        if ttl_seconds:
            await self._retry_redis_call(
                "set_agent_control_expire",
                self.redis.expire,
                key,
                ttl_seconds,
            )
        return {"agent_id": agent_id, **payload}

    async def is_agent_pop_enabled(self, agent_id: str) -> tuple[bool, str]:
        control = await self.get_agent_control_state(agent_id)
        state = control.get("state")
        if state in {"draining", "disabled"}:
            return False, str(control.get("reason") or state)
        return True, ""

    async def bind_agent_task(self, task_id: str, agent_id: str):
        await self.record_task_worker(task_id, agent_id)
        await self._retry_redis_call(
            "bind_agent_task",
            self.redis.hset,
            self._agent_heartbeat_key(agent_id),
            "current_task_id",
            task_id,
        )
        await self._retry_redis_call(
            "confirm_agent_task_delivery",
            self.redis.hdel,
            self._task_key(task_id),
            "claim_delivery_pending",
        )

    async def reserve_agent_task_delivery(self, task_id: str, agent_id: str):
        await self.record_task_worker(task_id, agent_id)
        await self._retry_redis_call(
            "reserve_agent_task_delivery",
            self.redis.hset,
            self._agent_heartbeat_key(agent_id),
            "current_task_id",
            task_id,
        )
        await self._retry_redis_call(
            "mark_agent_task_delivery_pending",
            self.redis.hset,
            self._task_key(task_id),
            "claim_delivery_pending",
            1,
        )

    async def get_agent_current_task_id(self, agent_id: str) -> str | None:
        current_task_id = await self._retry_redis_call(
            "get_agent_current_task_id",
            self.redis.hget,
            self._agent_heartbeat_key(agent_id),
            "current_task_id",
        )
        if current_task_id in (None, "", b""):
            return None
        return str(self._decode_redis_value(current_task_id))

    async def get_pending_agent_task_claim(self, agent_id: str) -> str | None:
        current_task_id = await self.get_agent_current_task_id(agent_id)
        if not current_task_id:
            return None
        delivery_pending = await self._retry_redis_call(
            "get_pending_agent_task_claim",
            self.redis.hget,
            self._task_key(current_task_id),
            "claim_delivery_pending",
        )
        return current_task_id if self._as_bool(delivery_pending) else None

    async def record_task_worker(self, task_id: str, agent_id: str):
        await self._retry_redis_call(
            "record_task_worker",
            self.redis.hset,
            self._task_key(task_id),
            "worker_id",
            agent_id,
        )

    async def clear_agent_current_task(
        self,
        agent_id: str,
        *,
        task_id: str | None = None,
    ):
        key = self._agent_heartbeat_key(agent_id)
        if task_id is not None:
            current_task_id = self._decode_redis_value(
                await self._retry_redis_call(
                    "clear_agent_current_task_hget",
                    self.redis.hget,
                    key,
                    "current_task_id",
                )
            )
            if current_task_id != task_id:
                return
        await self._retry_redis_call(
            "clear_agent_current_task_hdel",
            self.redis.hdel,
            key,
            "current_task_id",
        )

    async def get_queue_metrics_by_type(self) -> Dict[str, int]:
        return await get_queue_metrics_by_type_flow(
            zrange_func=lambda *args, **kwargs: self._retry_redis_call(
                "get_queue_metrics_by_type_zrange",
                self.redis.zrange,
                *args,
                **kwargs,
            ),
            pending_key=self.pending_key,
            initialize_type_counts_func=self._initialize_type_counts,
            fetch_pending_task_types_func=self._fetch_pending_task_types,
            accumulate_type_counts_func=self._accumulate_type_counts,
        )

    async def get_queue_metrics_by_type_details(self) -> dict[str, dict[str, Any]]:
        async def fetch_pending_task_details():
            task_ids = await self.redis.zrange(self.pending_key, 0, -1)
            if not task_ids:
                return [], []

            pipeline = self.redis.pipeline()
            for task_id in task_ids:
                task_id_str = self._decode_redis_value(task_id)
                task_key = self._task_key(task_id_str)
                pipeline.hget(task_key, "type")
                pipeline.hget(task_key, "created_at")
            return task_ids, await pipeline.execute()

        task_ids, values = await self._retry_redis_call(
            "get_queue_metrics_by_type_details",
            fetch_pending_task_details,
        )
        if not task_ids:
            return {}

        now = time.time()
        details: dict[str, dict[str, Any]] = {}
        for index, _task_id in enumerate(task_ids):
            task_type = self._task_type_key(values[index * 2])
            created_at = self._safe_int(self._decode_redis_value(values[index * 2 + 1]))
            if not task_type or created_at is None:
                continue

            wait_seconds = max(0, int(now - created_at))
            detail = details.setdefault(task_type, self._empty_queue_metrics_detail())
            detail["pending_count"] += 1
            self._update_wait_max(detail, "max_pending_wait_seconds", wait_seconds)

        return details
