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
    requested_count: int | None = None
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
        "requested_count": operation.requested_count,
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


def _container_env_file() -> Path:
    configured = os.getenv("DASHBOARD_RUNPOD_CONTAINER_ENV_FILE", "/app/.env").strip()
    return Path(configured)


def _runpod_env_file() -> str:
    return _default_env_file(
        "DASHBOARD_RUNPOD_ENV_FILE",
        (
            _container_env_file(),
            PROJECT_ROOT / ".env.cloud.test",
            PROJECT_ROOT / ".env",
        ),
    )


def _prod_env_file() -> str:
    return _default_env_file(
        "DASHBOARD_RUNPOD_PROD_ENV_FILE",
        (
            _container_env_file(),
            PROJECT_ROOT / ".env.cloud.prod",
            PROJECT_ROOT / ".env",
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


def _default_prod_max_manual_slots() -> int:
    raw = os.getenv("RUNPOD_PROD_MAX_MANUAL_SLOTS", "").strip()
    if not raw:
        return 100
    try:
        value = int(raw)
    except ValueError as exc:
        raise HTTPException(
            status_code=500,
            detail="RUNPOD_PROD_MAX_MANUAL_SLOTS must be an integer",
        ) from exc
    return max(1, value)


def _operation_env(*, prod_max_manual_slots: int | None = None) -> dict[str, str]:
    env = dict(os.environ)
    env["RUNPOD_DRY_RUN"] = "false"
    env["RUNPOD_AUTOSCALER_ENABLED"] = "true"
    env["RUNPOD_PROD_MAX_MANUAL_SLOTS"] = str(
        prod_max_manual_slots or _default_prod_max_manual_slots()
    )
    return env


def _requested_count_or_422(item: Any) -> int:
    raw = item.count if item.count is not None else item.desired_count
    if raw is None:
        raise HTTPException(
            status_code=422,
            detail="items[].count is required",
        )
    requested = int(raw)
    if requested < 1:
        raise HTTPException(
            status_code=422,
            detail="items[].count must be >= 1",
        )
    return requested


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
        normalized_items.append((profile, _requested_count_or_422(item)))

    env = _operation_env(prod_max_manual_slots=request.prod_max_manual_slots)

    operations: list[RunPodAdminOperation] = []
    for profile, requested_count in normalized_items:
        command = _base_command("add", profile=profile)
        command.extend(["--count", str(requested_count)])
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
                action="add",
                profile=profile,
                command=command,
                env=env,
                requested_count=requested_count,
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
    max_manual_slots = request.prod_max_manual_slots or _default_prod_max_manual_slots()
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
        env=_operation_env(prod_max_manual_slots=max_manual_slots),
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
    max_manual_slots = request.prod_max_manual_slots or _default_prod_max_manual_slots()
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
        env=_operation_env(prod_max_manual_slots=max_manual_slots),
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
    requested_count: int | None = None,
    agent_id: str | None = None,
    slot: str | None = None,
    spawn_task_func=None,
) -> RunPodAdminOperation:
    operation = RunPodAdminOperation(
        id=uuid.uuid4().hex,
        action=action,
        profile=profile,
        command=command,
        requested_count=requested_count,
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
