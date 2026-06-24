from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import time
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Protocol

from fastapi import HTTPException
import redis.asyncio as redis

from dashboard.backend.services import runpod_admin_service
from dashboard.backend.services.runpod_admin_operation import (
    FINISHED_OPERATION_STATUSES,
    operation_payload,
)
from dashboard.backend.services.system_service import (
    get_system_status_proxy_payload,
    get_system_workers_proxy_payload,
)
from ops.gpu_pool_controller.runpod_profile_catalog import (
    RUNPOD_ADMIN_PROFILE_OPTIONS,
    normalize_prod_worker_profile,
    prod_slot_from_agent_id,
    prod_worker_profile_from_agent_id,
)
from src.core.task_execution_types import resolve_worker_execution_task_type

logger = logging.getLogger("dashboard.runpod.autoscaler")

AUTOSCALER_CONTROL_KEY = "dashboard:runpod:autoscaler:control"
AUTOSCALER_LEADER_KEY = "dashboard:runpod:autoscaler:leader"
AUTOSCALER_LAST_DECISIONS_KEY = "dashboard:runpod:autoscaler:last_decisions"
AUTOSCALER_SETTINGS_KEY = "dashboard:runpod:autoscaler:settings"
AUTOSCALER_SCALE_UP_CONFIRMATIONS_KEY = (
    "dashboard:runpod:autoscaler:scale_up_confirmations"
)
AUTOSCALER_OWNER_ID = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex}"
SCALE_UP_WAIT_MINUTES_MIN = 1
SCALE_UP_WAIT_MINUTES_MAX = 240
SINGLE_OUTLIER_LOW_PRIORITY_MAX = 0


def _runpod_profile_names() -> list[str]:
    return [str(option["profile"]) for option in RUNPOD_ADMIN_PROFILE_OPTIONS]


def _default_scale_up_wait_seconds_by_profile(
    fallback_seconds: int,
) -> dict[str, int]:
    thresholds = {profile: int(fallback_seconds) for profile in _runpod_profile_names()}
    thresholds["img2img"] = 20 * 60
    thresholds["scail2"] = 40 * 60
    return thresholds


def _normalize_scale_up_wait_seconds_by_profile(
    raw: dict[str, Any] | None,
) -> dict[str, int]:
    valid_profiles = set(_runpod_profile_names())
    normalized: dict[str, int] = {}
    for profile, raw_seconds in (raw or {}).items():
        profile_name = str(profile)
        if profile_name not in valid_profiles:
            continue
        try:
            seconds = int(raw_seconds)
        except (TypeError, ValueError):
            continue
        if seconds < SCALE_UP_WAIT_MINUTES_MIN * 60:
            continue
        if seconds > SCALE_UP_WAIT_MINUTES_MAX * 60:
            continue
        normalized[profile_name] = seconds
    return normalized


def _validate_scale_up_wait_minutes_by_profile(
    updates: dict[str, Any] | None,
) -> dict[str, int]:
    if not updates:
        return {}
    valid_profiles = set(_runpod_profile_names())
    normalized: dict[str, int] = {}
    for profile, raw_minutes in updates.items():
        profile_name = str(profile)
        if profile_name not in valid_profiles:
            raise HTTPException(
                status_code=422,
                detail=f"unsupported RunPod profile: {profile_name}",
            )
        try:
            minutes = int(raw_minutes)
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=422,
                detail=f"invalid scale-up threshold minutes for {profile_name}",
            ) from exc
        if (
            minutes < SCALE_UP_WAIT_MINUTES_MIN
            or minutes > SCALE_UP_WAIT_MINUTES_MAX
        ):
            raise HTTPException(
                status_code=422,
                detail=(
                    f"scale-up threshold for {profile_name} must be between "
                    f"{SCALE_UP_WAIT_MINUTES_MIN} and {SCALE_UP_WAIT_MINUTES_MAX} minutes"
                ),
            )
        normalized[profile_name] = minutes * 60
    return normalized


def _normalize_scale_up_confirmation_counts(
    raw: dict[str, Any] | None,
) -> dict[str, int]:
    valid_profiles = set(_runpod_profile_names())
    normalized: dict[str, int] = {}
    for profile, raw_count in (raw or {}).items():
        profile_name = str(profile)
        if profile_name not in valid_profiles:
            continue
        try:
            count = int(raw_count)
        except (TypeError, ValueError):
            continue
        normalized[profile_name] = max(0, count)
    return normalized


def _bool_env(name: str, *, default: bool = False) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _int_env(name: str, *, default: int, minimum: int = 1) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return max(minimum, int(raw))
    except ValueError:
        logger.warning("Invalid integer env %s=%r; using %s", name, raw, default)
        return default


@dataclass(frozen=True)
class RunPodAutoscalerConfig:
    configured_enabled: bool = False
    mode: str = "execute"
    interval_seconds: int = 60
    scale_up_wait_seconds: int = 30 * 60
    scale_up_confirmation_rounds: int = 3
    scale_down_wait_seconds: int = 60
    cooldown_seconds: int = 10 * 60
    max_runpods_per_profile: int = 5
    heartbeat_max_age_seconds: int = 5 * 60
    leader_ttl_seconds: int = 90
    owner_id: str = AUTOSCALER_OWNER_ID
    scale_up_wait_seconds_by_profile: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        merged = _default_scale_up_wait_seconds_by_profile(self.scale_up_wait_seconds)
        merged.update(
            _normalize_scale_up_wait_seconds_by_profile(
                self.scale_up_wait_seconds_by_profile
            )
        )
        object.__setattr__(self, "scale_up_wait_seconds_by_profile", merged)
        object.__setattr__(
            self,
            "scale_up_confirmation_rounds",
            max(1, int(self.scale_up_confirmation_rounds or 1)),
        )

    def scale_up_wait_seconds_for_profile(self, profile: str) -> int:
        return int(
            self.scale_up_wait_seconds_by_profile.get(
                profile,
                self.scale_up_wait_seconds,
            )
        )

    def with_scale_up_wait_seconds_by_profile(
        self,
        thresholds: dict[str, int] | None,
    ) -> "RunPodAutoscalerConfig":
        merged = dict(self.scale_up_wait_seconds_by_profile)
        merged.update(_normalize_scale_up_wait_seconds_by_profile(thresholds))
        return replace(self, scale_up_wait_seconds_by_profile=merged)

    def payload(self) -> dict[str, Any]:
        return {
            "configured_enabled": self.configured_enabled,
            "mode": self.mode,
            "interval_seconds": self.interval_seconds,
            "scale_up_wait_seconds": self.scale_up_wait_seconds,
            "scale_up_confirmation_rounds": self.scale_up_confirmation_rounds,
            "scale_up_wait_seconds_by_profile": dict(
                self.scale_up_wait_seconds_by_profile
            ),
            "scale_down_wait_seconds": self.scale_down_wait_seconds,
            "cooldown_seconds": self.cooldown_seconds,
            "max_runpods_per_profile": self.max_runpods_per_profile,
            "heartbeat_max_age_seconds": self.heartbeat_max_age_seconds,
            "leader_ttl_seconds": self.leader_ttl_seconds,
        }


def config_from_env() -> RunPodAutoscalerConfig:
    mode = os.getenv("DASHBOARD_RUNPOD_AUTOSCALER_MODE", "execute").strip().lower()
    if mode != "execute":
        logger.warning("Unsupported RunPod autoscaler mode %r; using execute", mode)
        mode = "execute"
    return RunPodAutoscalerConfig(
        configured_enabled=_bool_env("DASHBOARD_RUNPOD_AUTOSCALER_ENABLED"),
        mode=mode,
        interval_seconds=_int_env(
            "DASHBOARD_RUNPOD_AUTOSCALER_INTERVAL_SECONDS",
            default=60,
            minimum=10,
        ),
        scale_up_wait_seconds=_int_env(
            "DASHBOARD_RUNPOD_AUTOSCALER_SCALE_UP_WAIT_SECONDS",
            default=30 * 60,
            minimum=1,
        ),
        scale_up_confirmation_rounds=_int_env(
            "DASHBOARD_RUNPOD_AUTOSCALER_SCALE_UP_CONFIRMATION_ROUNDS",
            default=3,
            minimum=1,
        ),
        scale_down_wait_seconds=_int_env(
            "DASHBOARD_RUNPOD_AUTOSCALER_SCALE_DOWN_WAIT_SECONDS",
            default=60,
            minimum=0,
        ),
        cooldown_seconds=_int_env(
            "DASHBOARD_RUNPOD_AUTOSCALER_COOLDOWN_SECONDS",
            default=10 * 60,
            minimum=1,
        ),
        max_runpods_per_profile=_int_env(
            "DASHBOARD_RUNPOD_AUTOSCALER_MAX_RUNPODS_PER_PROFILE",
            default=5,
            minimum=1,
        ),
        heartbeat_max_age_seconds=_int_env(
            "DASHBOARD_RUNPOD_AUTOSCALER_HEARTBEAT_MAX_AGE_SECONDS",
            default=5 * 60,
            minimum=1,
        ),
        leader_ttl_seconds=_int_env(
            "DASHBOARD_RUNPOD_AUTOSCALER_LEADER_TTL_SECONDS",
            default=90,
            minimum=10,
        ),
    )


class RunPodAutoscalerStateStore(Protocol):
    async def get_control_enabled(self, *, default: bool) -> bool:
        ...

    async def set_control_enabled(self, enabled: bool, *, reason: str | None) -> None:
        ...

    async def get_scale_up_wait_seconds_by_profile(self) -> dict[str, int]:
        ...

    async def set_scale_up_wait_seconds_by_profile(
        self,
        thresholds: dict[str, int],
        *,
        reason: str | None,
    ) -> None:
        ...

    async def get_scale_up_confirmation_counts(self) -> dict[str, int]:
        ...

    async def save_scale_up_confirmation_counts(
        self,
        counts: dict[str, int],
    ) -> None:
        ...

    async def acquire_leader(self, owner_id: str, *, ttl_seconds: int) -> bool:
        ...

    async def save_last_decisions(self, payload: dict[str, Any]) -> None:
        ...

    async def get_last_decisions(self) -> dict[str, Any] | None:
        ...


class DisabledRunPodAutoscalerStateStore:
    async def get_control_enabled(self, *, default: bool) -> bool:
        return default

    async def set_control_enabled(self, enabled: bool, *, reason: str | None) -> None:
        del enabled, reason

    async def get_scale_up_wait_seconds_by_profile(self) -> dict[str, int]:
        return {}

    async def set_scale_up_wait_seconds_by_profile(
        self,
        thresholds: dict[str, int],
        *,
        reason: str | None,
    ) -> None:
        del thresholds, reason

    async def get_scale_up_confirmation_counts(self) -> dict[str, int]:
        return {}

    async def save_scale_up_confirmation_counts(
        self,
        counts: dict[str, int],
    ) -> None:
        del counts

    async def acquire_leader(self, owner_id: str, *, ttl_seconds: int) -> bool:
        del owner_id, ttl_seconds
        return False

    async def save_last_decisions(self, payload: dict[str, Any]) -> None:
        del payload

    async def get_last_decisions(self) -> dict[str, Any] | None:
        return None


class InMemoryRunPodAutoscalerStateStore:
    def __init__(self, *, leader_available: bool = True) -> None:
        self.control_enabled: bool | None = None
        self.control_reason: str | None = None
        self.leader_available = leader_available
        self.last_decisions: dict[str, Any] | None = None
        self.scale_up_wait_seconds_by_profile: dict[str, int] = {}
        self.scale_up_confirmation_counts: dict[str, int] = {}
        self.settings_reason: str | None = None

    async def get_control_enabled(self, *, default: bool) -> bool:
        return default if self.control_enabled is None else self.control_enabled

    async def set_control_enabled(self, enabled: bool, *, reason: str | None) -> None:
        self.control_enabled = bool(enabled)
        self.control_reason = reason

    async def get_scale_up_wait_seconds_by_profile(self) -> dict[str, int]:
        return dict(self.scale_up_wait_seconds_by_profile)

    async def set_scale_up_wait_seconds_by_profile(
        self,
        thresholds: dict[str, int],
        *,
        reason: str | None,
    ) -> None:
        self.scale_up_wait_seconds_by_profile.update(
            _normalize_scale_up_wait_seconds_by_profile(thresholds)
        )
        self.settings_reason = reason

    async def get_scale_up_confirmation_counts(self) -> dict[str, int]:
        return dict(self.scale_up_confirmation_counts)

    async def save_scale_up_confirmation_counts(
        self,
        counts: dict[str, int],
    ) -> None:
        self.scale_up_confirmation_counts = _normalize_scale_up_confirmation_counts(
            counts
        )

    async def acquire_leader(self, owner_id: str, *, ttl_seconds: int) -> bool:
        del owner_id, ttl_seconds
        return self.leader_available

    async def save_last_decisions(self, payload: dict[str, Any]) -> None:
        self.last_decisions = json.loads(json.dumps(payload, ensure_ascii=False))

    async def get_last_decisions(self) -> dict[str, Any] | None:
        return self.last_decisions


class RedisRunPodAutoscalerStateStore:
    def __init__(self, redis_client) -> None:
        self.redis = redis_client

    async def get_control_enabled(self, *, default: bool) -> bool:
        raw = await self.redis.get(AUTOSCALER_CONTROL_KEY)
        if not raw:
            return default
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return default
        return bool(payload.get("enabled", default))

    async def set_control_enabled(self, enabled: bool, *, reason: str | None) -> None:
        payload = {
            "enabled": bool(enabled),
            "reason": reason or "",
            "updated_at": time.time(),
            "owner_id": AUTOSCALER_OWNER_ID,
        }
        await self.redis.set(
            AUTOSCALER_CONTROL_KEY,
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        )

    async def get_scale_up_wait_seconds_by_profile(self) -> dict[str, int]:
        raw = await self.redis.get(AUTOSCALER_SETTINGS_KEY)
        if not raw:
            return {}
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return _normalize_scale_up_wait_seconds_by_profile(
            payload.get("scale_up_wait_seconds_by_profile")
        )

    async def set_scale_up_wait_seconds_by_profile(
        self,
        thresholds: dict[str, int],
        *,
        reason: str | None,
    ) -> None:
        current = await self.get_scale_up_wait_seconds_by_profile()
        current.update(_normalize_scale_up_wait_seconds_by_profile(thresholds))
        payload = {
            "scale_up_wait_seconds_by_profile": current,
            "reason": reason or "",
            "updated_at": time.time(),
            "owner_id": AUTOSCALER_OWNER_ID,
        }
        await self.redis.set(
            AUTOSCALER_SETTINGS_KEY,
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        )

    async def get_scale_up_confirmation_counts(self) -> dict[str, int]:
        raw = await self.redis.get(AUTOSCALER_SCALE_UP_CONFIRMATIONS_KEY)
        if not raw:
            return {}
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return _normalize_scale_up_confirmation_counts(payload.get("counts"))

    async def save_scale_up_confirmation_counts(
        self,
        counts: dict[str, int],
    ) -> None:
        payload = {
            "counts": _normalize_scale_up_confirmation_counts(counts),
            "updated_at": time.time(),
            "owner_id": AUTOSCALER_OWNER_ID,
        }
        await self.redis.set(
            AUTOSCALER_SCALE_UP_CONFIRMATIONS_KEY,
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            ex=24 * 60 * 60,
        )

    async def acquire_leader(self, owner_id: str, *, ttl_seconds: int) -> bool:
        current = await self.redis.get(AUTOSCALER_LEADER_KEY)
        if current == owner_id:
            await self.redis.set(AUTOSCALER_LEADER_KEY, owner_id, ex=ttl_seconds)
            return True
        return bool(
            await self.redis.set(
                AUTOSCALER_LEADER_KEY,
                owner_id,
                nx=True,
                ex=ttl_seconds,
            )
        )

    async def save_last_decisions(self, payload: dict[str, Any]) -> None:
        await self.redis.set(
            AUTOSCALER_LAST_DECISIONS_KEY,
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            ex=24 * 60 * 60,
        )

    async def get_last_decisions(self) -> dict[str, Any] | None:
        raw = await self.redis.get(AUTOSCALER_LAST_DECISIONS_KEY)
        if not raw:
            return None
        return json.loads(raw)


def build_default_runpod_autoscaler_state_store() -> RunPodAutoscalerStateStore:
    redis_url = (
        os.getenv("DASHBOARD_RUNPOD_AUTOSCALER_REDIS_URL")
        or os.getenv("DASHBOARD_RUNPOD_OPERATION_REDIS_URL")
        or os.getenv("REDIS_URL")
        or os.getenv("WORKER_REDIS_URL")
    )
    if not redis_url:
        return DisabledRunPodAutoscalerStateStore()
    redis_client = redis.from_url(redis_url, decode_responses=True)
    return RedisRunPodAutoscalerStateStore(redis_client)


_state_store: RunPodAutoscalerStateStore = build_default_runpod_autoscaler_state_store()


def set_runpod_autoscaler_state_store_for_tests(
    store: RunPodAutoscalerStateStore,
) -> None:
    global _state_store
    _state_store = store


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed != parsed:
        return None
    return parsed


def _safe_int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _pending_wait_records(detail: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for raw_record in detail.get("pending_wait_records") or []:
        if not isinstance(raw_record, dict):
            continue
        wait_seconds = _safe_float(raw_record.get("wait_seconds"))
        if wait_seconds is None or wait_seconds < 0:
            continue
        records.append(
            {
                "wait_seconds": wait_seconds,
                "priority": _safe_int_or_none(raw_record.get("priority")),
            }
        )
    return records


def _pending_over_threshold_count(
    detail: dict[str, Any],
    *,
    scale_up_wait_seconds: int,
) -> int:
    records = _pending_wait_records(detail)
    if records:
        return sum(
            1
            for record in records
            if float(record["wait_seconds"]) > scale_up_wait_seconds
        )

    wait_seconds = _safe_float(detail.get("max_pending_wait_seconds"))
    if wait_seconds is None:
        return 0
    return int(wait_seconds > scale_up_wait_seconds)


def _is_single_low_priority_wait_outlier(
    detail: dict[str, Any],
    *,
    scale_up_wait_seconds: int,
) -> bool:
    records = _pending_wait_records(detail)
    if not records:
        return False
    breached_records = [
        record
        for record in records
        if float(record["wait_seconds"]) > scale_up_wait_seconds
    ]
    if len(breached_records) != 1:
        return False
    priority = breached_records[0].get("priority")
    return priority is not None and priority <= SINGLE_OUTLIER_LOW_PRIORITY_MAX


def _parse_operation_time(value: Any) -> float | None:
    if not value:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    raw = str(value)
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _normalized_supported_task_types(raw_task_types: Any) -> list[str]:
    normalized: list[str] = []
    for raw_task_type in raw_task_types or []:
        task_type = resolve_worker_execution_task_type(str(raw_task_type))
        if task_type not in normalized:
            normalized.append(task_type)
    return normalized


def _profile_task_types() -> dict[str, set[str]]:
    return {
        str(option["profile"]): set(
            _normalized_supported_task_types(option.get("supported_task_types"))
        )
        for option in RUNPOD_ADMIN_PROFILE_OPTIONS
    }


def _worker_task_types(worker: dict[str, Any]) -> set[str]:
    raw_types = str(worker.get("types") or "")
    task_types: set[str] = set()
    for raw_type in raw_types.split(","):
        stripped = raw_type.strip()
        if not stripped:
            continue
        task_types.add(resolve_worker_execution_task_type(stripped))
    return task_types


def _runpod_profile_for_worker(worker: dict[str, Any]) -> str | None:
    agent_id = str(worker.get("agent_id") or "")
    try:
        return prod_worker_profile_from_agent_id(agent_id)
    except ValueError:
        pass

    if str(worker.get("provider") or "").strip().lower() != "runpod":
        return None
    try:
        return normalize_prod_worker_profile(str(worker.get("runtime_profile") or ""))
    except ValueError:
        return None


def _worker_seen_recently(
    worker: dict[str, Any],
    *,
    now: float,
    heartbeat_max_age_seconds: int,
) -> bool:
    last_seen = _safe_float(worker.get("last_seen"))
    if last_seen is None:
        return False
    return 0 <= now - last_seen <= heartbeat_max_age_seconds


def _worker_accepting(
    worker: dict[str, Any],
    *,
    now: float,
    heartbeat_max_age_seconds: int,
) -> bool:
    return (
        _worker_seen_recently(
            worker,
            now=now,
            heartbeat_max_age_seconds=heartbeat_max_age_seconds,
        )
        and str(worker.get("status") or "").lower() in {"idle", "running"}
        and str(worker.get("control_state") or "enabled").lower() == "enabled"
    )


def _worker_idle_delete_candidate(
    worker: dict[str, Any],
    *,
    now: float,
    heartbeat_max_age_seconds: int,
) -> bool:
    return (
        _worker_accepting(
            worker,
            now=now,
            heartbeat_max_age_seconds=heartbeat_max_age_seconds,
        )
        and str(worker.get("status") or "").lower() == "idle"
        and not worker.get("current_task_id")
        and not worker.get("current_task_type")
    )


def _worker_supports_profile(
    worker: dict[str, Any],
    *,
    profile: str,
    profile_task_types: dict[str, set[str]],
) -> bool:
    worker_profile = str(worker.get("runtime_profile") or "").strip()
    if worker_profile:
        try:
            if normalize_prod_worker_profile(worker_profile) == profile:
                return True
        except ValueError:
            pass
    return bool(_worker_task_types(worker) & profile_task_types.get(profile, set()))


def _operation_profile(operation: dict[str, Any]) -> str:
    return str(operation.get("profile") or "")


def _operation_active(operation: dict[str, Any]) -> bool:
    return str(operation.get("status") or "") not in FINISHED_OPERATION_STATUSES


def _active_operation_for_profile(
    operations: list[dict[str, Any]],
    *,
    profile: str,
) -> dict[str, Any] | None:
    for operation in operations:
        if _operation_profile(operation) == profile and _operation_active(operation):
            return operation
    return None


def _autoscaler_cooldown_remaining_seconds(
    operations: list[dict[str, Any]],
    *,
    profile: str,
    now: float,
    cooldown_seconds: int,
) -> int:
    latest_ended_at: float | None = None
    for operation in operations:
        if _operation_profile(operation) != profile:
            continue
        if operation.get("source") != "autoscaler":
            continue
        ended_at = _parse_operation_time(operation.get("ended_at"))
        if ended_at is None:
            continue
        if latest_ended_at is None or ended_at > latest_ended_at:
            latest_ended_at = ended_at
    if latest_ended_at is None:
        return 0
    remaining = int(cooldown_seconds - (now - latest_ended_at))
    return max(0, remaining)


def _highest_slot_worker(workers: list[dict[str, Any]], *, profile: str) -> dict[str, Any] | None:
    candidates: list[tuple[int, dict[str, Any]]] = []
    for worker in workers:
        agent_id = str(worker.get("agent_id") or "")
        try:
            slot = prod_slot_from_agent_id(agent_id, profile=profile)
        except ValueError:
            continue
        candidates.append((int(slot), worker))
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]


def _decision(
    *,
    profile: str,
    action: str,
    reason: str,
    metrics: dict[str, Any],
    slot: str | None = None,
    operation_id: str | None = None,
) -> dict[str, Any]:
    payload = {
        "profile": profile,
        "action": action,
        "reason": reason,
        "slot": slot,
        "operation_id": operation_id,
    }
    payload.update(metrics)
    return payload


def build_runpod_autoscaler_decisions(
    *,
    status_payload: dict[str, Any],
    workers_payload: dict[str, Any],
    operations_payload: dict[str, Any],
    config: RunPodAutoscalerConfig,
    now: float,
    scale_up_confirmation_counts: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    queue_details = {
        str(item.get("profile")): item
        for item in status_payload.get("runpod_profile_queue_details") or []
    }
    workers = list(workers_payload.get("workers") or [])
    operations = list(operations_payload.get("operations") or [])
    profile_task_types = _profile_task_types()
    confirmation_counts = _normalize_scale_up_confirmation_counts(
        scale_up_confirmation_counts
    )
    decisions: list[dict[str, Any]] = []

    for option in RUNPOD_ADMIN_PROFILE_OPTIONS:
        profile = str(option["profile"])
        detail = queue_details.get(profile) or {}
        pending_count = int(detail.get("pending_count") or 0)
        active_count = int(detail.get("active_count") or 0)
        wait_seconds = _safe_float(detail.get("max_pending_wait_seconds"))
        scale_up_wait_seconds = config.scale_up_wait_seconds_for_profile(profile)
        pending_over_threshold_count = _pending_over_threshold_count(
            detail,
            scale_up_wait_seconds=scale_up_wait_seconds,
        )

        profile_runpod_workers: list[dict[str, Any]] = []
        profile_local_workers: list[dict[str, Any]] = []
        idle_runpod_workers: list[dict[str, Any]] = []
        accepting_runpod_count = 0
        accepting_local_count = 0
        runpod_total_count = 0

        for worker in workers:
            runpod_profile = _runpod_profile_for_worker(worker)
            is_runpod = runpod_profile == profile
            supports_profile = _worker_supports_profile(
                worker,
                profile=profile,
                profile_task_types=profile_task_types,
            )
            if not is_runpod and not supports_profile:
                continue
            accepting = _worker_accepting(
                worker,
                now=now,
                heartbeat_max_age_seconds=config.heartbeat_max_age_seconds,
            )
            if is_runpod:
                profile_runpod_workers.append(worker)
                if _worker_seen_recently(
                    worker,
                    now=now,
                    heartbeat_max_age_seconds=config.heartbeat_max_age_seconds,
                ):
                    runpod_total_count += 1
                if accepting:
                    accepting_runpod_count += 1
                if _worker_idle_delete_candidate(
                    worker,
                    now=now,
                    heartbeat_max_age_seconds=config.heartbeat_max_age_seconds,
                ):
                    idle_runpod_workers.append(worker)
            else:
                profile_local_workers.append(worker)
                if accepting:
                    accepting_local_count += 1

        total_accepting_count = accepting_runpod_count + accepting_local_count
        metrics = {
            "active_count": active_count,
            "pending_count": pending_count,
            "max_pending_wait_seconds": wait_seconds,
            "runpod_count": runpod_total_count,
            "runpod_accepting_count": accepting_runpod_count,
            "local_accepting_count": accepting_local_count,
            "total_accepting_count": total_accepting_count,
            "max_runpods_per_profile": config.max_runpods_per_profile,
            "scale_up_wait_seconds": scale_up_wait_seconds,
            "pending_over_threshold_count": pending_over_threshold_count,
            "scale_up_confirmation_count": 0,
            "scale_up_confirmation_required": config.scale_up_confirmation_rounds,
            "scale_up_confirmation_active": False,
        }

        active_operation = _active_operation_for_profile(operations, profile=profile)
        if active_operation is not None:
            decisions.append(
                _decision(
                    profile=profile,
                    action="hold",
                    reason=(
                        "operation active: "
                        f"{active_operation.get('action')} {active_operation.get('status')}"
                    ),
                    metrics=metrics,
                    operation_id=str(active_operation.get("id") or ""),
                )
            )
            continue

        cooldown_remaining = _autoscaler_cooldown_remaining_seconds(
            operations,
            profile=profile,
            now=now,
            cooldown_seconds=config.cooldown_seconds,
        )
        if cooldown_remaining > 0:
            decisions.append(
                _decision(
                    profile=profile,
                    action="hold",
                    reason=f"cooldown {cooldown_remaining}s remaining",
                    metrics={**metrics, "cooldown_remaining_seconds": cooldown_remaining},
                )
            )
            continue

        if (
            pending_count > 0
            and wait_seconds is not None
            and wait_seconds > scale_up_wait_seconds
        ):
            if _is_single_low_priority_wait_outlier(
                detail,
                scale_up_wait_seconds=scale_up_wait_seconds,
            ):
                decisions.append(
                    _decision(
                        profile=profile,
                        action="hold",
                        reason="hold: single low-priority wait outlier",
                        metrics=metrics,
                    )
                )
                continue

            if runpod_total_count >= config.max_runpods_per_profile:
                decisions.append(
                    _decision(
                        profile=profile,
                        action="hold",
                        reason="max runpod capacity reached",
                        metrics=metrics,
                    )
                )
            else:
                confirmation_count = min(
                    config.scale_up_confirmation_rounds,
                    int(confirmation_counts.get(profile, 0)) + 1,
                )
                confirmation_metrics = {
                    **metrics,
                    "scale_up_confirmation_count": confirmation_count,
                    "scale_up_confirmation_active": (
                        confirmation_count < config.scale_up_confirmation_rounds
                    ),
                }
                if confirmation_count < config.scale_up_confirmation_rounds:
                    decisions.append(
                        _decision(
                            profile=profile,
                            action="hold",
                            reason=(
                                "hold: scale-up signal confirming "
                                f"{confirmation_count}/"
                                f"{config.scale_up_confirmation_rounds}"
                            ),
                            metrics=confirmation_metrics,
                        )
                    )
                    continue

                decisions.append(
                    _decision(
                        profile=profile,
                        action="scale_up",
                        reason=(
                            f"pending wait {int(wait_seconds)}s exceeds "
                            f"{scale_up_wait_seconds}s"
                        ),
                        metrics=confirmation_metrics,
                    )
                )
            continue

        should_scale_down = pending_count == 0 or wait_seconds is None or (
            wait_seconds < config.scale_down_wait_seconds
        )
        if should_scale_down:
            if total_accepting_count <= 1:
                decisions.append(
                    _decision(
                        profile=profile,
                        action="hold",
                        reason="minimum total accepting capacity reached",
                        metrics=metrics,
                    )
                )
                continue
            candidate = _highest_slot_worker(idle_runpod_workers, profile=profile)
            if candidate is None:
                decisions.append(
                    _decision(
                        profile=profile,
                        action="hold",
                        reason="no idle runpod candidate",
                        metrics=metrics,
                    )
                )
                continue
            slot = prod_slot_from_agent_id(
                str(candidate.get("agent_id") or ""),
                profile=profile,
            )
            decisions.append(
                _decision(
                    profile=profile,
                    action="scale_down",
                    reason="pending wait below scale-down threshold",
                    metrics=metrics,
                    slot=slot,
                )
            )
            continue

        decisions.append(
            _decision(
                profile=profile,
                action="hold",
                reason="within thresholds",
                metrics=metrics,
            )
        )

    return decisions


def _scale_up_confirmation_counts_from_decisions(
    decisions: list[dict[str, Any]],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for decision in decisions:
        profile = str(decision.get("profile") or "")
        if not profile:
            continue
        if decision.get("scale_up_confirmation_active"):
            counts[profile] = int(decision.get("scale_up_confirmation_count") or 0)
        else:
            counts[profile] = 0
    return counts


async def _safe_store_save_decisions(
    store: RunPodAutoscalerStateStore,
    payload: dict[str, Any],
) -> None:
    try:
        await store.save_last_decisions(payload)
    except Exception:
        logger.warning("Failed to persist RunPod autoscaler decisions", exc_info=True)


async def _safe_store_save_scale_up_confirmation_counts(
    store: RunPodAutoscalerStateStore,
    counts: dict[str, int],
) -> None:
    try:
        await store.save_scale_up_confirmation_counts(counts)
    except Exception:
        logger.warning(
            "Failed to persist RunPod autoscaler scale-up confirmations",
            exc_info=True,
        )


async def evaluate_runpod_autoscaler_once(
    *,
    mutate: bool = True,
    config: RunPodAutoscalerConfig | None = None,
    store: RunPodAutoscalerStateStore | None = None,
    status_payload: dict[str, Any] | None = None,
    workers_payload: dict[str, Any] | None = None,
    operations_payload: dict[str, Any] | None = None,
    fetch_status_func=get_system_status_proxy_payload,
    fetch_workers_func=get_system_workers_proxy_payload,
    fetch_operations_func=runpod_admin_service.get_runpod_operations_payload,
    start_add_func=runpod_admin_service.start_runpod_autoscaler_add_operation,
    start_delete_func=runpod_admin_service.start_runpod_autoscaler_delete_operation,
    now_func=time.time,
    spawn_task_func=None,
) -> dict[str, Any]:
    active_config = config or config_from_env()
    active_store = store or _state_store
    now = float(now_func())
    control_error: str | None = None
    settings_error: str | None = None
    confirmation_error: str | None = None
    scale_up_confirmation_counts: dict[str, int] = {}
    try:
        active_config = active_config.with_scale_up_wait_seconds_by_profile(
            await active_store.get_scale_up_wait_seconds_by_profile()
        )
    except Exception as exc:
        logger.warning("RunPod autoscaler settings unavailable", exc_info=True)
        settings_error = str(exc)
    try:
        control_enabled = await active_store.get_control_enabled(
            default=active_config.configured_enabled
        )
    except Exception as exc:
        logger.warning("RunPod autoscaler control state unavailable", exc_info=True)
        control_enabled = False
        control_error = str(exc)
    try:
        scale_up_confirmation_counts = (
            await active_store.get_scale_up_confirmation_counts()
        )
    except Exception as exc:
        logger.warning(
            "RunPod autoscaler scale-up confirmations unavailable",
            exc_info=True,
        )
        confirmation_error = str(exc)
    effective_enabled = bool(active_config.configured_enabled and control_enabled)
    leader_acquired: bool | None = None

    if mutate and effective_enabled:
        try:
            leader_acquired = await active_store.acquire_leader(
                active_config.owner_id,
                ttl_seconds=active_config.leader_ttl_seconds,
            )
        except Exception:
            logger.warning("RunPod autoscaler leader lease unavailable", exc_info=True)
            leader_acquired = False
        if not leader_acquired:
            payload = {
                "enabled": effective_enabled,
                "configured_enabled": active_config.configured_enabled,
                "control_enabled": control_enabled,
                "leader_acquired": False,
                "config": active_config.payload(),
                "decisions": [],
                "recent_operations": [],
                "last_checked_at": datetime.fromtimestamp(
                    now, tz=timezone.utc
                ).isoformat().replace("+00:00", "Z"),
                "mutation_skipped_reason": "leader lease not acquired",
                "control_error": control_error,
                "settings_error": settings_error,
                "confirmation_error": confirmation_error,
            }
            await _safe_store_save_decisions(active_store, payload)
            return payload

    try:
        status = status_payload if status_payload is not None else await fetch_status_func()
        workers = (
            workers_payload if workers_payload is not None else await fetch_workers_func()
        )
        operations = (
            operations_payload
            if operations_payload is not None
            else await fetch_operations_func()
        )
    except Exception as exc:
        logger.warning("RunPod autoscaler snapshot unavailable: %s", exc)
        payload = {
            "enabled": effective_enabled,
            "configured_enabled": active_config.configured_enabled,
            "control_enabled": control_enabled,
            "leader_acquired": leader_acquired,
            "config": active_config.payload(),
            "decisions": [],
            "recent_operations": [],
            "last_checked_at": datetime.fromtimestamp(
                now, tz=timezone.utc
            ).isoformat().replace("+00:00", "Z"),
            "mutation_skipped_reason": "snapshot unavailable",
            "error": str(exc),
            "control_error": control_error,
            "settings_error": settings_error,
            "confirmation_error": confirmation_error,
        }
        await _safe_store_save_decisions(active_store, payload)
        return payload

    decisions = build_runpod_autoscaler_decisions(
        status_payload=status,
        workers_payload=workers,
        operations_payload=operations,
        config=active_config,
        now=now,
        scale_up_confirmation_counts=scale_up_confirmation_counts,
    )
    recent_operations = [
        operation
        for operation in operations.get("operations") or []
        if operation.get("source") == "autoscaler"
    ][:10]

    executed_operations: list[dict[str, Any]] = []
    if mutate and effective_enabled:
        for decision in decisions:
            try:
                if decision["action"] == "scale_up":
                    operation = await start_add_func(
                        profile=decision["profile"],
                        trigger_reason=decision["reason"],
                        spawn_task_func=spawn_task_func,
                    )
                    decision["operation_id"] = operation.id
                    executed_operations.append(operation_payload(operation))
                elif decision["action"] == "scale_down" and decision.get("slot"):
                    operation = await start_delete_func(
                        profile=decision["profile"],
                        slot=str(decision["slot"]),
                        trigger_reason=decision["reason"],
                        spawn_task_func=spawn_task_func,
                    )
                    decision["operation_id"] = operation.id
                    executed_operations.append(operation_payload(operation))
            except Exception as exc:
                logger.warning(
                    "RunPod autoscaler failed to register operation for %s",
                    decision.get("profile"),
                    exc_info=True,
                )
                decision["action"] = "hold"
                decision["operation_error"] = str(exc)

    if mutate and effective_enabled and leader_acquired is True:
        await _safe_store_save_scale_up_confirmation_counts(
            active_store,
            _scale_up_confirmation_counts_from_decisions(decisions),
        )

    payload = {
        "enabled": effective_enabled,
        "configured_enabled": active_config.configured_enabled,
        "control_enabled": control_enabled,
        "leader_acquired": leader_acquired,
        "config": active_config.payload(),
        "decisions": decisions,
        "recent_operations": recent_operations,
        "executed_operations": executed_operations,
        "last_checked_at": datetime.fromtimestamp(
            now, tz=timezone.utc
        ).isoformat().replace("+00:00", "Z"),
        "control_error": control_error,
        "settings_error": settings_error,
        "confirmation_error": confirmation_error,
    }
    await _safe_store_save_decisions(active_store, payload)
    return payload


async def get_runpod_autoscaler_payload() -> dict[str, Any]:
    return await evaluate_runpod_autoscaler_once(mutate=False)


async def set_runpod_autoscaler_control_payload(
    *,
    enabled: bool,
    reason: str | None = None,
) -> dict[str, Any]:
    await _state_store.set_control_enabled(enabled, reason=reason)
    return await get_runpod_autoscaler_payload()


async def set_runpod_autoscaler_settings_payload(
    *,
    scale_up_wait_minutes_by_profile: dict[str, Any] | None,
    reason: str | None = None,
    store: RunPodAutoscalerStateStore | None = None,
    config: RunPodAutoscalerConfig | None = None,
    refresh_payload: bool = True,
) -> dict[str, Any]:
    thresholds = _validate_scale_up_wait_minutes_by_profile(
        scale_up_wait_minutes_by_profile
    )
    active_store = store or _state_store
    await active_store.set_scale_up_wait_seconds_by_profile(thresholds, reason=reason)
    active_config = (config or config_from_env()).with_scale_up_wait_seconds_by_profile(
        await active_store.get_scale_up_wait_seconds_by_profile()
    )
    if not refresh_payload:
        return {"config": active_config.payload()}
    return await evaluate_runpod_autoscaler_once(
        mutate=False,
        config=active_config,
        store=active_store,
    )


def should_start_runpod_autoscaler_loop(
    config: RunPodAutoscalerConfig | None = None,
) -> bool:
    active_config = config or config_from_env()
    return active_config.configured_enabled


async def run_runpod_autoscaler_loop(
    *,
    config: RunPodAutoscalerConfig | None = None,
    store: RunPodAutoscalerStateStore | None = None,
) -> None:
    active_config = config or config_from_env()
    active_store = store or _state_store
    while True:
        try:
            await evaluate_runpod_autoscaler_once(
                mutate=True,
                config=active_config,
                store=active_store,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("RunPod autoscaler loop failed")
        await asyncio.sleep(active_config.interval_seconds)
