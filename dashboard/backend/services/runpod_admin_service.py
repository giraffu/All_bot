from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from dashboard.backend.schemas import RunPodScaleRequest, RunPodWorkerActionRequest
from dashboard.backend.services.runpod_admin_commands import (
    RUNPOD_PROFILE_OPTIONS,
    RunPodAdminCommandBuilder,
)
from dashboard.backend.services.runpod_admin_operation import (
    RunPodAdminOperation,
    append_operation_log,
    can_terminate_operation,
    can_terminate_operation_reason,
    normalized_stored_operation_payload,
    now_iso,
    operation_attached,
    operation_payload,
    redacted_command,
)
from dashboard.backend.services.runpod_admin_runner import (
    RunPodAdminOperationRunner,
)
from dashboard.backend.services.runpod_operation_store import (
    RunPodOperationStore,
    build_default_runpod_operation_store,
)
from ops.gpu_pool_controller.runpod_profile_catalog import prod_agent_id_from_slot

logger = logging.getLogger("dashboard.runpod")
PROJECT_ROOT = Path(__file__).resolve().parents[3]
RUNPOD_AUTOSCALER_BOOTSTRAP_TIMEOUT_SECONDS_DEFAULT = 40 * 60

_operation_store: RunPodOperationStore = build_default_runpod_operation_store()
_command_builder = RunPodAdminCommandBuilder(project_root=PROJECT_ROOT)
_operation_runner = RunPodAdminOperationRunner(
    store=_operation_store,
    command_builder=_command_builder,
    project_root=PROJECT_ROOT,
    logger=logger,
)

# Compatibility aliases for existing tests and diagnostic scripts.
_operations = _operation_runner.operations
_operation_tasks = _operation_runner.operation_tasks


def _sync_runtime_paths() -> None:
    _command_builder.project_root = PROJECT_ROOT
    _operation_runner.project_root = PROJECT_ROOT


def set_runpod_operation_store_for_tests(store: RunPodOperationStore) -> None:
    global _operation_store
    _operation_store = store
    _operation_runner.set_store(store)


def _operation_payload(operation: RunPodAdminOperation) -> dict[str, Any]:
    return operation_payload(operation)


def _redacted_command(command: list[str]) -> list[str]:
    return redacted_command(command)


def _append_log(operation: RunPodAdminOperation, line: str) -> None:
    append_operation_log(operation, line)


def _can_terminate_operation(operation: RunPodAdminOperation) -> bool:
    return can_terminate_operation(operation)


def _operation_attached(operation: RunPodAdminOperation) -> bool:
    return operation_attached(operation)


def _can_terminate_operation_reason(
    operation: RunPodAdminOperation,
) -> str | None:
    return can_terminate_operation_reason(operation)


def _normalized_stored_operation_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return normalized_stored_operation_payload(payload)


async def _persist_operation(operation: RunPodAdminOperation) -> None:
    await _operation_runner.persist_operation(operation)


async def _release_active_add_if_needed(operation: RunPodAdminOperation) -> None:
    await _operation_runner.release_active_add_if_needed(operation)


async def _active_add_operation_for_profile(profile: str) -> dict[str, Any] | None:
    return await _operation_runner.active_add_operation_for_profile(profile)


def _prune_operations() -> None:
    _operation_runner.prune_operations()


def _default_env_file(env_name: str, candidates: tuple[Path, ...]) -> str:
    return _command_builder.default_env_file(env_name, candidates)


def _container_env_file() -> Path:
    return _command_builder.container_env_file()


def _runpod_env_file() -> str:
    _sync_runtime_paths()
    return _command_builder.runpod_env_file()


def _prod_env_file() -> str:
    _sync_runtime_paths()
    return _command_builder.prod_env_file()


def _runpod_ops_script() -> str:
    _sync_runtime_paths()
    return _command_builder.runpod_ops_script()


def _base_command(action: str, *, profile: str, slot: str | None = None) -> list[str]:
    _sync_runtime_paths()
    return _command_builder.base_command(action, profile=profile, slot=slot)


def _lan_aio_slot_selection_or_422(agent_id: str):
    return _command_builder.lan_aio_slot_selection_or_422(agent_id)


def _lan_aio_restart_command(slot_id: str) -> list[str]:
    _sync_runtime_paths()
    return _command_builder.lan_aio_restart_command(slot_id)


def _lan_aio_control_command(action: str, slot_id: str) -> list[str]:
    _sync_runtime_paths()
    return _command_builder.lan_aio_control_command(action, slot_id)


def _default_prod_max_manual_slots() -> int:
    return _command_builder.default_prod_max_manual_slots()


def _autoscaler_bootstrap_timeout_seconds() -> int:
    raw = os.getenv("DASHBOARD_RUNPOD_AUTOSCALER_BOOTSTRAP_TIMEOUT_SECONDS", "")
    try:
        return (
            max(60, int(raw))
            if raw.strip()
            else RUNPOD_AUTOSCALER_BOOTSTRAP_TIMEOUT_SECONDS_DEFAULT
        )
    except ValueError:
        logger.warning(
            "Invalid DASHBOARD_RUNPOD_AUTOSCALER_BOOTSTRAP_TIMEOUT_SECONDS=%r; "
            "using %s",
            raw,
            RUNPOD_AUTOSCALER_BOOTSTRAP_TIMEOUT_SECONDS_DEFAULT,
        )
        return RUNPOD_AUTOSCALER_BOOTSTRAP_TIMEOUT_SECONDS_DEFAULT


def _operation_env(*, prod_max_manual_slots: int | None = None) -> dict[str, str]:
    return _command_builder.operation_env(prod_max_manual_slots=prod_max_manual_slots)


def _requested_count_or_422(item: Any) -> int:
    return _command_builder.requested_count_or_422(item)


def _normalize_profile_or_422(profile: str) -> str:
    return _command_builder.normalize_profile_or_422(profile)


async def _default_manual_add_plan(
    *,
    profile: str,
    count: int,
    excluded_slots: list[str],
    env: dict[str, str],
) -> list[str]:
    command = _command_builder.plan_add_command(
        profile=profile,
        count=count,
        excluded_slots=excluded_slots,
    )
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=str(PROJECT_ROOT),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    output = stdout.decode("utf-8", errors="replace")
    if process.returncode != 0:
        del stderr
        raise HTTPException(
            status_code=409,
            detail="RunPod add planning command failed",
        )
    try:
        payload = json.loads(output)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=502,
            detail="RunPod add planner returned invalid JSON",
        ) from exc
    if payload.get("ok") is not True:
        raise HTTPException(
            status_code=409,
            detail=str(payload.get("error") or "RunPod add planning failed"),
        )
    slots = list((payload.get("add_plan") or {}).get("create_slots") or [])
    if len(slots) != count:
        raise HTTPException(
            status_code=409,
            detail="RunPod add planner did not return enough free slots",
        )
    return [str(slot) for slot in slots]


_manual_add_plan_func = _default_manual_add_plan


def _agent_selection_or_422(
    agent_id: str,
    *,
    max_manual_slots: int,
) -> tuple[str, str]:
    return _command_builder.agent_selection_or_422(
        agent_id, max_manual_slots=max_manual_slots
    )


async def get_runpod_profiles_payload() -> dict[str, Any]:
    return {"profiles": list(RUNPOD_PROFILE_OPTIONS)}


async def get_runpod_operations_payload(
    *,
    workers_payload: dict[str, Any] | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    if workers_payload is None:
        from dashboard.backend.services.system_service import (
            get_system_workers_proxy_payload,
        )

        async def keep_worker_payload(payload: dict[str, Any]) -> dict[str, Any]:
            return payload

        workers_payload = await get_system_workers_proxy_payload(
            annotate_runpod_locks_func=keep_worker_payload,
        )
    return await _operation_runner.operations_payload(
        workers_payload=workers_payload,
        now=now,
    )


def _runpod_worker_lock_payload(
    *,
    agent_id: str,
    profile: str,
    slot: str,
    reason: str | None,
) -> dict[str, Any]:
    locked_at = time.time()
    return {
        "agent_id": agent_id,
        "profile": profile,
        "slot": slot,
        "locked": True,
        "locked_at": now_iso(locked_at),
        "reason": reason or "dashboard lock runpod worker",
    }


async def is_runpod_worker_locked(agent_id: str) -> bool:
    return await _operation_store.get_locked_runpod_worker(agent_id) is not None


async def get_locked_runpod_workers_payload() -> dict[str, Any]:
    locked = await _operation_store.list_locked_runpod_workers()
    return {
        "locked_workers": [locked[agent_id] for agent_id in sorted(locked)],
        "count": len(locked),
    }


async def lock_runpod_worker_payload(
    agent_id: str,
    request: RunPodWorkerActionRequest,
) -> dict[str, Any]:
    _sync_runtime_paths()
    max_manual_slots = request.prod_max_manual_slots or _default_prod_max_manual_slots()
    profile, slot = _agent_selection_or_422(
        agent_id,
        max_manual_slots=max_manual_slots,
    )
    payload = _runpod_worker_lock_payload(
        agent_id=agent_id,
        profile=profile,
        slot=slot,
        reason=request.reason,
    )
    await _operation_store.set_locked_runpod_worker(agent_id, payload)
    return {"status": "locked", "worker": payload}


async def unlock_runpod_worker_payload(
    agent_id: str,
    request: RunPodWorkerActionRequest,
) -> dict[str, Any]:
    _sync_runtime_paths()
    max_manual_slots = request.prod_max_manual_slots or _default_prod_max_manual_slots()
    profile, slot = _agent_selection_or_422(
        agent_id,
        max_manual_slots=max_manual_slots,
    )
    await _operation_store.clear_locked_runpod_worker(agent_id)
    return {
        "status": "unlocked",
        "worker": {
            "agent_id": agent_id,
            "profile": profile,
            "slot": slot,
            "locked": False,
        },
    }


async def _raise_if_runpod_worker_locked(agent_id: str) -> None:
    locked = await _operation_store.get_locked_runpod_worker(agent_id)
    if locked is None:
        return
    raise HTTPException(
        status_code=409,
        detail=f"RunPod worker is locked; unlock before deleting: {agent_id}",
    )


async def annotate_runpod_worker_locks_payload(
    payload: dict[str, Any],
) -> dict[str, Any]:
    workers = payload.get("workers") if isinstance(payload, dict) else None
    if not isinstance(workers, list):
        return payload
    locked = await _operation_store.list_locked_runpod_workers()
    if not locked:
        for worker in workers:
            if isinstance(worker, dict) and "runpod_locked" not in worker:
                worker["runpod_locked"] = False
        return payload
    for worker in workers:
        if not isinstance(worker, dict):
            continue
        agent_id = str(worker.get("agent_id") or "")
        lock_payload = locked.get(agent_id)
        worker["runpod_locked"] = lock_payload is not None
        if lock_payload is not None:
            worker["runpod_lock"] = lock_payload
    payload["locked_runpod_worker_count"] = len(locked)
    return payload


async def terminate_runpod_operation_payload(operation_id: str) -> dict[str, Any]:
    return await _operation_runner.terminate_operation_payload(operation_id)


async def start_runpod_scale_payload(
    request: RunPodScaleRequest,
    *,
    spawn_task_func=None,
    plan_slots_func=None,
) -> dict[str, Any]:
    _sync_runtime_paths()
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
    planner = plan_slots_func or _manual_add_plan_func
    batch_id = uuid.uuid4().hex
    operations: list[RunPodAdminOperation] = []
    for profile, requested_count in normalized_items:
        active_operation_id = await _operation_store.get_active_add(profile)
        if active_operation_id:
            raise HTTPException(
                status_code=409,
                detail=(
                    "RunPod autoscaler add operation is already active for profile "
                    f"{profile}: {active_operation_id}"
                ),
            )
        for attempt in range(3):
            reserved_slots = await _operation_store.list_manual_add_slots(profile)
            slots = await planner(
                profile=profile,
                count=requested_count,
                excluded_slots=sorted(reserved_slots),
                env=env,
            )
            specs: list[dict[str, Any]] = []
            for slot in slots:
                agent_id = prod_agent_id_from_slot(
                    slot,
                    profile=profile,
                    max_manual_slots=(
                        request.prod_max_manual_slots
                        or _default_prod_max_manual_slots()
                    ),
                )
                command = _base_command("add", profile=profile, slot=slot)
                command.extend(["--count", "1"])
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
                specs.append({"slot": slot, "agent_id": agent_id, "command": command})
            try:
                registered = await _operation_runner.register_manual_add_batch(
                    profile=profile,
                    batch_id=batch_id,
                    specs=specs,
                    env=env,
                    spawn_task_func=spawn_task_func,
                )
            except HTTPException as exc:
                if exc.status_code == 409 and attempt < 2:
                    continue
                raise
            operations.extend(registered)
            break

    return {
        "status": "accepted",
        "batch_id": batch_id,
        "operations": [_operation_payload(operation) for operation in operations],
    }


async def pause_runpod_worker_payload(
    agent_id: str,
    request: RunPodWorkerActionRequest,
    *,
    spawn_task_func=None,
) -> dict[str, Any]:
    _sync_runtime_paths()
    max_manual_slots = request.prod_max_manual_slots or _default_prod_max_manual_slots()
    profile, slot = _agent_selection_or_422(
        agent_id,
        max_manual_slots=max_manual_slots,
    )
    command = _base_command("disable", profile=profile, slot=slot)
    command.append("--execute")
    operation = await _register_operation(
        action="pause",
        profile=profile,
        command=command,
        env=_operation_env(prod_max_manual_slots=max_manual_slots),
        agent_id=agent_id,
        slot=slot,
        spawn_task_func=spawn_task_func,
    )
    return {"status": "accepted", "operation": _operation_payload(operation)}


async def enable_runpod_worker_payload(
    agent_id: str,
    request: RunPodWorkerActionRequest,
    *,
    spawn_task_func=None,
) -> dict[str, Any]:
    _sync_runtime_paths()
    max_manual_slots = request.prod_max_manual_slots or _default_prod_max_manual_slots()
    profile, slot = _agent_selection_or_422(
        agent_id,
        max_manual_slots=max_manual_slots,
    )
    command = _base_command("enable", profile=profile, slot=slot)
    command.append("--execute")
    operation = await _register_operation(
        action="enable",
        profile=profile,
        command=command,
        env=_operation_env(prod_max_manual_slots=max_manual_slots),
        agent_id=agent_id,
        slot=slot,
        spawn_task_func=spawn_task_func,
    )
    return {"status": "accepted", "operation": _operation_payload(operation)}


async def restart_runpod_worker_payload(
    agent_id: str,
    request: RunPodWorkerActionRequest,
    *,
    spawn_task_func=None,
) -> dict[str, Any]:
    _sync_runtime_paths()
    max_manual_slots = request.prod_max_manual_slots or _default_prod_max_manual_slots()
    profile, slot = _agent_selection_or_422(
        agent_id,
        max_manual_slots=max_manual_slots,
    )
    command = _base_command("restart", profile=profile, slot=slot)
    command.append("--execute")
    operation = await _register_operation(
        action="restart",
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
    _sync_runtime_paths()
    max_manual_slots = request.prod_max_manual_slots or _default_prod_max_manual_slots()
    profile, slot = _agent_selection_or_422(
        agent_id,
        max_manual_slots=max_manual_slots,
    )
    await _raise_if_runpod_worker_locked(agent_id)
    command = _base_command("down", profile=profile, slot=slot)
    command.append("--execute")
    operation = await _register_operation(
        action="delete",
        profile=profile,
        command=command,
        env=_operation_env(prod_max_manual_slots=max_manual_slots),
        agent_id=agent_id,
        slot=slot,
        spawn_task_func=spawn_task_func,
    )
    return {"status": "accepted", "operation": _operation_payload(operation)}


async def start_runpod_autoscaler_add_operation(
    *,
    profile: str,
    trigger_reason: str,
    spawn_task_func=None,
) -> RunPodAdminOperation:
    _sync_runtime_paths()
    normalized_profile = _normalize_profile_or_422(profile)
    active_operation = await _active_add_operation_for_profile(normalized_profile)
    if active_operation is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                "RunPod add operation is already active for profile "
                f"{normalized_profile}: {active_operation['id']}"
            ),
        )
    command = _base_command("add", profile=normalized_profile)
    command.extend(
        [
            "--count",
            "1",
            "--retry-unavailable",
            "--max-attempts",
            "100",
            "--retry-interval",
            "30",
            "--worker-timeout",
            str(_autoscaler_bootstrap_timeout_seconds()),
            "--execute",
        ]
    )
    return await _register_operation(
        action="add",
        profile=normalized_profile,
        command=command,
        env=_operation_env(),
        requested_count=1,
        active_add_profile=normalized_profile,
        source="autoscaler",
        trigger_reason=trigger_reason,
        spawn_task_func=spawn_task_func,
    )


async def start_runpod_autoscaler_delete_operation(
    *,
    profile: str,
    slot: str,
    trigger_reason: str,
    spawn_task_func=None,
) -> RunPodAdminOperation:
    _sync_runtime_paths()
    normalized_profile = _normalize_profile_or_422(profile)
    max_manual_slots = _default_prod_max_manual_slots()
    agent_id = prod_agent_id_from_slot(
        slot,
        profile=normalized_profile,
        max_manual_slots=max_manual_slots,
    )
    await _raise_if_runpod_worker_locked(agent_id)
    command = _base_command("down", profile=normalized_profile, slot=slot)
    command.append("--execute")
    return await _register_operation(
        action="delete",
        profile=normalized_profile,
        command=command,
        env=_operation_env(prod_max_manual_slots=max_manual_slots),
        agent_id=agent_id,
        slot=slot,
        source="autoscaler",
        trigger_reason=trigger_reason,
        spawn_task_func=spawn_task_func,
    )


async def start_runpod_autoscaler_enable_operation(
    *,
    profile: str,
    slot: str,
    agent_id: str,
    trigger_reason: str,
    spawn_task_func=None,
) -> RunPodAdminOperation:
    _sync_runtime_paths()
    normalized_profile = _normalize_profile_or_422(profile)
    max_manual_slots = _default_prod_max_manual_slots()
    command = _base_command("enable", profile=normalized_profile, slot=slot)
    command.append("--execute")
    return await _register_operation(
        action="enable",
        profile=normalized_profile,
        command=command,
        env=_operation_env(prod_max_manual_slots=max_manual_slots),
        agent_id=agent_id,
        slot=slot,
        source="autoscaler",
        trigger_reason=trigger_reason,
        spawn_task_func=spawn_task_func,
    )


async def start_runpod_autoscaler_restart_operation(
    *,
    profile: str,
    slot: str,
    agent_id: str,
    trigger_reason: str,
    spawn_task_func=None,
) -> RunPodAdminOperation:
    _sync_runtime_paths()
    normalized_profile = _normalize_profile_or_422(profile)
    max_manual_slots = _default_prod_max_manual_slots()
    command = _base_command("restart", profile=normalized_profile, slot=slot)
    command.append("--execute")
    return await _register_operation(
        action="restart",
        profile=normalized_profile,
        command=command,
        env=_operation_env(prod_max_manual_slots=max_manual_slots),
        agent_id=agent_id,
        slot=slot,
        source="autoscaler",
        trigger_reason=trigger_reason,
        spawn_task_func=spawn_task_func,
    )


async def restart_lan_aio_worker_payload(
    agent_id: str,
    request: RunPodWorkerActionRequest,
    *,
    spawn_task_func=None,
) -> dict[str, Any]:
    _sync_runtime_paths()
    del request
    slot = _lan_aio_slot_selection_or_422(agent_id)
    operation = await _register_operation(
        action="restart",
        profile=slot.target_profile_id,
        command=_lan_aio_restart_command(slot.id),
        env=dict(os.environ),
        agent_id=agent_id,
        slot=slot.id,
        spawn_task_func=spawn_task_func,
    )
    return {"status": "accepted", "operation": _operation_payload(operation)}


async def pause_lan_aio_worker_payload(
    agent_id: str,
    request: RunPodWorkerActionRequest,
    *,
    spawn_task_func=None,
) -> dict[str, Any]:
    _sync_runtime_paths()
    del request
    slot = _lan_aio_slot_selection_or_422(agent_id)
    operation = await _register_operation(
        action="pause",
        profile=slot.target_profile_id,
        command=_lan_aio_control_command("disable-aio", slot.id),
        env=dict(os.environ),
        agent_id=agent_id,
        slot=slot.id,
        spawn_task_func=spawn_task_func,
    )
    return {"status": "accepted", "operation": _operation_payload(operation)}


async def enable_lan_aio_worker_payload(
    agent_id: str,
    request: RunPodWorkerActionRequest,
    *,
    spawn_task_func=None,
) -> dict[str, Any]:
    _sync_runtime_paths()
    del request
    slot = _lan_aio_slot_selection_or_422(agent_id)
    operation = await _register_operation(
        action="enable",
        profile=slot.target_profile_id,
        command=_lan_aio_control_command("enable-aio", slot.id),
        env=dict(os.environ),
        agent_id=agent_id,
        slot=slot.id,
        spawn_task_func=spawn_task_func,
    )
    return {"status": "accepted", "operation": _operation_payload(operation)}


async def _register_operation(
    *,
    action: str,
    profile: str,
    command: list[str],
    env: dict[str, str],
    requested_count: int | None = None,
    agent_id: str | None = None,
    slot: str | None = None,
    active_add_profile: str | None = None,
    active_lan_aio_slot: str | None = None,
    source: str = "manual",
    trigger_reason: str | None = None,
    spawn_task_func=None,
) -> RunPodAdminOperation:
    return await _operation_runner.register_operation(
        action=action,
        profile=profile,
        command=command,
        env=env,
        requested_count=requested_count,
        agent_id=agent_id,
        slot=slot,
        active_add_profile=active_add_profile,
        active_lan_aio_slot=active_lan_aio_slot,
        source=source,
        trigger_reason=trigger_reason,
        spawn_task_func=spawn_task_func,
    )


async def _run_operation(
    operation_id: str,
    *,
    command: list[str],
    env: dict[str, str],
) -> None:
    await _operation_runner.run_operation(operation_id, command=command, env=env)


def _terminate_process_group(operation: RunPodAdminOperation) -> None:
    _operation_runner.terminate_process_group(operation)


async def _run_termination_cleanup(
    operation: RunPodAdminOperation,
    *,
    env: dict[str, str],
) -> bool:
    return await _operation_runner.run_termination_cleanup(operation, env=env)


async def _run_cleanup_command(
    operation: RunPodAdminOperation,
    *,
    command: list[str],
    env: dict[str, str],
) -> int:
    return await _operation_runner.run_cleanup_command(
        operation,
        command=command,
        env=env,
    )
