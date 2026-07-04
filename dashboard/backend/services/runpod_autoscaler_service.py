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
    RUNPOD_AUTOSCALER_PROFILE_OPTIONS,
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
AUTOSCALER_OWNER_ID = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex}"
SCALE_UP_WAIT_MINUTES_MIN = 1
SCALE_UP_WAIT_MINUTES_MAX = 240
TASK_DURATION_SECONDS_MIN = 1
TASK_DURATION_SECONDS_MAX = 3600
UNKNOWN_TASK_DURATION_SECONDS = 100
RUNPOD_FAULT_RESTART_SECONDS_DEFAULT = 5 * 60
RUNPOD_BOOTSTRAP_TIMEOUT_SECONDS_DEFAULT = 40 * 60
RUNPOD_BOOTSTRAP_REPLACEMENT_LIMIT_DEFAULT = 2
RUNPOD_BOOTSTRAP_REPLACEMENT_WINDOW_SECONDS_DEFAULT = 2 * 60 * 60
RUNPOD_UNHEALTHY_STATUSES = {"error", "quarantined"}
RUNPOD_PAUSED_CONTROL_STATES = {"disabled", "draining"}
RUNPOD_RECOVERABLE_STATUSES = {"idle", "running"}
DEFAULT_TASK_DURATION_SECONDS_BY_TYPE: dict[str, int] = {
    "img2img": 13,
    "img2img_lora": 13,
    "image_to_video": 60,
    "wan22_video_v2": 60,
    "i2i_pro": 12,
    "t2i-pornmaster-turbo": 12,
    "face_swap": 12,
    "scail2_action_transfer": 300,
    "scail2_video_replacement": 300,
    "ltx_video": 120,
    "ltx_video_flf2v": 120,
    "ltx_video_v2v_audio": 120,
    "pornmaster_flux2_single_edit": 30,
    "pornmaster_flux2_multi_edit": 30,
    "unknown": UNKNOWN_TASK_DURATION_SECONDS,
}


def _runpod_profile_names() -> list[str]:
    return [str(option["profile"]) for option in RUNPOD_AUTOSCALER_PROFILE_OPTIONS]


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


def _valid_autoscaler_task_types() -> set[str]:
    task_types = {"unknown"}
    for option in RUNPOD_AUTOSCALER_PROFILE_OPTIONS:
        task_types.update(_normalized_supported_task_types(option.get("supported_task_types")))
    return task_types


def _normalize_task_duration_seconds_by_type(
    raw: dict[str, Any] | None,
) -> dict[str, int]:
    normalized: dict[str, int] = {}
    valid_task_types = _valid_autoscaler_task_types()
    for raw_task_type, raw_seconds in (raw or {}).items():
        task_type = resolve_worker_execution_task_type(str(raw_task_type))
        if task_type not in valid_task_types:
            continue
        try:
            seconds = int(raw_seconds)
        except (TypeError, ValueError):
            continue
        if seconds < TASK_DURATION_SECONDS_MIN:
            continue
        if seconds > TASK_DURATION_SECONDS_MAX:
            continue
        normalized[task_type] = seconds
    return normalized


def _validate_task_duration_seconds_by_type(
    updates: dict[str, Any] | None,
) -> dict[str, int]:
    if not updates:
        return {}
    normalized: dict[str, int] = {}
    valid_task_types = _valid_autoscaler_task_types()
    for raw_task_type, raw_seconds in updates.items():
        task_type = resolve_worker_execution_task_type(str(raw_task_type))
        if task_type not in valid_task_types:
            raise HTTPException(
                status_code=422,
                detail=f"unsupported task type duration setting: {raw_task_type}",
            )
        try:
            seconds = int(raw_seconds)
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=422,
                detail=f"invalid task duration seconds for {raw_task_type}",
            ) from exc
        if seconds < TASK_DURATION_SECONDS_MIN or seconds > TASK_DURATION_SECONDS_MAX:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"task duration for {raw_task_type} must be between "
                    f"{TASK_DURATION_SECONDS_MIN} and {TASK_DURATION_SECONDS_MAX} seconds"
                ),
            )
        normalized[task_type] = seconds
    return normalized


def _normalize_paused_profiles(raw: Any) -> set[str]:
    valid_profiles = set(_runpod_profile_names())
    if isinstance(raw, dict):
        candidates = []
        for profile, paused in raw.items():
            try:
                is_paused = _coerce_bool_setting(paused)
            except ValueError:
                continue
            if is_paused:
                candidates.append(str(profile))
    else:
        candidates = [str(profile) for profile in (raw or [])]
    return {profile for profile in candidates if profile in valid_profiles}


def _coerce_bool_setting(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    raise ValueError("invalid boolean setting")


def _validate_profile_autoscaler_paused_by_profile(
    updates: dict[str, Any] | None,
) -> dict[str, bool]:
    if not updates:
        return {}
    valid_profiles = set(_runpod_profile_names())
    normalized: dict[str, bool] = {}
    for profile, raw_paused in updates.items():
        profile_name = str(profile)
        if profile_name not in valid_profiles:
            raise HTTPException(
                status_code=422,
                detail=f"unsupported RunPod profile: {profile_name}",
            )
        try:
            normalized[profile_name] = _coerce_bool_setting(raw_paused)
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"invalid autoscaler pause flag for {profile_name}",
            ) from exc
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
    scale_down_wait_seconds: int = 60
    cooldown_seconds: int = 10 * 60
    max_runpods_per_profile: int = 5
    heartbeat_max_age_seconds: int = 5 * 60
    min_runpod_lifetime_seconds: int = 30 * 60
    runpod_fault_restart_seconds: int = RUNPOD_FAULT_RESTART_SECONDS_DEFAULT
    runpod_bootstrap_timeout_seconds: int = RUNPOD_BOOTSTRAP_TIMEOUT_SECONDS_DEFAULT
    runpod_bootstrap_replacement_limit: int = (
        RUNPOD_BOOTSTRAP_REPLACEMENT_LIMIT_DEFAULT
    )
    runpod_bootstrap_replacement_window_seconds: int = (
        RUNPOD_BOOTSTRAP_REPLACEMENT_WINDOW_SECONDS_DEFAULT
    )
    leader_ttl_seconds: int = 90
    owner_id: str = AUTOSCALER_OWNER_ID
    scale_up_wait_seconds_by_profile: dict[str, int] = field(default_factory=dict)
    task_duration_seconds_by_type: dict[str, int] = field(default_factory=dict)
    paused_profiles: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        merged = _default_scale_up_wait_seconds_by_profile(self.scale_up_wait_seconds)
        merged.update(
            _normalize_scale_up_wait_seconds_by_profile(
                self.scale_up_wait_seconds_by_profile
            )
        )
        object.__setattr__(self, "scale_up_wait_seconds_by_profile", merged)
        duration_seconds = dict(DEFAULT_TASK_DURATION_SECONDS_BY_TYPE)
        duration_seconds.update(
            _normalize_task_duration_seconds_by_type(
                self.task_duration_seconds_by_type
            )
        )
        duration_seconds.setdefault("unknown", UNKNOWN_TASK_DURATION_SECONDS)
        object.__setattr__(self, "task_duration_seconds_by_type", duration_seconds)
        object.__setattr__(
            self,
            "paused_profiles",
            _normalize_paused_profiles(self.paused_profiles),
        )
        object.__setattr__(
            self,
            "min_runpod_lifetime_seconds",
            max(0, int(self.min_runpod_lifetime_seconds or 0)),
        )
        object.__setattr__(
            self,
            "runpod_fault_restart_seconds",
            max(0, int(self.runpod_fault_restart_seconds or 0)),
        )
        object.__setattr__(
            self,
            "runpod_bootstrap_timeout_seconds",
            max(60, int(self.runpod_bootstrap_timeout_seconds or 0)),
        )
        object.__setattr__(
            self,
            "runpod_bootstrap_replacement_limit",
            max(0, int(self.runpod_bootstrap_replacement_limit or 0)),
        )
        object.__setattr__(
            self,
            "runpod_bootstrap_replacement_window_seconds",
            max(60, int(self.runpod_bootstrap_replacement_window_seconds or 0)),
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

    def task_duration_seconds_for_type(self, task_type: str | None) -> int:
        normalized = resolve_worker_execution_task_type(task_type)
        return int(
            self.task_duration_seconds_by_type.get(
                normalized,
                self.task_duration_seconds_by_type.get(
                    "unknown",
                    UNKNOWN_TASK_DURATION_SECONDS,
                ),
            )
        )

    def with_task_duration_seconds_by_type(
        self,
        durations: dict[str, int] | None,
    ) -> "RunPodAutoscalerConfig":
        merged = dict(self.task_duration_seconds_by_type)
        merged.update(_normalize_task_duration_seconds_by_type(durations))
        return replace(self, task_duration_seconds_by_type=merged)

    def is_profile_paused(self, profile: str) -> bool:
        return str(profile) in self.paused_profiles

    def with_paused_profiles(
        self,
        paused_profiles: Any,
    ) -> "RunPodAutoscalerConfig":
        return replace(
            self,
            paused_profiles=_normalize_paused_profiles(paused_profiles),
        )

    def payload(self) -> dict[str, Any]:
        paused_profiles = sorted(self.paused_profiles)
        return {
            "configured_enabled": self.configured_enabled,
            "mode": self.mode,
            "interval_seconds": self.interval_seconds,
            "scale_up_wait_seconds": self.scale_up_wait_seconds,
            "scale_up_wait_seconds_by_profile": dict(
                self.scale_up_wait_seconds_by_profile
            ),
            "task_duration_seconds_by_type": dict(
                self.task_duration_seconds_by_type
            ),
            "unknown_task_duration_seconds": self.task_duration_seconds_for_type(
                "unknown"
            ),
            "paused_profiles": paused_profiles,
            "profile_autoscaler_paused_by_profile": {
                profile: profile in self.paused_profiles
                for profile in _runpod_profile_names()
            },
            "scale_down_wait_seconds": self.scale_down_wait_seconds,
            "cooldown_seconds": self.cooldown_seconds,
            "max_runpods_per_profile": self.max_runpods_per_profile,
            "heartbeat_max_age_seconds": self.heartbeat_max_age_seconds,
            "min_runpod_lifetime_seconds": self.min_runpod_lifetime_seconds,
            "runpod_fault_restart_seconds": self.runpod_fault_restart_seconds,
            "runpod_bootstrap_timeout_seconds": (
                self.runpod_bootstrap_timeout_seconds
            ),
            "runpod_bootstrap_replacement_limit": (
                self.runpod_bootstrap_replacement_limit
            ),
            "runpod_bootstrap_replacement_window_seconds": (
                self.runpod_bootstrap_replacement_window_seconds
            ),
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
        min_runpod_lifetime_seconds=_int_env(
            "DASHBOARD_RUNPOD_AUTOSCALER_MIN_RUNPOD_LIFETIME_SECONDS",
            default=30 * 60,
            minimum=0,
        ),
        runpod_fault_restart_seconds=_int_env(
            "DASHBOARD_RUNPOD_AUTOSCALER_FAULT_RESTART_SECONDS",
            default=RUNPOD_FAULT_RESTART_SECONDS_DEFAULT,
            minimum=0,
        ),
        runpod_bootstrap_timeout_seconds=_int_env(
            "DASHBOARD_RUNPOD_AUTOSCALER_BOOTSTRAP_TIMEOUT_SECONDS",
            default=RUNPOD_BOOTSTRAP_TIMEOUT_SECONDS_DEFAULT,
            minimum=60,
        ),
        runpod_bootstrap_replacement_limit=_int_env(
            "DASHBOARD_RUNPOD_AUTOSCALER_BOOTSTRAP_REPLACEMENT_LIMIT",
            default=RUNPOD_BOOTSTRAP_REPLACEMENT_LIMIT_DEFAULT,
            minimum=0,
        ),
        runpod_bootstrap_replacement_window_seconds=_int_env(
            "DASHBOARD_RUNPOD_AUTOSCALER_BOOTSTRAP_REPLACEMENT_WINDOW_SECONDS",
            default=RUNPOD_BOOTSTRAP_REPLACEMENT_WINDOW_SECONDS_DEFAULT,
            minimum=60,
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

    async def get_task_duration_seconds_by_type(self) -> dict[str, int]:
        ...

    async def set_task_duration_seconds_by_type(
        self,
        durations: dict[str, int],
        *,
        reason: str | None,
    ) -> None:
        ...

    async def get_paused_profiles(self) -> set[str]:
        ...

    async def set_profile_autoscaler_paused_by_profile(
        self,
        updates: dict[str, bool],
        *,
        reason: str | None,
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

    async def get_task_duration_seconds_by_type(self) -> dict[str, int]:
        return {}

    async def set_task_duration_seconds_by_type(
        self,
        durations: dict[str, int],
        *,
        reason: str | None,
    ) -> None:
        del durations, reason

    async def get_paused_profiles(self) -> set[str]:
        return set()

    async def set_profile_autoscaler_paused_by_profile(
        self,
        updates: dict[str, bool],
        *,
        reason: str | None,
    ) -> None:
        del updates, reason

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
        self.task_duration_seconds_by_type: dict[str, int] = {}
        self.paused_profiles: set[str] = set()
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

    async def get_task_duration_seconds_by_type(self) -> dict[str, int]:
        return dict(self.task_duration_seconds_by_type)

    async def set_task_duration_seconds_by_type(
        self,
        durations: dict[str, int],
        *,
        reason: str | None,
    ) -> None:
        self.task_duration_seconds_by_type.update(
            _normalize_task_duration_seconds_by_type(durations)
        )
        self.settings_reason = reason

    async def get_paused_profiles(self) -> set[str]:
        return set(self.paused_profiles)

    async def set_profile_autoscaler_paused_by_profile(
        self,
        updates: dict[str, bool],
        *,
        reason: str | None,
    ) -> None:
        normalized = _validate_profile_autoscaler_paused_by_profile(updates)
        for profile, paused in normalized.items():
            if paused:
                self.paused_profiles.add(profile)
            else:
                self.paused_profiles.discard(profile)
        self.settings_reason = reason

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

    async def _get_settings_payload(self) -> dict[str, Any]:
        raw = await self.redis.get(AUTOSCALER_SETTINGS_KEY)
        if not raw:
            return {}
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    async def _save_settings_payload(
        self,
        payload: dict[str, Any],
        *,
        reason: str | None,
    ) -> None:
        payload["reason"] = reason or ""
        payload["updated_at"] = time.time()
        payload["owner_id"] = AUTOSCALER_OWNER_ID
        await self.redis.set(
            AUTOSCALER_SETTINGS_KEY,
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        )

    async def set_scale_up_wait_seconds_by_profile(
        self,
        thresholds: dict[str, int],
        *,
        reason: str | None,
    ) -> None:
        payload = await self._get_settings_payload()
        current = _normalize_scale_up_wait_seconds_by_profile(
            payload.get("scale_up_wait_seconds_by_profile")
        )
        current.update(_normalize_scale_up_wait_seconds_by_profile(thresholds))
        payload["scale_up_wait_seconds_by_profile"] = current
        await self._save_settings_payload(payload, reason=reason)

    async def get_task_duration_seconds_by_type(self) -> dict[str, int]:
        payload = await self._get_settings_payload()
        return _normalize_task_duration_seconds_by_type(
            payload.get("task_duration_seconds_by_type")
        )

    async def set_task_duration_seconds_by_type(
        self,
        durations: dict[str, int],
        *,
        reason: str | None,
    ) -> None:
        payload = await self._get_settings_payload()
        current = _normalize_task_duration_seconds_by_type(
            payload.get("task_duration_seconds_by_type")
        )
        current.update(_normalize_task_duration_seconds_by_type(durations))
        payload["task_duration_seconds_by_type"] = current
        await self._save_settings_payload(payload, reason=reason)

    async def get_paused_profiles(self) -> set[str]:
        payload = await self._get_settings_payload()
        return _normalize_paused_profiles(payload.get("paused_profiles"))

    async def set_profile_autoscaler_paused_by_profile(
        self,
        updates: dict[str, bool],
        *,
        reason: str | None,
    ) -> None:
        payload = await self._get_settings_payload()
        paused_profiles = _normalize_paused_profiles(payload.get("paused_profiles"))
        for profile, paused in _validate_profile_autoscaler_paused_by_profile(
            updates
        ).items():
            if paused:
                paused_profiles.add(profile)
            else:
                paused_profiles.discard(profile)
        payload["paused_profiles"] = sorted(paused_profiles)
        await self._save_settings_payload(payload, reason=reason)

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
    from src.services.redis_connection import build_redis_client

    redis_client = build_redis_client(redis_url, decode_responses=True)
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
        for option in RUNPOD_AUTOSCALER_PROFILE_OPTIONS
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


def _worker_status(worker: dict[str, Any]) -> str:
    return str(worker.get("status") or "").strip().lower()


def _worker_control_state(worker: dict[str, Any]) -> str:
    return str(worker.get("control_state") or "enabled").strip().lower()


def _worker_runpod_locked(worker: dict[str, Any]) -> bool:
    value = worker.get("runpod_locked", worker.get("locked", False))
    try:
        return _coerce_bool_setting(value)
    except ValueError:
        return False


def _runpod_slot_for_worker(worker: dict[str, Any], *, profile: str) -> str | None:
    try:
        return prod_slot_from_agent_id(str(worker.get("agent_id") or ""), profile=profile)
    except ValueError:
        return None


def _runpod_fault_age_seconds(worker: dict[str, Any], *, now: float) -> int | None:
    if _worker_status(worker) not in RUNPOD_UNHEALTHY_STATUSES:
        return None
    last_error_at = _safe_float(worker.get("last_error_at"))
    if last_error_at is None:
        return None
    return max(0, int(now - last_error_at))


def _runpod_restart_recovery_candidate(
    worker: dict[str, Any],
    *,
    profile: str,
    now: float,
    heartbeat_max_age_seconds: int,
    fault_restart_seconds: int,
) -> tuple[int, str, dict[str, Any]] | None:
    if not _worker_seen_recently(
        worker,
        now=now,
        heartbeat_max_age_seconds=heartbeat_max_age_seconds,
    ):
        return None
    slot = _runpod_slot_for_worker(worker, profile=profile)
    if not slot:
        return None
    fault_age_seconds = _runpod_fault_age_seconds(worker, now=now)
    if fault_age_seconds is None or fault_age_seconds < fault_restart_seconds:
        return None
    return fault_age_seconds, slot, worker


def _runpod_enable_recovery_candidate(
    worker: dict[str, Any],
    *,
    profile: str,
    now: float,
    heartbeat_max_age_seconds: int,
) -> tuple[int, str, dict[str, Any]] | None:
    if not _worker_seen_recently(
        worker,
        now=now,
        heartbeat_max_age_seconds=heartbeat_max_age_seconds,
    ):
        return None
    if _worker_status(worker) not in RUNPOD_RECOVERABLE_STATUSES:
        return None
    if _worker_control_state(worker) not in RUNPOD_PAUSED_CONTROL_STATES:
        return None
    slot = _runpod_slot_for_worker(worker, profile=profile)
    if not slot:
        return None
    return int(slot), slot, worker


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
        and _worker_status(worker) in RUNPOD_RECOVERABLE_STATUSES
        and _worker_control_state(worker) == "enabled"
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


def _operation_started_at(operation: dict[str, Any]) -> float | None:
    return (
        _parse_operation_time(operation.get("started_at"))
        or _parse_operation_time(operation.get("created_at"))
    )


def _operation_cleanup_slots(operation: dict[str, Any]) -> set[str]:
    return {str(item) for item in operation.get("cleanup_slots") or []}


def _operation_is_bootstrap_cleanup_success(operation: dict[str, Any]) -> bool:
    return (
        operation.get("source") == "autoscaler"
        and str(operation.get("action") or "") == "add"
        and str(operation.get("status") or "") == "failed"
        and str(operation.get("cleanup_status") or "") == "succeeded"
        and bool(_operation_cleanup_slots(operation))
    )


def _active_bootstrap_elapsed_seconds(
    operation: dict[str, Any],
    *,
    now: float,
) -> int | None:
    if operation.get("source") != "autoscaler":
        return None
    if str(operation.get("action") or "") != "add":
        return None
    if not _operation_cleanup_slots(operation):
        return None
    started_at = _operation_started_at(operation)
    if started_at is None:
        return None
    return max(0, int(now - started_at))


def _bootstrap_replacement_count(
    operations: list[dict[str, Any]],
    *,
    profile: str,
    now: float,
    window_seconds: int,
) -> int:
    count = 0
    for operation in operations:
        if _operation_profile(operation) != profile:
            continue
        if not _operation_is_bootstrap_cleanup_success(operation):
            continue
        ended_at = _parse_operation_time(operation.get("ended_at"))
        if ended_at is None:
            continue
        if 0 <= now - ended_at <= window_seconds:
            count += 1
    return count


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
        if _operation_is_bootstrap_cleanup_success(operation):
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


def _autoscaler_agent_cooldown_remaining_seconds(
    operations: list[dict[str, Any]],
    *,
    agent_id: str,
    actions: set[str],
    now: float,
    cooldown_seconds: int,
) -> int:
    latest_ended_at: float | None = None
    for operation in operations:
        if operation.get("source") != "autoscaler":
            continue
        if str(operation.get("agent_id") or "") != agent_id:
            continue
        if str(operation.get("action") or "") not in actions:
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


def _safe_count_map(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    counts: dict[str, int] = {}
    for raw_task_type, raw_count in value.items():
        task_type = resolve_worker_execution_task_type(str(raw_task_type))
        count = _safe_int_or_none(raw_count)
        if count is None or count <= 0:
            continue
        counts[task_type] = counts.get(task_type, 0) + count
    return counts


def _pending_count_by_task_type(detail: dict[str, Any]) -> dict[str, int]:
    counts = _safe_count_map(detail.get("pending_count_by_task_type"))
    if counts:
        return counts
    pending_count = _safe_int_or_none(detail.get("pending_count")) or 0
    if pending_count <= 0:
        return {}
    supported_task_types = _normalized_supported_task_types(
        detail.get("supported_task_types")
    )
    fallback_task_type = supported_task_types[0] if supported_task_types else "unknown"
    return {fallback_task_type: pending_count}


def _non_low_trust_clear_pending_count_by_task_type(
    detail: dict[str, Any],
) -> dict[str, int]:
    return _safe_count_map(
        detail.get("non_low_trust_clear_pending_count_by_task_type")
    )


def _pending_work_seconds(
    pending_counts: dict[str, int],
    *,
    config: RunPodAutoscalerConfig,
) -> int:
    return sum(
        count * config.task_duration_seconds_for_type(task_type)
        for task_type, count in pending_counts.items()
    )


def _running_remaining_seconds_for_worker(
    worker: dict[str, Any],
    *,
    config: RunPodAutoscalerConfig,
    now: float,
) -> int:
    if str(worker.get("status") or "").lower() != "running":
        return 0
    task_type = resolve_worker_execution_task_type(worker.get("current_task_type"))
    duration_seconds = config.task_duration_seconds_for_type(task_type)
    started_at = _safe_float(worker.get("current_task_created_at"))
    if started_at is None or started_at <= 0:
        return duration_seconds
    elapsed_seconds = max(0, int(now - started_at))
    return max(duration_seconds - elapsed_seconds, 0)


def _autoscaler_created_slot_started_at(
    operations: list[dict[str, Any]],
    *,
    profile: str,
    slot: str,
) -> float | None:
    newest_started_at: float | None = None
    for operation in operations:
        if _operation_profile(operation) != profile:
            continue
        if operation.get("source") != "autoscaler":
            continue
        if operation.get("action") != "add":
            continue
        cleanup_slots = {str(item) for item in operation.get("cleanup_slots") or []}
        if slot not in cleanup_slots:
            continue
        started_at = (
            _parse_operation_time(operation.get("ended_at"))
            or _parse_operation_time(operation.get("started_at"))
            or _parse_operation_time(operation.get("created_at"))
        )
        if started_at is None:
            continue
        if newest_started_at is None or started_at > newest_started_at:
            newest_started_at = started_at
    return newest_started_at


def _minimum_lifetime_remaining_seconds(
    operations: list[dict[str, Any]],
    *,
    profile: str,
    slot: str,
    now: float,
    min_lifetime_seconds: int,
) -> int:
    if min_lifetime_seconds <= 0:
        return 0
    started_at = _autoscaler_created_slot_started_at(
        operations,
        profile=profile,
        slot=slot,
    )
    if started_at is None:
        return 0
    return max(0, int(min_lifetime_seconds - (now - started_at)))


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
) -> list[dict[str, Any]]:
    queue_details = {
        str(item.get("profile")): item
        for item in status_payload.get("runpod_profile_queue_details") or []
    }
    workers = list(workers_payload.get("workers") or [])
    operations = list(operations_payload.get("operations") or [])
    profile_task_types = _profile_task_types()
    decisions: list[dict[str, Any]] = []

    for option in RUNPOD_AUTOSCALER_PROFILE_OPTIONS:
        profile = str(option["profile"])
        detail = queue_details.get(profile) or {}
        pending_count = int(detail.get("pending_count") or 0)
        active_count = int(detail.get("active_count") or 0)
        wait_seconds = _safe_float(detail.get("max_pending_wait_seconds"))
        clear_time_threshold_seconds = config.scale_up_wait_seconds_for_profile(profile)
        pending_counts_by_task_type = _pending_count_by_task_type(detail)
        total_pending_work_seconds = _pending_work_seconds(
            pending_counts_by_task_type,
            config=config,
        )
        non_low_trust_clear_pending_counts_by_task_type = (
            _non_low_trust_clear_pending_count_by_task_type(detail)
        )
        non_low_trust_clear_pending_count = sum(
            non_low_trust_clear_pending_counts_by_task_type.values()
        )
        pending_work_seconds = _pending_work_seconds(
            non_low_trust_clear_pending_counts_by_task_type,
            config=config,
        )

        idle_runpod_workers: list[dict[str, Any]] = []
        accepting_runpod_count = 0
        accepting_local_count = 0
        runpod_total_count = 0
        locked_runpod_count = 0
        locked_idle_runpod_count = 0
        running_remaining_seconds = 0
        runpod_restart_candidates: list[tuple[int, str, dict[str, Any]]] = []
        runpod_enable_candidates: list[tuple[int, str, dict[str, Any]]] = []

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
                if _worker_seen_recently(
                    worker,
                    now=now,
                    heartbeat_max_age_seconds=config.heartbeat_max_age_seconds,
                ):
                    runpod_total_count += 1
                if accepting:
                    accepting_runpod_count += 1
                runpod_locked = _worker_runpod_locked(worker)
                if runpod_locked:
                    locked_runpod_count += 1
                if (
                    runpod_locked
                    and _worker_idle_delete_candidate(
                        worker,
                        now=now,
                        heartbeat_max_age_seconds=config.heartbeat_max_age_seconds,
                    )
                ):
                    locked_idle_runpod_count += 1
                if (not runpod_locked) and _worker_idle_delete_candidate(
                    worker,
                    now=now,
                    heartbeat_max_age_seconds=config.heartbeat_max_age_seconds,
                ):
                    idle_runpod_workers.append(worker)
                restart_candidate = _runpod_restart_recovery_candidate(
                    worker,
                    profile=profile,
                    now=now,
                    heartbeat_max_age_seconds=config.heartbeat_max_age_seconds,
                    fault_restart_seconds=config.runpod_fault_restart_seconds,
                )
                if restart_candidate is not None:
                    runpod_restart_candidates.append(restart_candidate)
                enable_candidate = _runpod_enable_recovery_candidate(
                    worker,
                    profile=profile,
                    now=now,
                    heartbeat_max_age_seconds=config.heartbeat_max_age_seconds,
                )
                if enable_candidate is not None:
                    runpod_enable_candidates.append(enable_candidate)
            else:
                if accepting:
                    accepting_local_count += 1
            if accepting:
                running_remaining_seconds += _running_remaining_seconds_for_worker(
                    worker,
                    config=config,
                    now=now,
                )

        total_accepting_count = accepting_runpod_count + accepting_local_count
        estimated_backlog_seconds = pending_work_seconds + running_remaining_seconds
        estimated_clear_time_seconds: float | None
        if non_low_trust_clear_pending_count <= 0:
            estimated_clear_time_seconds = None
            capacity_status = (
                "no_non_low_trust_backlog" if pending_count > 0 else "idle"
            )
        elif total_accepting_count > 0:
            estimated_clear_time_seconds = (
                estimated_backlog_seconds / total_accepting_count
            )
            capacity_status = "ok"
        elif pending_count > 0 or running_remaining_seconds > 0:
            estimated_clear_time_seconds = None
            capacity_status = "no_accepting_workers"
        else:
            estimated_clear_time_seconds = 0.0
            capacity_status = "idle"
        bootstrap_replacement_count = _bootstrap_replacement_count(
            operations,
            profile=profile,
            now=now,
            window_seconds=config.runpod_bootstrap_replacement_window_seconds,
        )
        metrics = {
            "active_count": active_count,
            "pending_count": pending_count,
            "max_pending_wait_seconds": wait_seconds,
            "runpod_count": runpod_total_count,
            "runpod_accepting_count": accepting_runpod_count,
            "runpod_locked_count": locked_runpod_count,
            "runpod_locked_idle_count": locked_idle_runpod_count,
            "runpod_idle_delete_candidate_count": len(idle_runpod_workers),
            "local_accepting_count": accepting_local_count,
            "total_accepting_count": total_accepting_count,
            "max_runpods_per_profile": config.max_runpods_per_profile,
            "scale_up_wait_seconds": clear_time_threshold_seconds,
            "clear_time_threshold_seconds": clear_time_threshold_seconds,
            "pending_count_by_task_type": pending_counts_by_task_type,
            "non_low_trust_clear_pending_count": non_low_trust_clear_pending_count,
            "non_low_trust_clear_pending_count_by_task_type": (
                non_low_trust_clear_pending_counts_by_task_type
            ),
            "last_non_low_trust_pending_queue_index": detail.get(
                "last_non_low_trust_pending_queue_index"
            ),
            "task_duration_seconds_by_type": {
                task_type: config.task_duration_seconds_for_type(task_type)
                for task_type in {
                    *pending_counts_by_task_type,
                    *non_low_trust_clear_pending_counts_by_task_type,
                }
            },
            "estimated_total_pending_work_seconds": total_pending_work_seconds,
            "estimated_pending_work_seconds": pending_work_seconds,
            "estimated_non_low_trust_pending_work_seconds": pending_work_seconds,
            "estimated_running_remaining_seconds": running_remaining_seconds,
            "estimated_backlog_seconds": estimated_backlog_seconds,
            "estimated_clear_time_seconds": estimated_clear_time_seconds,
            "estimated_non_low_trust_clear_time_seconds": (
                estimated_clear_time_seconds
            ),
            "capacity_status": capacity_status,
            "runpod_fault_restart_seconds": config.runpod_fault_restart_seconds,
            "runpod_fault_candidate_count": len(runpod_restart_candidates),
            "runpod_paused_candidate_count": len(runpod_enable_candidates),
            "runpod_bootstrap_timeout_seconds": (
                config.runpod_bootstrap_timeout_seconds
            ),
            "runpod_bootstrap_replacement_count": bootstrap_replacement_count,
            "runpod_bootstrap_replacement_limit": (
                config.runpod_bootstrap_replacement_limit
            ),
            "runpod_bootstrap_replacement_window_seconds": (
                config.runpod_bootstrap_replacement_window_seconds
            ),
            "profile_autoscaler_paused": config.is_profile_paused(profile),
        }

        if config.is_profile_paused(profile):
            decisions.append(
                _decision(
                    profile=profile,
                    action="hold",
                    reason="hold: profile autoscaler paused",
                    metrics=metrics,
                )
            )
            continue

        active_operation = _active_operation_for_profile(operations, profile=profile)
        if active_operation is not None:
            bootstrap_elapsed_seconds = _active_bootstrap_elapsed_seconds(
                active_operation,
                now=now,
            )
            active_reason = (
                f"hold: runpod add still bootstrapping {bootstrap_elapsed_seconds}s"
                if bootstrap_elapsed_seconds is not None
                else (
                    "operation active: "
                    f"{active_operation.get('action')} {active_operation.get('status')}"
                )
            )
            active_metrics = metrics
            if bootstrap_elapsed_seconds is not None:
                active_metrics = {
                    **metrics,
                    "runpod_bootstrap_elapsed_seconds": bootstrap_elapsed_seconds,
                }
            decisions.append(
                _decision(
                    profile=profile,
                    action="hold",
                    reason=active_reason,
                    metrics=active_metrics,
                    operation_id=str(active_operation.get("id") or ""),
                )
            )
            continue

        if runpod_restart_candidates:
            fault_age_seconds, slot, worker = max(
                runpod_restart_candidates,
                key=lambda item: item[0],
            )
            agent_id = str(worker.get("agent_id") or "")
            recovery_cooldown_remaining = (
                _autoscaler_agent_cooldown_remaining_seconds(
                    operations,
                    agent_id=agent_id,
                    actions={"restart"},
                    now=now,
                    cooldown_seconds=config.cooldown_seconds,
                )
            )
            if recovery_cooldown_remaining <= 0:
                decisions.append(
                    _decision(
                        profile=profile,
                        action="restart",
                        reason=(
                            "restart: runpod fault persisted "
                            f"{fault_age_seconds}s"
                        ),
                        metrics={
                            **metrics,
                            "agent_id": agent_id,
                            "runpod_fault_age_seconds": fault_age_seconds,
                        },
                        slot=slot,
                    )
                )
                continue

        if runpod_enable_candidates:
            _slot_number, slot, worker = max(
                runpod_enable_candidates,
                key=lambda item: item[0],
            )
            agent_id = str(worker.get("agent_id") or "")
            recovery_cooldown_remaining = (
                _autoscaler_agent_cooldown_remaining_seconds(
                    operations,
                    agent_id=agent_id,
                    actions={"enable"},
                    now=now,
                    cooldown_seconds=config.cooldown_seconds,
                )
            )
            if recovery_cooldown_remaining <= 0:
                decisions.append(
                    _decision(
                        profile=profile,
                        action="enable",
                        reason="enable: runpod paused worker available",
                        metrics={
                            **metrics,
                            "agent_id": agent_id,
                            "runpod_control_state": _worker_control_state(worker),
                        },
                        slot=slot,
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

        if pending_count > 0:
            if non_low_trust_clear_pending_count <= 0:
                decisions.append(
                    _decision(
                        profile=profile,
                        action="hold",
                        reason="hold: no non-low-trust backlog",
                        metrics=metrics,
                    )
                )
                continue

            if (
                config.runpod_bootstrap_replacement_limit > 0
                and bootstrap_replacement_count
                >= config.runpod_bootstrap_replacement_limit
            ):
                decisions.append(
                    _decision(
                        profile=profile,
                        action="hold",
                        reason="hold: bootstrap replacement limit reached",
                        metrics=metrics,
                    )
                )
                continue

            if runpod_total_count >= config.max_runpods_per_profile:
                decisions.append(
                    _decision(
                        profile=profile,
                        action="hold",
                        reason="hold: max runpod capacity reached",
                        metrics=metrics,
                    )
                )
                continue

            if capacity_status == "no_accepting_workers":
                decisions.append(
                    _decision(
                        profile=profile,
                        action="scale_up",
                        reason="scale_up: no accepting workers for backlog",
                        metrics=metrics,
                    )
                )
                continue

            if (
                estimated_clear_time_seconds is not None
                and estimated_clear_time_seconds > clear_time_threshold_seconds
            ):
                if bootstrap_replacement_count > 0:
                    scale_up_reason = (
                        "replace: previous runpod bootstrap timed out; "
                        "estimated non-low-trust clear time "
                        f"{int(estimated_clear_time_seconds)}s exceeds "
                        f"{clear_time_threshold_seconds}s"
                    )
                else:
                    scale_up_reason = (
                        "scale_up: estimated non-low-trust clear time "
                        f"{int(estimated_clear_time_seconds)}s exceeds "
                        f"{clear_time_threshold_seconds}s"
                    )
                decisions.append(
                    _decision(
                        profile=profile,
                        action="scale_up",
                        reason=scale_up_reason,
                        metrics=metrics,
                    )
                )
                continue

            decisions.append(
                _decision(
                    profile=profile,
                    action="hold",
                    reason=(
                        "hold: estimated non-low-trust clear time within threshold"
                    ),
                    metrics=metrics,
                )
            )
            continue

        if runpod_total_count <= 0:
            decisions.append(
                _decision(
                    profile=profile,
                    action="hold",
                    reason="hold: no backlog",
                    metrics=metrics,
                )
            )
            continue

        if total_accepting_count <= 1:
            decisions.append(
                _decision(
                    profile=profile,
                    action="hold",
                    reason="hold: minimum total accepting capacity reached",
                    metrics=metrics,
                )
            )
            continue
        candidate = _highest_slot_worker(idle_runpod_workers, profile=profile)
        if candidate is None:
            reason = (
                "hold: all idle runpod candidates are locked"
                if locked_idle_runpod_count > 0
                else "hold: no idle runpod candidate"
            )
            decisions.append(
                _decision(
                    profile=profile,
                    action="hold",
                    reason=reason,
                    metrics=metrics,
                )
            )
            continue
        slot = prod_slot_from_agent_id(
            str(candidate.get("agent_id") or ""),
            profile=profile,
        )
        lifetime_remaining_seconds = _minimum_lifetime_remaining_seconds(
            operations,
            profile=profile,
            slot=slot,
            now=now,
            min_lifetime_seconds=config.min_runpod_lifetime_seconds,
        )
        if lifetime_remaining_seconds > 0:
            decisions.append(
                _decision(
                    profile=profile,
                    action="hold",
                    reason=(
                        "hold: minimum lifetime remaining "
                        f"{lifetime_remaining_seconds}s"
                    ),
                    metrics={
                        **metrics,
                        "minimum_lifetime_remaining_seconds": (
                            lifetime_remaining_seconds
                        ),
                    },
                    slot=slot,
                )
            )
            continue
        decisions.append(
            _decision(
                profile=profile,
                action="scale_down",
                reason="scale_down: no backlog and idle runpod available",
                metrics=metrics,
                slot=slot,
            )
        )
        continue

    return decisions


async def _safe_store_save_decisions(
    store: RunPodAutoscalerStateStore,
    payload: dict[str, Any],
) -> None:
    try:
        await store.save_last_decisions(payload)
    except Exception:
        logger.warning("Failed to persist RunPod autoscaler decisions", exc_info=True)


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
    start_restart_func=runpod_admin_service.start_runpod_autoscaler_restart_operation,
    start_enable_func=runpod_admin_service.start_runpod_autoscaler_enable_operation,
    now_func=time.time,
    spawn_task_func=None,
) -> dict[str, Any]:
    active_config = config or config_from_env()
    active_store = store or _state_store
    now = float(now_func())
    control_error: str | None = None
    settings_error: str | None = None
    try:
        active_config = active_config.with_scale_up_wait_seconds_by_profile(
            await active_store.get_scale_up_wait_seconds_by_profile()
        )
        active_config = active_config.with_task_duration_seconds_by_type(
            await active_store.get_task_duration_seconds_by_type()
        )
        active_config = active_config.with_paused_profiles(
            await active_store.get_paused_profiles()
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
        }
        await _safe_store_save_decisions(active_store, payload)
        return payload

    decisions = build_runpod_autoscaler_decisions(
        status_payload=status,
        workers_payload=workers,
        operations_payload=operations,
        config=active_config,
        now=now,
    )
    recent_operations = [
        operation
        for operation in operations.get("operations") or []
        if operation.get("source") == "autoscaler"
    ][:10]

    executed_operations: list[dict[str, Any]] = []
    if mutate and effective_enabled:
        scale_up_executed = False
        for decision in decisions:
            try:
                if decision["action"] == "scale_up":
                    if scale_up_executed:
                        decision["operation_skipped_reason"] = (
                            "scale-up already executed this round"
                        )
                        continue
                    operation = await start_add_func(
                        profile=decision["profile"],
                        trigger_reason=decision["reason"],
                        spawn_task_func=spawn_task_func,
                    )
                    decision["operation_id"] = operation.id
                    scale_up_executed = True
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
                elif (
                    decision["action"] == "restart"
                    and decision.get("slot")
                    and decision.get("agent_id")
                ):
                    operation = await start_restart_func(
                        profile=decision["profile"],
                        slot=str(decision["slot"]),
                        agent_id=str(decision["agent_id"]),
                        trigger_reason=decision["reason"],
                        spawn_task_func=spawn_task_func,
                    )
                    decision["operation_id"] = operation.id
                    executed_operations.append(operation_payload(operation))
                elif (
                    decision["action"] == "enable"
                    and decision.get("slot")
                    and decision.get("agent_id")
                ):
                    operation = await start_enable_func(
                        profile=decision["profile"],
                        slot=str(decision["slot"]),
                        agent_id=str(decision["agent_id"]),
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
    task_duration_seconds_by_type: dict[str, Any] | None = None,
    profile_autoscaler_paused_by_profile: dict[str, Any] | None = None,
    reason: str | None = None,
    store: RunPodAutoscalerStateStore | None = None,
    config: RunPodAutoscalerConfig | None = None,
    refresh_payload: bool = True,
) -> dict[str, Any]:
    thresholds = _validate_scale_up_wait_minutes_by_profile(
        scale_up_wait_minutes_by_profile
    )
    durations = _validate_task_duration_seconds_by_type(
        task_duration_seconds_by_type
    )
    paused_updates = _validate_profile_autoscaler_paused_by_profile(
        profile_autoscaler_paused_by_profile
    )
    active_store = store or _state_store
    if thresholds:
        await active_store.set_scale_up_wait_seconds_by_profile(thresholds, reason=reason)
    if durations:
        await active_store.set_task_duration_seconds_by_type(durations, reason=reason)
    if paused_updates:
        await active_store.set_profile_autoscaler_paused_by_profile(
            paused_updates,
            reason=reason,
        )
    active_config = (config or config_from_env()).with_scale_up_wait_seconds_by_profile(
        await active_store.get_scale_up_wait_seconds_by_profile()
    ).with_task_duration_seconds_by_type(
        await active_store.get_task_duration_seconds_by_type()
    ).with_paused_profiles(
        await active_store.get_paused_profiles()
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
