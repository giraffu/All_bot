from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from dashboard.backend.schemas import RunPodScaleRequest, RunPodWorkerActionRequest
from ops.gpu_pool_controller.providers.runpod import (
    normalize_prod_worker_profile,
    prod_slot_from_agent_id,
    prod_worker_profile_from_agent_id,
    redact_text,
)

logger = logging.getLogger("dashboard.runpod")
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OPERATION_LOG_LINES = int(
    os.getenv("DASHBOARD_RUNPOD_OPERATION_LOG_LINES", "160")
)
DEFAULT_MAX_OPERATION_RECORDS = int(
    os.getenv("DASHBOARD_RUNPOD_MAX_OPERATION_RECORDS", "100")
)

RUNPOD_PROFILE_OPTIONS: tuple[dict[str, Any], ...] = (
    {
        "profile": "img2img",
        "label": "img2img / img2img_lora",
        "supported_task_types": ["img2img", "img2img_lora"],
    },
    {
        "profile": "image_to_video",
        "label": "image_to_video",
        "supported_task_types": ["image_to_video", "video_insert", "video_edit"],
    },
    {
        "profile": "wan22_video_v2",
        "label": "wan22_video_v2",
        "supported_task_types": ["wan22_video_v2"],
    },
    {
        "profile": "i2i_pro",
        "label": "i2i_pro / txt2img / face_swap",
        "supported_task_types": ["i2i_pro", "t2i-pornmaster-turbo", "face_swap"],
    },
)


@dataclass
class RunPodAdminOperation:
    id: str
    action: str
    profile: str
    command: list[str]
    created_at: float = field(default_factory=time.time)
    desired_count: int | None = None
    agent_id: str | None = None
    slot: str | None = None
    status: str = "pending"
    started_at: float | None = None
    ended_at: float | None = None
    pid: int | None = None
    exit_code: int | None = None
    error: str | None = None
    log_lines: list[str] = field(default_factory=list)


_operations: dict[str, RunPodAdminOperation] = {}
_operation_tasks: set[asyncio.Task] = set()


def _now_iso(timestamp: float | None) -> str | None:
    if timestamp is None:
        return None
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(timestamp))


def _operation_payload(operation: RunPodAdminOperation) -> dict[str, Any]:
    return {
        "id": operation.id,
        "action": operation.action,
        "profile": operation.profile,
        "desired_count": operation.desired_count,
        "agent_id": operation.agent_id,
        "slot": operation.slot,
        "status": operation.status,
        "created_at": _now_iso(operation.created_at),
        "started_at": _now_iso(operation.started_at),
        "ended_at": _now_iso(operation.ended_at),
        "pid": operation.pid,
        "exit_code": operation.exit_code,
        "error": operation.error,
        "log_tail": list(operation.log_lines[-DEFAULT_OPERATION_LOG_LINES:]),
        "command": _redacted_command(operation.command),
    }


def _redacted_command(command: list[str]) -> list[str]:
    return [redact_text(str(part)) for part in command]


def _append_log(operation: RunPodAdminOperation, line: str) -> None:
    clean = redact_text(line.rstrip())
    if not clean:
        return
    operation.log_lines.append(clean)
    if len(operation.log_lines) > DEFAULT_OPERATION_LOG_LINES:
        operation.log_lines = operation.log_lines[-DEFAULT_OPERATION_LOG_LINES:]


def _prune_operations() -> None:
    if DEFAULT_MAX_OPERATION_RECORDS <= 0:
        return
    if len(_operations) <= DEFAULT_MAX_OPERATION_RECORDS:
        return
    finished = [
        operation
        for operation in _operations.values()
        if operation.status in {"succeeded", "failed"}
    ]
    finished.sort(key=lambda item: item.ended_at or item.created_at)
    overflow = len(_operations) - DEFAULT_MAX_OPERATION_RECORDS
    for operation in finished[:overflow]:
        _operations.pop(operation.id, None)


def _default_env_file(env_name: str, candidates: tuple[Path, ...]) -> str:
    configured = os.getenv(env_name, "").strip()
    if configured:
        return configured
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return str(candidates[0])


def _runpod_env_file() -> str:
    return _default_env_file(
        "DASHBOARD_RUNPOD_ENV_FILE",
        (
            PROJECT_ROOT / ".env.cloud.test",
            PROJECT_ROOT / ".env",
            Path("/app/.env"),
        ),
    )


def _prod_env_file() -> str:
    return _default_env_file(
        "DASHBOARD_RUNPOD_PROD_ENV_FILE",
        (
            PROJECT_ROOT / ".env.cloud.prod",
            PROJECT_ROOT / ".env",
            Path("/app/.env"),
        ),
    )


def _runpod_ops_script() -> str:
    return os.getenv(
        "DASHBOARD_RUNPOD_OPS_SCRIPT",
        str(PROJECT_ROOT / "scripts" / "runpod_prod_ops.sh"),
    )


def _base_command(action: str, *, profile: str, slot: str | None = None) -> list[str]:
    command = [
        "bash",
        _runpod_ops_script(),
        action,
        "--profile",
        profile,
        "--runpod-env-file",
        _runpod_env_file(),
        "--prod-env-file",
        _prod_env_file(),
    ]
    if slot:
        command.extend(["--slot", slot])
    return command


def _operation_env(
    *,
    max_pods_total: int,
    max_pods_per_type: int,
    max_hourly_cost_usd: float,
    prod_max_manual_slots: int | None,
) -> dict[str, str]:
    env = dict(os.environ)
    env["RUNPOD_DRY_RUN"] = "false"
    env["RUNPOD_AUTOSCALER_ENABLED"] = "true"
    env["RUNPOD_MAX_PODS_TOTAL"] = str(max_pods_total)
    env["RUNPOD_MAX_PODS_PER_TYPE"] = str(max_pods_per_type)
    env["RUNPOD_MAX_HOURLY_COST_USD"] = f"{max_hourly_cost_usd:g}"
    env["RUNPOD_PROD_MAX_MANUAL_SLOTS"] = str(
        prod_max_manual_slots or max(2, max_pods_per_type)
    )
    return env


def _validate_gate_values(
    *,
    desired_counts: list[int],
    max_pods_total: int,
    max_pods_per_type: int,
) -> None:
    max_desired = max(desired_counts or [0])
    if max_pods_per_type > max_pods_total:
        raise HTTPException(
            status_code=422,
            detail="max_pods_per_type must be <= max_pods_total",
        )
    if max_desired > max_pods_per_type:
        raise HTTPException(
            status_code=422,
            detail="desired_count must be <= max_pods_per_type",
        )


def _normalize_profile_or_422(profile: str) -> str:
    try:
        return normalize_prod_worker_profile(profile)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _agent_selection_or_422(
    agent_id: str,
    *,
    max_manual_slots: int,
) -> tuple[str, str]:
    try:
        profile = prod_worker_profile_from_agent_id(agent_id)
        slot = prod_slot_from_agent_id(
            agent_id,
            profile=profile,
            max_manual_slots=max_manual_slots,
        )
        return profile, slot
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


async def get_runpod_profiles_payload() -> dict[str, Any]:
    return {"profiles": list(RUNPOD_PROFILE_OPTIONS)}


async def get_runpod_operations_payload() -> dict[str, Any]:
    operations = sorted(
        _operations.values(),
        key=lambda item: item.created_at,
        reverse=True,
    )
    return {
        "operations": [_operation_payload(operation) for operation in operations],
        "count": len(operations),
    }


async def start_runpod_scale_payload(
    request: RunPodScaleRequest,
    *,
    spawn_task_func=None,
) -> dict[str, Any]:
    normalized_items: list[tuple[str, int]] = []
    seen_profiles: set[str] = set()
    for item in request.items:
        profile = _normalize_profile_or_422(item.profile)
        if profile in seen_profiles:
            raise HTTPException(
                status_code=422,
                detail=f"duplicate profile in scale request: {profile}",
            )
        seen_profiles.add(profile)
        normalized_items.append((profile, int(item.desired_count)))

    _validate_gate_values(
        desired_counts=[desired for _profile, desired in normalized_items],
        max_pods_total=request.max_pods_total,
        max_pods_per_type=request.max_pods_per_type,
    )
    env = _operation_env(
        max_pods_total=request.max_pods_total,
        max_pods_per_type=request.max_pods_per_type,
        max_hourly_cost_usd=request.max_hourly_cost_usd,
        prod_max_manual_slots=request.prod_max_manual_slots,
    )

    operations: list[RunPodAdminOperation] = []
    for profile, desired_count in normalized_items:
        command = _base_command("scale", profile=profile)
        command.extend(["--desired", str(desired_count)])
        if request.retry_unavailable:
            command.append("--retry-unavailable")
        command.extend(
            [
                "--max-attempts",
                str(request.max_attempts),
                "--retry-interval",
                str(request.retry_interval_seconds),
                "--execute",
            ]
        )
        operations.append(
            _register_operation(
                action="scale",
                profile=profile,
                command=command,
                env=env,
                desired_count=desired_count,
                spawn_task_func=spawn_task_func,
            )
        )

    return {
        "status": "accepted",
        "operations": [_operation_payload(operation) for operation in operations],
    }


async def pause_runpod_worker_payload(
    agent_id: str,
    request: RunPodWorkerActionRequest,
    *,
    spawn_task_func=None,
) -> dict[str, Any]:
    max_manual_slots = request.prod_max_manual_slots or max(2, request.max_pods_per_type)
    profile, slot = _agent_selection_or_422(
        agent_id,
        max_manual_slots=max_manual_slots,
    )
    command = _base_command("disable", profile=profile, slot=slot)
    command.append("--execute")
    operation = _register_operation(
        action="pause",
        profile=profile,
        command=command,
        env=_operation_env(
            max_pods_total=request.max_pods_total,
            max_pods_per_type=request.max_pods_per_type,
            max_hourly_cost_usd=request.max_hourly_cost_usd,
            prod_max_manual_slots=max_manual_slots,
        ),
        agent_id=agent_id,
        slot=slot,
        spawn_task_func=spawn_task_func,
    )
    return {"status": "accepted", "operation": _operation_payload(operation)}


async def delete_runpod_worker_payload(
    agent_id: str,
    request: RunPodWorkerActionRequest,
    *,
    spawn_task_func=None,
) -> dict[str, Any]:
    max_manual_slots = request.prod_max_manual_slots or max(2, request.max_pods_per_type)
    profile, slot = _agent_selection_or_422(
        agent_id,
        max_manual_slots=max_manual_slots,
    )
    command = _base_command("down", profile=profile, slot=slot)
    command.append("--execute")
    operation = _register_operation(
        action="delete",
        profile=profile,
        command=command,
        env=_operation_env(
            max_pods_total=request.max_pods_total,
            max_pods_per_type=request.max_pods_per_type,
            max_hourly_cost_usd=request.max_hourly_cost_usd,
            prod_max_manual_slots=max_manual_slots,
        ),
        agent_id=agent_id,
        slot=slot,
        spawn_task_func=spawn_task_func,
    )
    return {"status": "accepted", "operation": _operation_payload(operation)}


def _register_operation(
    *,
    action: str,
    profile: str,
    command: list[str],
    env: dict[str, str],
    desired_count: int | None = None,
    agent_id: str | None = None,
    slot: str | None = None,
    spawn_task_func=None,
) -> RunPodAdminOperation:
    operation = RunPodAdminOperation(
        id=uuid.uuid4().hex,
        action=action,
        profile=profile,
        command=command,
        desired_count=desired_count,
        agent_id=agent_id,
        slot=slot,
    )
    _operations[operation.id] = operation
    _prune_operations()
    coroutine = _run_operation(operation.id, command=command, env=env)
    task_factory = spawn_task_func or asyncio.create_task
    task = task_factory(coroutine)
    if task is None:
        coroutine.close()
    if isinstance(task, asyncio.Task):
        _operation_tasks.add(task)
        task.add_done_callback(_operation_tasks.discard)
    return operation


async def _run_operation(
    operation_id: str,
    *,
    command: list[str],
    env: dict[str, str],
) -> None:
    operation = _operations.get(operation_id)
    if operation is None:
        return
    operation.status = "running"
    operation.started_at = time.time()
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(PROJECT_ROOT),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        operation.pid = process.pid
        assert process.stdout is not None
        while True:
            raw = await process.stdout.readline()
            if not raw:
                break
            _append_log(operation, raw.decode("utf-8", errors="replace"))
        operation.exit_code = await process.wait()
        operation.status = "succeeded" if operation.exit_code == 0 else "failed"
        if operation.exit_code != 0:
            operation.error = f"runpod operation exited with code {operation.exit_code}"
    except Exception as exc:
        operation.status = "failed"
        operation.error = redact_text(str(exc))
        logger.exception("RunPod dashboard operation failed")
    finally:
        operation.ended_at = time.time()
