from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from dashboard.backend.schemas import (
    LanAioSlotActionRequest,
    RunPodScaleRequest,
    RunPodWorkerActionRequest,
)
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
from ops.gpu_pool_controller.config_loader import load_controller_config
from ops.gpu_pool_controller.lan_aio_prod import (
    LanAioProdOps,
    physical_slot_key,
    slot_to_jsonable,
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


def _lan_aio_ops_script() -> str:
    _sync_runtime_paths()
    return _command_builder.lan_aio_ops_script()


def _lan_aio_prod_env_file() -> str:
    _sync_runtime_paths()
    return _command_builder.lan_aio_prod_env_file()


def _lan_aio_aio_env_file() -> str:
    _sync_runtime_paths()
    return _command_builder.lan_aio_aio_env_file()


def _lan_aio_model_env_file() -> str:
    _sync_runtime_paths()
    return _command_builder.lan_aio_model_env_file()


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


def _lan_aio_action_command(action: str, slot_id: str) -> list[str]:
    _sync_runtime_paths()
    return _command_builder.lan_aio_action_command(action, slot_id)


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


async def get_runpod_operations_payload() -> dict[str, Any]:
    return await _operation_runner.operations_payload()


def _build_lan_aio_ops() -> LanAioProdOps:
    _sync_runtime_paths()
    return LanAioProdOps(
        config_root=None,
        prod_env_file=Path(_lan_aio_prod_env_file()),
        aio_env_file=Path(_lan_aio_aio_env_file()),
        model_env_file=Path(_lan_aio_model_env_file()),
        remote_workers_source_dir=PROJECT_ROOT / "remote_workers",
    )


async def get_lan_aio_profiles_payload() -> dict[str, Any]:
    config = load_controller_config()
    profiles = []
    for profile in config.profiles.values():
        if not profile.all_in_one_image_ref or not profile.model_manifest_key:
            continue
        profiles.append(
            {
                "profile": profile.id,
                "runtime_profile": profile.runtime_profile,
                "task_types": list(profile.task_types),
                "model_bundles": list(profile.model_bundles),
                "required_nodes": list(profile.required_nodes),
                "workflow": profile.workflow,
                "min_vram_gb": profile.min_vram_gb,
                "image_ref": profile.image_ref,
                "all_in_one_image_ref": profile.all_in_one_image_ref,
                "model_prefix": profile.model_prefix,
                "model_manifest_key": profile.model_manifest_key,
            }
        )
    return {"profiles": sorted(profiles, key=lambda item: item["profile"])}


async def get_lan_aio_slots_payload(
    *,
    include_disabled: bool = False,
) -> dict[str, Any]:
    ops = _build_lan_aio_ops()
    slots = ops.select_slots(None, include_disabled=include_disabled)
    slot_status_by_id: dict[str, dict[str, Any]] = {}
    status_error = None
    try:
        status_payload = ops.status_payload(slots)
        for item in status_payload.get("slots", []):
            slot_payload = item.get("slot") if isinstance(item, dict) else None
            slot_id = slot_payload.get("id") if isinstance(slot_payload, dict) else None
            if slot_id:
                slot_status_by_id[str(slot_id)] = item
    except Exception as exc:
        status_error = str(exc)

    groups: dict[str, dict[str, Any]] = {}
    for slot in slots:
        slot_payload = slot_status_by_id.get(slot.id) or {
            "slot": slot_to_jsonable(slot, ops.config),
            "workers": [],
            "control": {"legacy": "unknown", "aio": "unknown"},
            "remote_containers": [],
            "model_cache": {"status": "unknown"},
        }
        key = physical_slot_key(slot)
        group = groups.setdefault(
            key,
            {
                "physical_slot_key": key,
                "node_id": slot.node_id,
                "gpu_index": slot.gpu_index,
                "slots": [],
            },
        )
        group["slots"].append(slot_payload)

    return {
        "ok": status_error is None,
        "include_disabled": include_disabled,
        "status_error": status_error,
        "groups": list(groups.values()),
        "slots": list(slot_status_by_id.values())
        if slot_status_by_id
        else [slot for group in groups.values() for slot in group["slots"]],
    }


LAN_AIO_SLOT_ACTIONS: dict[str, tuple[str, str]] = {
    "preflight": ("preflight", "lan-aio-preflight"),
    "pull-image": ("pull-image", "lan-aio-pull-image"),
    "warm-cache": ("warm-cache", "lan-aio-warm-cache"),
    "drain-legacy": ("drain-legacy", "lan-aio-drain-legacy"),
    "wait-idle": ("wait-idle", "lan-aio-wait-idle"),
    "stop-old": ("stop-old", "lan-aio-stop-old"),
    "start-disabled": ("start-disabled", "lan-aio-start-disabled"),
    "enable-aio": ("enable-aio", "lan-aio-enable"),
}


async def start_lan_aio_slot_action_payload(
    slot_id: str,
    action: str,
    request: LanAioSlotActionRequest,
    *,
    spawn_task_func=None,
) -> dict[str, Any]:
    _sync_runtime_paths()
    if action not in LAN_AIO_SLOT_ACTIONS:
        raise HTTPException(status_code=422, detail=f"unsupported LAN AIO action: {action}")
    ops = _build_lan_aio_ops()
    try:
        slot = ops.select_slots(slot_id, include_disabled=True)[0]
    except KeyError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"unknown LAN AIO slot: {slot_id}",
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    lock_key = physical_slot_key(slot)
    active_operation = await _operation_runner.active_lan_aio_operation_for_slot(
        lock_key
    )
    if active_operation is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                "LAN AIO operation is already active for physical slot "
                f"{lock_key}: {active_operation['id']}"
            ),
        )

    cli_action, operation_action = LAN_AIO_SLOT_ACTIONS[action]
    reason = request.reason or f"dashboard {operation_action}"
    operation = await _register_operation(
        action=operation_action,
        profile=slot.target_profile_id,
        command=_lan_aio_action_command(cli_action, slot.id),
        env=dict(os.environ),
        agent_id=slot.agent_id,
        slot=slot.id,
        active_lan_aio_slot=lock_key,
        trigger_reason=reason,
        spawn_task_func=spawn_task_func,
    )
    return {"status": "accepted", "operation": _operation_payload(operation)}


async def terminate_runpod_operation_payload(operation_id: str) -> dict[str, Any]:
    return await _operation_runner.terminate_operation_payload(operation_id)


async def start_runpod_scale_payload(
    request: RunPodScaleRequest,
    *,
    spawn_task_func=None,
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

    for profile, _requested_count in normalized_items:
        active_operation = await _active_add_operation_for_profile(profile)
        if active_operation is not None:
            raise HTTPException(
                status_code=409,
                detail=(
                    "RunPod add operation is already active for profile "
                    f"{profile}: {active_operation['id']}"
                ),
            )

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
            await _register_operation(
                action="add",
                profile=profile,
                command=command,
                env=env,
                requested_count=requested_count,
                active_add_profile=profile,
                source="manual",
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
