import time
from collections.abc import Awaitable, Callable
from typing import Any, Optional

from app.models import TaskStatus, TaskType
from redis.asyncio import Redis


RedisCall = Callable[..., Awaitable[Any]]


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


class RedisQueueSelector:
    """Own pending-queue selection and read-only queue projections."""

    def __init__(
        self,
        redis: Redis,
        *,
        pending_key: str,
        task_prefix: str,
        safe_call: RedisCall,
        claim_call: RedisCall,
    ) -> None:
        self._redis = redis
        self._pending_key = pending_key
        self._task_prefix = task_prefix
        self._safe_call = safe_call
        self._claim_call = claim_call

    @staticmethod
    def _decode(value: Any) -> Any:
        return value.decode() if isinstance(value, bytes) else value

    @classmethod
    def _decode_dict(cls, data: dict[Any, Any]) -> dict[str, Any]:
        return {
            str(cls._decode(key)): cls._decode(value) for key, value in data.items()
        }

    def _task_key(self, task_id: str) -> str:
        return f"{self._task_prefix}{task_id}"

    @classmethod
    def _task_type_value(cls, value: Any) -> str:
        value = cls._decode(value)
        if isinstance(value, TaskType):
            return value.value
        return str(value or "").strip()

    async def _get_task_type(self, task_id: str) -> Optional[str]:
        value = await self._safe_call(
            "queue_selector_get_task_type",
            self._redis.hget,
            self._task_key(task_id),
            "type",
        )
        return self._decode(value) if value else None

    async def _fetch_task_types(self, task_ids: list[Any]) -> list[Any]:
        async def execute_pipeline():
            pipeline = self._redis.pipeline(transaction=False)
            for task_id in task_ids:
                pipeline.hget(self._task_key(str(self._decode(task_id))), "type")
            return await pipeline.execute()

        return await self._safe_call(
            "queue_selector_fetch_task_types",
            execute_pipeline,
        )

    async def _fetch_task_details(
        self, task_ids: list[Any]
    ) -> list[Optional[dict[str, Any]]]:
        async def execute_pipeline():
            pipeline = self._redis.pipeline(transaction=False)
            for task_id in task_ids:
                pipeline.hgetall(self._task_key(str(self._decode(task_id))))
            return await pipeline.execute()

        raw_details = await self._safe_call(
            "queue_selector_fetch_task_details",
            execute_pipeline,
        )
        return [
            self._decode_dict(details) if details else None for details in raw_details
        ]

    async def _pop_next(self) -> Optional[tuple[str, float]]:
        result = await self._claim_call(
            "queue_selector_pop_next",
            self._redis.zpopmin,
            self._pending_key,
        )
        if not result:
            return None
        task_id, score = result[0]
        return str(self._decode(task_id)), score

    async def _find_next_allowed(
        self,
        allowed_types: list[str],
        *,
        batch_size: int = 50,
    ) -> Optional[tuple[str, float]]:
        offset = 0
        while True:
            tasks_with_scores = await self._safe_call(
                "queue_selector_find_allowed",
                self._redis.zrange,
                self._pending_key,
                offset,
                offset + batch_size - 1,
                withscores=True,
            )
            if not tasks_with_scores:
                return None

            for task_id_raw, score in tasks_with_scores:
                task_id = str(self._decode(task_id_raw))
                task_type = await self._get_task_type(task_id)
                if not task_type or task_type not in allowed_types:
                    continue

                removed = await self._claim_call(
                    "queue_selector_claim_allowed",
                    self._redis.zrem,
                    self._pending_key,
                    task_id,
                )
                if removed:
                    return task_id, score

            offset += batch_size

    async def _pop_preferred_or_fallback(
        self,
        *,
        allowed_types: list[str],
        preferred_types: list[str],
    ) -> Optional[tuple[str, float]]:
        result = await self._claim_call(
            "queue_selector_pop_preferred_or_fallback",
            self._redis.eval,
            _POP_PREFERRED_TASK_SCRIPT,
            2,
            self._pending_key,
            self._task_prefix,
            len(allowed_types),
            len(preferred_types),
            *allowed_types,
            *preferred_types,
        )
        if not result:
            return None
        task_id, score = result
        return str(self._decode(task_id)), float(score)

    async def select_next(
        self,
        *,
        allowed_types: Optional[list[str]],
        preferred_types: Optional[list[str]],
    ) -> Optional[tuple[str, float]]:
        if preferred_types:
            return await self._pop_preferred_or_fallback(
                allowed_types=list(allowed_types or []),
                preferred_types=preferred_types,
            )
        if allowed_types:
            return await self._find_next_allowed(allowed_types)
        return await self._pop_next()

    async def peek(
        self,
        *,
        allowed_types: Optional[list[str]],
        preferred_types: Optional[list[str]],
        limit: int,
        batch_size: int,
    ) -> list[dict[str, Any]]:
        if limit <= 0:
            return []

        preferred_set = set(preferred_types or [])
        allowed_set = set(allowed_types or [])
        preferred_matches: list[dict[str, Any]] = []
        fallback_matches: list[dict[str, Any]] = []
        offset = 0

        while not preferred_types or len(preferred_matches) < limit:
            tasks_with_scores = await self._safe_call(
                "queue_selector_peek",
                self._redis.zrange,
                self._pending_key,
                offset,
                offset + batch_size - 1,
                withscores=True,
            )
            if not tasks_with_scores:
                break

            task_details_batch = await self._fetch_task_details(
                [task_id for task_id, _score in tasks_with_scores]
            )
            for task_details in task_details_batch:
                if not task_details or task_details.get("status") != TaskStatus.PENDING:
                    continue
                task_type = task_details.get("type")
                if allowed_set and task_type not in allowed_set:
                    continue
                target = (
                    preferred_matches
                    if task_type in preferred_set
                    else fallback_matches
                )
                if len(target) < limit:
                    target.append(task_details)
                if not preferred_types and len(fallback_matches) >= limit:
                    return fallback_matches
            offset += batch_size

        return (preferred_matches + fallback_matches)[:limit]

    async def position(self, task_id: str) -> Optional[int]:
        return await self._safe_call(
            "queue_selector_position",
            self._redis.zrank,
            self._pending_key,
            task_id,
        )

    async def position_by_type(self, task_id: str) -> Optional[int]:
        global_position = await self.position(task_id)
        if global_position is None:
            return None

        target_type = await self._get_task_type(task_id)
        if not target_type:
            return None

        task_ids = await self._safe_call(
            "queue_selector_position_by_type",
            self._redis.zrange,
            self._pending_key,
            0,
            global_position,
        )
        task_types = await self._fetch_task_types(task_ids)
        type_position = 0
        for pending_task_id, pending_task_type in zip(task_ids, task_types):
            if str(self._decode(pending_task_id)) == task_id:
                return type_position
            if pending_task_type and self._decode(pending_task_type) == target_type:
                type_position += 1
        return None

    async def size(self) -> int:
        return await self._safe_call(
            "queue_selector_size",
            self._redis.zcard,
            self._pending_key,
        )

    async def metrics_by_type(self) -> dict[str, int]:
        task_ids = await self._safe_call(
            "queue_selector_metrics_by_type",
            self._redis.zrange,
            self._pending_key,
            0,
            -1,
        )
        counts = {task_type.value: 0 for task_type in TaskType}
        if not task_ids:
            return counts
        for raw_type in await self._fetch_task_types(task_ids):
            if not raw_type:
                continue
            task_type = self._task_type_value(raw_type)
            counts[task_type] = counts.get(task_type, 0) + 1
        return counts

    async def metrics_by_type_details(self) -> dict[str, dict[str, Any]]:
        async def fetch_pending_task_details():
            task_ids = await self._redis.zrange(self._pending_key, 0, -1)
            if not task_ids:
                return [], []

            pipeline = self._redis.pipeline(transaction=False)
            for task_id in task_ids:
                task_key = self._task_key(str(self._decode(task_id)))
                pipeline.hget(task_key, "type")
                pipeline.hget(task_key, "created_at")
            return task_ids, await pipeline.execute()

        task_ids, values = await self._safe_call(
            "queue_selector_metrics_by_type_details",
            fetch_pending_task_details,
        )
        if not task_ids:
            return {}

        now = time.time()
        details: dict[str, dict[str, Any]] = {}
        for index, _task_id in enumerate(task_ids):
            task_type = self._task_type_value(values[index * 2])
            created_at = self._safe_int(self._decode(values[index * 2 + 1]))
            if not task_type or created_at is None:
                continue

            wait_seconds = max(0, int(now - created_at))
            detail = details.setdefault(
                task_type,
                {"pending_count": 0, "max_pending_wait_seconds": None},
            )
            detail["pending_count"] += 1
            current_max = detail["max_pending_wait_seconds"]
            if current_max is None or wait_seconds > current_max:
                detail["max_pending_wait_seconds"] = wait_seconds
        return details

    @staticmethod
    def _safe_int(value: Any) -> Optional[int]:
        if value in (None, ""):
            return None
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None
