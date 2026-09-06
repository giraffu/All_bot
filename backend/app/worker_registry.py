import hashlib
import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Optional

from redis.asyncio import Redis


logger = logging.getLogger(__name__)
RedisCall = Callable[..., Awaitable[Any]]


@dataclass(frozen=True)
class WorkerRegistryConfig:
    task_prefix: str = "comfy:task:"
    heartbeat_prefix: str = "comfy:agent:heartbeat:"
    control_prefix: str = "comfy:agent:control:"
    heartbeat_loss_prefix: str = "comfy:agent:heartbeat_losses:"
    heartbeat_loss_quarantine_threshold: int = 6
    heartbeat_loss_window_seconds: int = 3600
    heartbeat_loss_quarantine_seconds: int = 1800
    outcome_prefix: str = "comfy:worker:outcomes:"
    outcome_retention_seconds: int = 7 * 24 * 60 * 60


class RedisWorkerRegistry:
    """Own Worker heartbeat, control, task binding, and outcome projections."""

    def __init__(
        self,
        redis: Redis,
        *,
        safe_call: RedisCall,
        config: WorkerRegistryConfig,
    ) -> None:
        self._redis = redis
        self._safe_call = safe_call
        self.config = config

    @staticmethod
    def _decode(value: Any) -> Any:
        return value.decode() if isinstance(value, bytes) else value

    @classmethod
    def _decode_dict(cls, data: dict[Any, Any]) -> dict[str, Any]:
        return {
            str(cls._decode(key)): cls._decode(value) for key, value in data.items()
        }

    @staticmethod
    def _as_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in {"1", "true", "yes", "on"}
        return bool(value)

    def heartbeat_key(self, agent_id: str) -> str:
        return f"{self.config.heartbeat_prefix}{agent_id}"

    def control_key(self, agent_id: str) -> str:
        return f"{self.config.control_prefix}{agent_id}"

    def heartbeat_loss_key(self, agent_id: str) -> str:
        return f"{self.config.heartbeat_loss_prefix}{agent_id}"

    def outcome_key(self, agent_id: str) -> str:
        digest = hashlib.sha256(agent_id.encode("utf-8")).hexdigest()
        return f"{self.config.outcome_prefix}{digest}"

    def _task_key(self, task_id: str) -> str:
        return f"{self.config.task_prefix}{task_id}"

    async def _scan_heartbeat_keys(self) -> list[Any]:
        cursor = 0
        keys: list[Any] = []
        pattern = f"{self.config.heartbeat_prefix}*"
        while True:
            cursor, batch = await self._safe_call(
                "worker_registry_scan_heartbeats",
                self._redis.scan,
                cursor,
                match=pattern,
                count=100,
            )
            keys.extend(batch)
            if cursor == 0:
                return keys

    def _build_worker_info(
        self,
        agent_id: str,
        raw_data: dict[Any, Any],
    ) -> Optional[dict[str, Any]]:
        if not raw_data:
            return None

        worker = self._decode_dict(raw_data)
        worker["agent_id"] = agent_id
        if not all(worker.get(field) for field in ("types", "status", "last_seen")):
            return None

        self._normalize_worker_info(worker)
        return worker

    @classmethod
    def _normalize_worker_info(cls, worker: dict[str, Any]) -> None:
        for key in ("last_error_at", "quarantined_until"):
            if key in worker:
                worker[key] = cls._optional_float(worker.get(key))
        if "consecutive_failures" in worker:
            worker["consecutive_failures"] = (
                cls._optional_int(worker.get("consecutive_failures")) or 0
            )
        for key in ("last_error", "health_reason"):
            if key in worker and worker.get(key) is None:
                worker[key] = ""
        if "gpu_index" in worker:
            worker["gpu_index"] = cls._optional_int(worker.get("gpu_index"))
        if "pool_managed" in worker:
            worker["pool_managed"] = str(
                worker.get("pool_managed")
            ).strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
        if "model_bundle_versions" in worker:
            value = worker.get("model_bundle_versions")
            if isinstance(value, str) and value:
                try:
                    parsed = json.loads(value)
                except (TypeError, ValueError):
                    parsed = None
                worker["model_bundle_versions"] = (
                    parsed if isinstance(parsed, dict) else None
                )

    @staticmethod
    def _optional_float(value: Any) -> Optional[float]:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _optional_int(cls, value: Any) -> Optional[int]:
        parsed = cls._optional_float(value)
        return int(parsed) if parsed is not None else None

    async def active_count(self) -> int:
        return len(await self._scan_heartbeat_keys())

    async def all_workers(self) -> list[dict[str, Any]]:
        keys = await self._scan_heartbeat_keys()
        if not keys:
            return []

        async def fetch_heartbeats():
            pipeline = self._redis.pipeline(transaction=False)
            for key in keys:
                pipeline.hgetall(key)
            return await pipeline.execute()

        heartbeat_rows = await self._safe_call(
            "worker_registry_fetch_heartbeats",
            fetch_heartbeats,
        )
        workers: list[dict[str, Any]] = []
        for key, row in zip(keys, heartbeat_rows):
            key_str = str(self._decode(key))
            agent_id = key_str.removeprefix(self.config.heartbeat_prefix)
            worker = self._build_worker_info(agent_id, row)
            if worker:
                workers.append(worker)
        await self._enrich_running_tasks(workers)
        return workers

    async def _enrich_running_tasks(self, workers: list[dict[str, Any]]) -> None:
        running_workers = [
            worker
            for worker in workers
            if worker.get("status") == "running" and worker.get("current_task_id")
        ]
        if not running_workers:
            return

        async def fetch_current_tasks():
            pipeline = self._redis.pipeline(transaction=False)
            for worker in running_workers:
                pipeline.hgetall(self._task_key(str(worker["current_task_id"])))
            return await pipeline.execute()

        task_rows = await self._safe_call(
            "worker_registry_fetch_current_tasks",
            fetch_current_tasks,
        )
        for worker, raw_task in zip(running_workers, task_rows):
            if not raw_task:
                continue
            task = self._decode_dict(raw_task)
            worker["current_task_type"] = task.get("type")
            worker["current_task_progress"] = float(task.get("progress", 0.0))
            worker["current_task_created_at"] = float(task.get("created_at", 0.0))

    async def update_heartbeat(
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
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        payload: dict[str, Any] = {
            "types": types,
            "status": status,
            "last_seen": time.time(),
            "health_reason": health_reason or "",
            "last_error": last_error or "",
            "last_error_at": last_error_at or "",
            "consecutive_failures": consecutive_failures or 0,
            "quarantined_until": quarantined_until or "",
        }
        allowed_metadata = {
            "node_id",
            "provider",
            "gpu_index",
            "runtime_profile",
            "image_ref",
            "model_bundle_versions",
            "pool_managed",
        }
        payload.update(
            {
                key: value
                for key, value in (metadata or {}).items()
                if key in allowed_metadata and value not in (None, "")
            }
        )
        key = self.heartbeat_key(agent_id)
        await self._safe_call(
            "worker_registry_update_heartbeat",
            self._redis.hset,
            key,
            mapping=payload,
        )
        await self._safe_call(
            "worker_registry_expire_heartbeat",
            self._redis.expire,
            key,
            30,
        )

    async def get_control(self, agent_id: str) -> dict[str, Any]:
        data = self._decode_dict(
            await self._safe_call(
                "worker_registry_get_control",
                self._redis.hgetall,
                self.control_key(agent_id),
            )
        )
        state = str(data.get("state") or "enabled").strip().lower()
        data["state"] = (
            state if state in {"enabled", "draining", "disabled"} else "enabled"
        )
        return data

    async def set_control(
        self,
        agent_id: str,
        state: str,
        *,
        reason: str = "",
        ttl_seconds: Optional[int] = None,
    ) -> dict[str, Any]:
        normalized_state = state.strip().lower()
        if normalized_state not in {"enabled", "draining", "disabled"}:
            raise ValueError(
                "agent control state must be enabled, draining, or disabled"
            )
        key = self.control_key(agent_id)
        if normalized_state == "enabled":
            await self._safe_call(
                "worker_registry_enable",
                self._redis.hdel,
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
        await self._safe_call(
            "worker_registry_set_control",
            self._redis.hset,
            key,
            mapping=payload,
        )
        if ttl_seconds:
            await self._safe_call(
                "worker_registry_expire_control",
                self._redis.expire,
                key,
                ttl_seconds,
            )
        return {"agent_id": agent_id, **payload}

    async def pop_enabled(self, agent_id: str) -> tuple[bool, str]:
        control = await self.get_control(agent_id)
        state = control.get("state")
        if state in {"draining", "disabled"}:
            return False, str(control.get("reason") or state)
        return True, ""

    async def record_heartbeat_loss(self, agent_id: str) -> int:
        key = self.heartbeat_loss_key(agent_id)
        count = int(
            await self._safe_call(
                "worker_registry_record_heartbeat_loss",
                self._redis.incr,
                key,
            )
        )
        await self._safe_call(
            "worker_registry_expire_heartbeat_losses",
            self._redis.expire,
            key,
            self.config.heartbeat_loss_window_seconds,
        )
        if count < self.config.heartbeat_loss_quarantine_threshold:
            return count

        control = await self.get_control(agent_id)
        if control.get("state") == "enabled":
            await self.set_control(
                agent_id,
                "disabled",
                reason="automatic quarantine after repeated task heartbeat loss",
                ttl_seconds=self.config.heartbeat_loss_quarantine_seconds,
            )
            logger.error(
                "Automatically quarantined agent %s after %s task heartbeat losses",
                agent_id,
                count,
            )
        return count

    async def record_task_worker(self, task_id: str, agent_id: str) -> None:
        await self._safe_call(
            "worker_registry_record_task_worker",
            self._redis.hset,
            self._task_key(task_id),
            "worker_id",
            agent_id,
        )

    async def bind_task(self, task_id: str, agent_id: str) -> None:
        await self.record_task_worker(task_id, agent_id)
        await self._safe_call(
            "worker_registry_bind_task",
            self._redis.hset,
            self.heartbeat_key(agent_id),
            "current_task_id",
            task_id,
        )
        await self._safe_call(
            "worker_registry_confirm_task_delivery",
            self._redis.hdel,
            self._task_key(task_id),
            "claim_delivery_pending",
        )

    async def reserve_task_delivery(self, task_id: str, agent_id: str) -> None:
        await self.record_task_worker(task_id, agent_id)
        await self._safe_call(
            "worker_registry_reserve_task_delivery",
            self._redis.hset,
            self.heartbeat_key(agent_id),
            "current_task_id",
            task_id,
        )
        await self._safe_call(
            "worker_registry_mark_delivery_pending",
            self._redis.hset,
            self._task_key(task_id),
            "claim_delivery_pending",
            1,
        )

    async def current_task_id(self, agent_id: str) -> Optional[str]:
        task_id = await self._safe_call(
            "worker_registry_get_current_task",
            self._redis.hget,
            self.heartbeat_key(agent_id),
            "current_task_id",
        )
        if task_id in (None, "", b""):
            return None
        return str(self._decode(task_id))

    async def pending_task_claim(self, agent_id: str) -> Optional[str]:
        task_id = await self.current_task_id(agent_id)
        if not task_id:
            return None
        delivery_pending = await self._safe_call(
            "worker_registry_get_pending_claim",
            self._redis.hget,
            self._task_key(task_id),
            "claim_delivery_pending",
        )
        return task_id if self._as_bool(delivery_pending) else None

    async def clear_current_task(
        self,
        agent_id: str,
        *,
        task_id: Optional[str] = None,
    ) -> None:
        key = self.heartbeat_key(agent_id)
        if task_id is not None:
            current_task_id = self._decode(
                await self._safe_call(
                    "worker_registry_compare_current_task",
                    self._redis.hget,
                    key,
                    "current_task_id",
                )
            )
            if current_task_id != task_id:
                return
        await self._safe_call(
            "worker_registry_clear_current_task",
            self._redis.hdel,
            key,
            "current_task_id",
        )

    async def record_outcome(
        self,
        *,
        task_id: str,
        event_payload: dict[str, Any],
    ) -> None:
        worker_id = str(event_payload.get("worker_id") or "").strip()
        status = str(event_payload.get("status") or "").strip()
        if not worker_id or status not in {"done", "error"}:
            return

        observed_at = time.time()
        raw_task_type = event_payload.get("task_type") or "unknown"
        task_type = str(getattr(raw_task_type, "value", raw_task_type))
        member = json.dumps(
            {"task_id": task_id, "status": status, "task_type": task_type},
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        try:
            await self._safe_call(
                "worker_registry_record_outcome",
                self._redis.zadd,
                self.outcome_key(worker_id),
                {member: observed_at},
            )
            await self._safe_call(
                "worker_registry_prune_outcomes",
                self._redis.zremrangebyscore,
                self.outcome_key(worker_id),
                "-inf",
                observed_at - self.config.outcome_retention_seconds,
            )
            await self._safe_call(
                "worker_registry_expire_outcomes",
                self._redis.expire,
                self.outcome_key(worker_id),
                self.config.outcome_retention_seconds,
            )
        except Exception:
            logger.exception(
                "Failed to record worker outcome telemetry task_id=%s worker_id=%s",
                task_id,
                worker_id,
            )

    async def active_outcome_stats(
        self,
        *,
        window_seconds: int,
        now: Optional[float] = None,
    ) -> list[dict[str, Any]]:
        window_seconds = max(300, min(int(window_seconds), 24 * 60 * 60))
        observed_at = time.time() if now is None else float(now)
        cutoff = observed_at - window_seconds
        workers = [
            worker
            for worker in await self.all_workers()
            if str(worker.get("agent_id") or "").strip()
        ]
        if not workers:
            return []

        async def fetch_outcome_windows():
            pipeline = self._redis.pipeline(transaction=False)
            for worker in workers:
                pipeline.zrangebyscore(
                    self.outcome_key(str(worker["agent_id"])),
                    cutoff,
                    observed_at,
                    withscores=True,
                )
            return await pipeline.execute()

        outcome_rows = await self._safe_call(
            "worker_registry_get_outcome_windows",
            fetch_outcome_windows,
        )
        return [
            self._summarize_outcomes(worker, rows)
            for worker, rows in zip(workers, outcome_rows)
        ]

    @classmethod
    def _summarize_outcomes(
        cls,
        worker: dict[str, Any],
        rows: list[tuple[Any, Any]],
    ) -> dict[str, Any]:
        failed_tasks = 0
        failures_by_type: dict[str, int] = {}
        last_failure_at: Optional[float] = None
        valid_rows = 0
        for raw_member, raw_score in rows:
            try:
                payload = json.loads(str(cls._decode(raw_member)))
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            valid_rows += 1
            if payload.get("status") != "error":
                continue
            failed_tasks += 1
            task_type = str(payload.get("task_type") or "unknown")
            failures_by_type[task_type] = failures_by_type.get(task_type, 0) + 1
            score = float(raw_score)
            if last_failure_at is None or score > last_failure_at:
                last_failure_at = score
        return {
            "worker_id": str(worker.get("agent_id") or "").strip(),
            "status": str(worker.get("status") or "unknown"),
            "total_tasks": valid_rows,
            "failed_tasks": failed_tasks,
            "failure_rate": failed_tasks / valid_rows if valid_rows else 0.0,
            "failures_by_type": dict(
                sorted(failures_by_type.items(), key=lambda item: (-item[1], item[0]))
            ),
            "last_failure_at": last_failure_at,
        }
