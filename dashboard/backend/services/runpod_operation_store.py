from __future__ import annotations

import json
import os
from copy import deepcopy
from typing import Any, Protocol


OPERATIONS_ZSET_KEY = "dashboard:runpod:operations"
OPERATION_KEY_PREFIX = "dashboard:runpod:operation:"
ACTIVE_ADD_KEY_PREFIX = "dashboard:runpod:active_add:"
MANUAL_ADD_SLOTS_KEY_PREFIX = "dashboard:runpod:manual_add_slots:"
ACTIVE_LAN_AIO_SLOT_KEY_PREFIX = "dashboard:runpod:active_lan_aio_slot:"
LOCKED_RUNPOD_WORKERS_KEY = "dashboard:runpod:locked_workers"
FINISHED_OPERATION_TTL_SECONDS = 24 * 60 * 60


class RunPodOperationStore(Protocol):
    async def save_operation(
        self,
        payload: dict[str, Any],
        *,
        created_at: float,
        ttl_seconds: int | None = None,
    ) -> None: ...

    async def get_operation(self, operation_id: str) -> dict[str, Any] | None: ...

    async def list_operations(self, *, limit: int) -> list[dict[str, Any]]: ...

    async def prune_operations(self, *, max_records: int) -> None: ...

    async def acquire_active_add(self, profile: str, operation_id: str) -> bool: ...

    async def get_active_add(self, profile: str) -> str | None: ...

    async def release_active_add(self, profile: str, operation_id: str) -> None: ...

    async def reserve_manual_add_slots(
        self, profile: str, reservations: dict[str, str]
    ) -> bool: ...

    async def list_manual_add_slots(self, profile: str) -> dict[str, str]: ...

    async def release_manual_add_slot(
        self, profile: str, slot: str, operation_id: str
    ) -> None: ...

    async def acquire_active_lan_aio_slot(
        self,
        physical_slot_key: str,
        operation_id: str,
    ) -> bool: ...

    async def get_active_lan_aio_slot(self, physical_slot_key: str) -> str | None: ...

    async def release_active_lan_aio_slot(
        self,
        physical_slot_key: str,
        operation_id: str,
    ) -> None: ...

    async def set_locked_runpod_worker(
        self,
        agent_id: str,
        payload: dict[str, Any],
    ) -> None: ...

    async def get_locked_runpod_worker(
        self,
        agent_id: str,
    ) -> dict[str, Any] | None: ...

    async def list_locked_runpod_workers(self) -> dict[str, dict[str, Any]]: ...

    async def clear_locked_runpod_worker(self, agent_id: str) -> None: ...


class InMemoryRunPodOperationStore:
    def __init__(self) -> None:
        self.operations: dict[str, dict[str, Any]] = {}
        self.scores: dict[str, float] = {}
        self.active_add: dict[str, str] = {}
        self.manual_add_slots: dict[str, dict[str, str]] = {}
        self.active_lan_aio_slot: dict[str, str] = {}
        self.locked_runpod_workers: dict[str, dict[str, Any]] = {}

    async def save_operation(
        self,
        payload: dict[str, Any],
        *,
        created_at: float,
        ttl_seconds: int | None = None,
    ) -> None:
        del ttl_seconds
        operation_id = str(payload["id"])
        self.operations[operation_id] = deepcopy(payload)
        self.scores[operation_id] = float(created_at)

    async def get_operation(self, operation_id: str) -> dict[str, Any] | None:
        payload = self.operations.get(operation_id)
        return deepcopy(payload) if payload is not None else None

    async def list_operations(self, *, limit: int) -> list[dict[str, Any]]:
        operation_ids = sorted(
            self.scores,
            key=lambda operation_id: self.scores[operation_id],
            reverse=True,
        )
        if limit > 0:
            operation_ids = operation_ids[:limit]
        return [deepcopy(self.operations[item]) for item in operation_ids]

    async def prune_operations(self, *, max_records: int) -> None:
        if max_records <= 0 or len(self.scores) <= max_records:
            return
        operation_ids = sorted(self.scores, key=lambda item: self.scores[item])
        for operation_id in operation_ids[: len(self.scores) - max_records]:
            self.operations.pop(operation_id, None)
            self.scores.pop(operation_id, None)

    async def acquire_active_add(self, profile: str, operation_id: str) -> bool:
        if profile in self.active_add or self.manual_add_slots.get(profile):
            return False
        self.active_add[profile] = operation_id
        return True

    async def get_active_add(self, profile: str) -> str | None:
        return self.active_add.get(profile)

    async def release_active_add(self, profile: str, operation_id: str) -> None:
        if self.active_add.get(profile) == operation_id:
            self.active_add.pop(profile, None)

    async def reserve_manual_add_slots(
        self, profile: str, reservations: dict[str, str]
    ) -> bool:
        if not reservations or profile in self.active_add:
            return False
        active = self.manual_add_slots.setdefault(profile, {})
        if any(slot in active for slot in reservations):
            return False
        active.update(
            {
                str(slot): str(operation_id)
                for slot, operation_id in reservations.items()
            }
        )
        return True

    async def list_manual_add_slots(self, profile: str) -> dict[str, str]:
        return deepcopy(self.manual_add_slots.get(profile, {}))

    async def release_manual_add_slot(
        self, profile: str, slot: str, operation_id: str
    ) -> None:
        active = self.manual_add_slots.get(profile)
        if active and active.get(str(slot)) == str(operation_id):
            active.pop(str(slot), None)
            if not active:
                self.manual_add_slots.pop(profile, None)

    async def acquire_active_lan_aio_slot(
        self,
        physical_slot_key: str,
        operation_id: str,
    ) -> bool:
        if physical_slot_key in self.active_lan_aio_slot:
            return False
        self.active_lan_aio_slot[physical_slot_key] = operation_id
        return True

    async def get_active_lan_aio_slot(self, physical_slot_key: str) -> str | None:
        return self.active_lan_aio_slot.get(physical_slot_key)

    async def release_active_lan_aio_slot(
        self,
        physical_slot_key: str,
        operation_id: str,
    ) -> None:
        if self.active_lan_aio_slot.get(physical_slot_key) == operation_id:
            self.active_lan_aio_slot.pop(physical_slot_key, None)

    async def set_locked_runpod_worker(
        self,
        agent_id: str,
        payload: dict[str, Any],
    ) -> None:
        self.locked_runpod_workers[str(agent_id)] = deepcopy(payload)

    async def get_locked_runpod_worker(
        self,
        agent_id: str,
    ) -> dict[str, Any] | None:
        payload = self.locked_runpod_workers.get(str(agent_id))
        return deepcopy(payload) if payload is not None else None

    async def list_locked_runpod_workers(self) -> dict[str, dict[str, Any]]:
        return deepcopy(self.locked_runpod_workers)

    async def clear_locked_runpod_worker(self, agent_id: str) -> None:
        self.locked_runpod_workers.pop(str(agent_id), None)


class RedisRunPodOperationStore:
    def __init__(self, redis_client) -> None:
        self.redis = redis_client

    @staticmethod
    def operation_key(operation_id: str) -> str:
        return f"{OPERATION_KEY_PREFIX}{operation_id}"

    @staticmethod
    def active_add_key(profile: str) -> str:
        return f"{ACTIVE_ADD_KEY_PREFIX}{profile}"

    @staticmethod
    def manual_add_slots_key(profile: str) -> str:
        return f"{MANUAL_ADD_SLOTS_KEY_PREFIX}{profile}"

    @staticmethod
    def active_lan_aio_slot_key(physical_slot_key: str) -> str:
        return f"{ACTIVE_LAN_AIO_SLOT_KEY_PREFIX}{physical_slot_key}"

    async def save_operation(
        self,
        payload: dict[str, Any],
        *,
        created_at: float,
        ttl_seconds: int | None = None,
    ) -> None:
        operation_id = str(payload["id"])
        key = self.operation_key(operation_id)
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.set(key, encoded)
            if ttl_seconds is not None:
                pipe.expire(key, ttl_seconds)
            else:
                pipe.persist(key)
            pipe.zadd(OPERATIONS_ZSET_KEY, {operation_id: float(created_at)})
            await pipe.execute()

    async def get_operation(self, operation_id: str) -> dict[str, Any] | None:
        raw = await self.redis.get(self.operation_key(operation_id))
        if not raw:
            return None
        return json.loads(raw)

    async def list_operations(self, *, limit: int) -> list[dict[str, Any]]:
        stop = max(0, limit - 1) if limit > 0 else -1
        operation_ids = await self.redis.zrevrange(OPERATIONS_ZSET_KEY, 0, stop)
        operations: list[dict[str, Any]] = []
        stale_ids: list[str] = []
        for operation_id in operation_ids:
            payload = await self.get_operation(str(operation_id))
            if payload is None:
                stale_ids.append(str(operation_id))
                continue
            operations.append(payload)
        if stale_ids:
            await self.redis.zrem(OPERATIONS_ZSET_KEY, *stale_ids)
        return operations

    async def prune_operations(self, *, max_records: int) -> None:
        if max_records <= 0:
            return
        count = await self.redis.zcard(OPERATIONS_ZSET_KEY)
        overflow = int(count) - int(max_records)
        if overflow <= 0:
            return
        operation_ids = await self.redis.zrange(OPERATIONS_ZSET_KEY, 0, overflow - 1)
        if not operation_ids:
            return
        keys = [self.operation_key(str(operation_id)) for operation_id in operation_ids]
        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.delete(*keys)
            pipe.zrem(OPERATIONS_ZSET_KEY, *operation_ids)
            await pipe.execute()

    async def acquire_active_add(self, profile: str, operation_id: str) -> bool:
        script = """
if redis.call("hlen", KEYS[2]) > 0 then
    return 0
end
return redis.call("set", KEYS[1], ARGV[1], "NX") and 1 or 0
"""
        return bool(
            await self.redis.eval(
                script,
                2,
                self.active_add_key(profile),
                self.manual_add_slots_key(profile),
                operation_id,
            )
        )

    async def get_active_add(self, profile: str) -> str | None:
        value = await self.redis.get(self.active_add_key(profile))
        return str(value) if value else None

    async def release_active_add(self, profile: str, operation_id: str) -> None:
        script = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
end
return 0
"""
        await self.redis.eval(script, 1, self.active_add_key(profile), operation_id)

    async def reserve_manual_add_slots(
        self, profile: str, reservations: dict[str, str]
    ) -> bool:
        if not reservations:
            return False
        slots = list(reservations)
        values = [str(reservations[slot]) for slot in slots]
        script = """
if redis.call("exists", KEYS[1]) == 1 then
    return 0
end
for index = 1, #ARGV, 2 do
    if redis.call("hexists", KEYS[2], ARGV[index]) == 1 then
        return 0
    end
end
for index = 1, #ARGV, 2 do
    redis.call("hset", KEYS[2], ARGV[index], ARGV[index + 1])
end
return 1
"""
        args: list[str] = []
        for slot, operation_id in zip(slots, values):
            args.extend([str(slot), operation_id])
        return bool(
            await self.redis.eval(
                script,
                2,
                self.active_add_key(profile),
                self.manual_add_slots_key(profile),
                *args,
            )
        )

    async def list_manual_add_slots(self, profile: str) -> dict[str, str]:
        payload = await self.redis.hgetall(self.manual_add_slots_key(profile))
        return {str(slot): str(operation_id) for slot, operation_id in payload.items()}

    async def release_manual_add_slot(
        self, profile: str, slot: str, operation_id: str
    ) -> None:
        script = """
if redis.call("hget", KEYS[1], ARGV[1]) == ARGV[2] then
    return redis.call("hdel", KEYS[1], ARGV[1])
end
return 0
"""
        await self.redis.eval(
            script,
            1,
            self.manual_add_slots_key(profile),
            str(slot),
            str(operation_id),
        )

    async def acquire_active_lan_aio_slot(
        self,
        physical_slot_key: str,
        operation_id: str,
    ) -> bool:
        return bool(
            await self.redis.set(
                self.active_lan_aio_slot_key(physical_slot_key),
                operation_id,
                nx=True,
            )
        )

    async def get_active_lan_aio_slot(self, physical_slot_key: str) -> str | None:
        value = await self.redis.get(self.active_lan_aio_slot_key(physical_slot_key))
        return str(value) if value else None

    async def release_active_lan_aio_slot(
        self,
        physical_slot_key: str,
        operation_id: str,
    ) -> None:
        script = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
end
return 0
"""
        await self.redis.eval(
            script,
            1,
            self.active_lan_aio_slot_key(physical_slot_key),
            operation_id,
        )

    async def set_locked_runpod_worker(
        self,
        agent_id: str,
        payload: dict[str, Any],
    ) -> None:
        await self.redis.hset(
            LOCKED_RUNPOD_WORKERS_KEY,
            str(agent_id),
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        )

    async def get_locked_runpod_worker(
        self,
        agent_id: str,
    ) -> dict[str, Any] | None:
        raw = await self.redis.hget(LOCKED_RUNPOD_WORKERS_KEY, str(agent_id))
        if not raw:
            return None
        return json.loads(raw)

    async def list_locked_runpod_workers(self) -> dict[str, dict[str, Any]]:
        raw_items = await self.redis.hgetall(LOCKED_RUNPOD_WORKERS_KEY)
        locked: dict[str, dict[str, Any]] = {}
        stale_agent_ids: list[str] = []
        for agent_id, raw_payload in raw_items.items():
            try:
                payload = json.loads(raw_payload)
            except json.JSONDecodeError:
                stale_agent_ids.append(str(agent_id))
                continue
            if isinstance(payload, dict):
                locked[str(agent_id)] = payload
            else:
                stale_agent_ids.append(str(agent_id))
        if stale_agent_ids:
            await self.redis.hdel(LOCKED_RUNPOD_WORKERS_KEY, *stale_agent_ids)
        return locked

    async def clear_locked_runpod_worker(self, agent_id: str) -> None:
        await self.redis.hdel(LOCKED_RUNPOD_WORKERS_KEY, str(agent_id))


def build_default_runpod_operation_store() -> RunPodOperationStore:
    store_mode = os.getenv("DASHBOARD_RUNPOD_OPERATION_STORE", "").strip().lower()
    if store_mode == "memory":
        return InMemoryRunPodOperationStore()

    redis_url = (
        os.getenv("DASHBOARD_RUNPOD_OPERATION_REDIS_URL")
        or os.getenv("REDIS_URL")
        or os.getenv("WORKER_REDIS_URL")
    )
    if not redis_url:
        return InMemoryRunPodOperationStore()

    from src.services.redis_connection import build_redis_client

    redis_client = build_redis_client(redis_url, decode_responses=True)
    return RedisRunPodOperationStore(redis_client)
