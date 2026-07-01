from __future__ import annotations

import asyncio
import json
import logging
import os
import time
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


def _lan_aio_action_command(
    action: str,
    slot_id: str,
    *,
    replacement_target_slot_id: str | None = None,
    failure_policy: str | None = None,
    physical_slot: str | None = None,
    recover_prefer: str | None = None,
) -> list[str]:
    _sync_runtime_paths()
    return _command_builder.lan_aio_action_command(
        action,
        slot_id,
        replacement_target_slot_id=replacement_target_slot_id,
        failure_policy=failure_policy,
        physical_slot=physical_slot,
        recover_prefer=recover_prefer,
    )


def _lan_aio_status_command(*, include_disabled: bool = False) -> list[str]:
    _sync_runtime_paths()
    return _command_builder.lan_aio_status_command(
        include_disabled=include_disabled,
    )


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
        "locked_workers": [
            locked[agent_id] for agent_id in sorted(locked)
        ],
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


def _build_lan_aio_ops() -> LanAioProdOps:
    _sync_runtime_paths()
    return LanAioProdOps(
        config_root=None,
        prod_env_file=Path(_lan_aio_prod_env_file()),
        aio_env_file=Path(_lan_aio_aio_env_file()),
        model_env_file=Path(_lan_aio_model_env_file()),
        remote_workers_source_dir=PROJECT_ROOT / "remote_workers",
    )


async def _lan_aio_status_payload(
    ops: LanAioProdOps,
    slots: list[Any],
    *,
    include_disabled: bool,
) -> dict[str, Any]:
    if _command_builder.lan_aio_execution_mode() != "ssh":
        return ops.status_payload(slots)

    command = _lan_aio_status_command(include_disabled=include_disabled)
    process = await _operation_runner._create_subprocess_exec(
        *command,
        cwd=str(PROJECT_ROOT),
        env=dict(os.environ),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        start_new_session=True,
    )
    assert process.stdout is not None
    output_parts: list[str] = []
    while True:
        raw = await process.stdout.readline()
        if not raw:
            break
        output_parts.append(raw.decode("utf-8", errors="replace"))
    exit_code = await process.wait()
    output = "".join(output_parts).strip()
    if exit_code != 0:
        detail = output.splitlines()[-1] if output else f"exit code {exit_code}"
        raise RuntimeError(f"LAN AIO runner status failed: {detail}")
    try:
        payload = json.loads(output)
    except json.JSONDecodeError as exc:
        json_start = output.find("{")
        if json_start < 0:
            detail = output[:500] if output else "empty output"
            raise RuntimeError(
                f"LAN AIO runner status returned invalid JSON: {detail}"
            ) from exc
        try:
            payload = json.loads(output[json_start:])
        except json.JSONDecodeError as inner_exc:
            detail = output[:500] if output else "empty output"
            raise RuntimeError(
                f"LAN AIO runner status returned invalid JSON: {detail}"
            ) from inner_exc
    if not isinstance(payload, dict):
        raise RuntimeError("LAN AIO runner status returned non-object JSON")
    return payload


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


def _lan_aio_slot_has_runtime_signal(slot_status: dict[str, Any]) -> bool:
    slot = slot_status.get("slot") if isinstance(slot_status, dict) else None
    if not isinstance(slot, dict):
        return False

    agent_id = str(slot.get("agent_id") or "")
    if agent_id:
        for worker in slot_status.get("workers") or []:
            if isinstance(worker, dict) and str(worker.get("agent_id") or "") == agent_id:
                return True

    container_name = str(slot.get("container_name") or "")
    if container_name:
        for raw_line in slot_status.get("remote_containers") or []:
            line = str(raw_line)
            if line.startswith(f"{container_name} ") and " Up " in f" {line} ":
                return True
    return False


def _parse_task_type_csv(raw: Any) -> list[str]:
    if isinstance(raw, (list, tuple)):
        return [str(item).strip() for item in raw if str(item).strip()]
    text = str(raw or "").strip()
    if not text:
        return []
    return [item.strip() for item in text.split(",") if item.strip()]


def _lan_aio_worker_for_slot(slot_status: dict[str, Any]) -> dict[str, Any] | None:
    slot = slot_status.get("slot") if isinstance(slot_status, dict) else None
    if not isinstance(slot, dict):
        return None
    agent_id = str(slot.get("agent_id") or "")
    if not agent_id:
        return None
    for worker in slot_status.get("workers") or []:
        if isinstance(worker, dict) and str(worker.get("agent_id") or "") == agent_id:
            return worker
    return None


def _configured_task_types_for_slot(
    slot: dict[str, Any],
    config: Any,
) -> list[str]:
    explicit = _parse_task_type_csv(slot.get("target_task_types"))
    if explicit:
        return explicit
    profile = config.profiles.get(str(slot.get("target_profile_id") or ""))
    return list(profile.task_types) if profile else []


def _annotate_lan_aio_slot_runtime(
    slot_status: dict[str, Any],
    config: Any,
) -> None:
    slot = slot_status.get("slot") if isinstance(slot_status, dict) else None
    if not isinstance(slot, dict):
        return

    configured_profile_id = str(slot.get("target_profile_id") or "")
    configured_task_types = _configured_task_types_for_slot(slot, config)
    worker = _lan_aio_worker_for_slot(slot_status)
    live_runtime_profile = str((worker or {}).get("runtime_profile") or "").strip()
    live_types_raw = (worker or {}).get("types") or (worker or {}).get(
        "supported_task_types"
    )
    live_task_types = _parse_task_type_csv(live_types_raw)
    live_image_ref = str((worker or {}).get("image_ref") or "").strip()
    configured_image_ref = str(slot.get("all_in_one_image_ref") or "").strip()
    drift_reasons: list[str] = []

    if live_runtime_profile and live_runtime_profile != configured_profile_id:
        drift_reasons.append("profile")
    if live_image_ref and configured_image_ref and live_image_ref != configured_image_ref:
        drift_reasons.append("image")
    if live_task_types and configured_task_types and set(live_task_types) != set(
        configured_task_types
    ):
        drift_reasons.append("task_types")

    slot["configured_profile_id"] = configured_profile_id
    slot["configured_task_types"] = configured_task_types
    slot["live_runtime_profile"] = live_runtime_profile or None
    slot["live_types"] = str(live_types_raw or "") or None
    slot["live_task_types"] = live_task_types
    slot["live_image_ref"] = live_image_ref or None
    slot["runtime_drift"] = bool(drift_reasons)
    slot["runtime_drift_reasons"] = drift_reasons
    slot.setdefault("replacement_targets", [])


def _lan_aio_slot_allows_config_current(slot: dict[str, Any]) -> bool:
    if not bool(slot.get("enabled")):
        return False
    phase = str(slot.get("phase") or "").strip()
    if phase in {"maintenance_disabled", "candidate"}:
        return False
    if phase.startswith("blocked_") or phase.startswith("superseded_"):
        return False
    return phase in {"", "prod_enabled", "aio_enabled"}


def _annotate_lan_aio_runtime_current(groups: dict[str, dict[str, Any]]) -> None:
    for group in groups.values():
        slot_statuses = group.get("slots") or []
        runtime_current = [
            item for item in slot_statuses if _lan_aio_slot_has_runtime_signal(item)
        ]
        current_source = "runtime" if runtime_current else "none"
        current_items = runtime_current
        current_id_list = [
            str((item.get("slot") or {}).get("id") or "")
            for item in current_items
        ]
        current_ids = {slot_id for slot_id in current_id_list if slot_id}

        for item in slot_statuses:
            slot = item.get("slot") or {}
            slot_id = str(slot.get("id") or "")
            slot["configured_current"] = bool(slot.get("enabled"))
            slot["runtime_current"] = bool(slot_id and slot_id in current_ids)
            slot["current_source"] = current_source

        group["active_slot_id"] = next(
            (slot_id for slot_id in current_id_list if slot_id),
            None,
        )
        group["active_slot_source"] = current_source


def _parse_lan_aio_container_state(
    slot_status: dict[str, Any],
) -> dict[str, Any]:
    slot = slot_status.get("slot") if isinstance(slot_status, dict) else None
    container_name = str((slot or {}).get("container_name") or "")
    status_unavailable = None
    if not container_name:
        return {"state": "unknown"}
    for raw_line in slot_status.get("remote_containers") or []:
        line = str(raw_line)
        if line.startswith("status_unavailable:"):
            status_unavailable = line
            continue
        if not line.startswith(f"{container_name} "):
            continue
        summary = line
        if " Up " in f" {line} ":
            return {"state": "running", "summary": summary}
        lowered = line.lower()
        if "exited" in lowered:
            return {"state": "exited", "summary": summary}
        if "created" in lowered:
            return {"state": "created", "summary": summary}
        if "dead" in lowered:
            return {"state": "dead", "summary": summary}
        return {"state": "unknown", "summary": summary}
    if status_unavailable:
        return {"state": "unknown", "summary": status_unavailable}
    return {"state": "missing"}


def _switch_reason_label(reason: str) -> str:
    return reason.replace("_", " ")


def _annotate_lan_aio_switch_state(groups: dict[str, dict[str, Any]]) -> None:
    for group in groups.values():
        active_slot_id = group.get("active_slot_id")
        for slot_status in group.get("slots") or []:
            if not isinstance(slot_status, dict):
                continue
            slot = slot_status.get("slot")
            if not isinstance(slot, dict):
                continue
            container_state = _parse_lan_aio_container_state(slot_status)
            has_runtime = _lan_aio_slot_has_runtime_signal(slot_status)
            phase = str(slot.get("phase") or "")
            control = slot_status.get("control") if isinstance(slot_status.get("control"), dict) else {}
            aio_control = str((control or {}).get("aio") or "")
            cache = (
                slot_status.get("model_cache")
                if isinstance(slot_status.get("model_cache"), dict)
                else {}
            )
            cache_status = str((cache or {}).get("status") or "")
            hard_blockers: list[str] = []
            warnings: list[str] = []

            state = str(container_state.get("state") or "unknown")
            is_current = bool(slot.get("runtime_current"))
            has_active_sibling = bool(active_slot_id) and not is_current
            if has_runtime:
                live_state = "running"
            elif state in {"exited", "created", "dead"}:
                live_state = "stopped"
            elif state == "missing":
                live_state = "missing"
            else:
                live_state = "unknown"

            if is_current:
                hard_blockers.append("current_slot")
            if phase == "maintenance_disabled":
                hard_blockers.append("maintenance_disabled")
            if phase.startswith("blocked_"):
                hard_blockers.append(phase)
            if bool(slot.get("enabled")) and phase in {"prod_enabled", "aio_enabled", ""} and not has_runtime:
                if has_active_sibling:
                    warnings.append("missing_live_runtime")
                else:
                    hard_blockers.append("missing_live_runtime")
            if aio_control == "enabled" and not has_runtime:
                if has_active_sibling or (slot.get("retargetable") and not is_current):
                    warnings.append("control_enabled_without_live_runtime")
                else:
                    hard_blockers.append("control_enabled_without_live_runtime")
            if state == "running" and not has_runtime:
                hard_blockers.append("target_container_running_without_heartbeat")
            elif state in {"exited", "created", "dead"}:
                warnings.append("stale_target_container")

            selectable_targets = [
                target
                for target in slot.get("replacement_targets") or []
                if isinstance(target, dict) and target.get("selectable")
            ]
            if slot.get("retargetable") and not slot.get("runtime_current"):
                if not selectable_targets:
                    hard_blockers.append("missing_live_target")
                if cache_status in {"missing", "invalid", "unavailable", "failed"}:
                    warnings.append(f"model_cache_{cache_status}")
            elif has_active_sibling and cache_status in {
                "missing",
                "invalid",
                "unavailable",
                "failed",
            }:
                warnings.append(f"model_cache_{cache_status}")
            elif not slot.get("runtime_current"):
                if phase.startswith("superseded_"):
                    warnings.append("superseded_slot")
                elif phase == "candidate":
                    warnings.append("candidate_disabled")

            switch_blockers = list(dict.fromkeys([*hard_blockers, *warnings]))
            if hard_blockers:
                readiness = "blocked"
            elif warnings:
                readiness = "warning"
            else:
                readiness = (
                    "ready"
                    if slot.get("retargetable") or has_active_sibling
                    else "blocked"
                )

            slot["target_container_state"] = container_state
            slot["live_state"] = live_state
            slot["switch_readiness"] = readiness
            slot["switch_blockers"] = switch_blockers
            slot["switch_blocker_labels"] = [
                _switch_reason_label(reason) for reason in switch_blockers
            ]
            slot["last_failed_operation_id"] = None
            slot["recovery_status"] = None
            slot_status["target_container_state"] = container_state
            slot_status["live_state"] = live_state
            slot_status["switch_readiness"] = readiness
            slot_status["switch_blockers"] = switch_blockers


def _slot_can_be_selected_for_recover(slot: dict[str, Any]) -> bool:
    phase = str(slot.get("phase") or "").strip()
    if phase == "maintenance_disabled" or phase.startswith("blocked_"):
        return False
    if bool(slot.get("runtime_current")):
        return False
    if bool(slot.get("retargetable")):
        return True
    return bool(slot.get("enabled")) and phase in {"", "prod_enabled", "aio_enabled"}


def _recover_prefer_for_slot(slot: dict[str, Any]) -> str:
    if bool(slot.get("retargetable")) and not bool(slot.get("enabled")):
        return "candidate"
    return "old"


def _annotate_lan_aio_recover_state(groups: dict[str, dict[str, Any]]) -> None:
    for group in groups.values():
        active_slot_id = group.get("active_slot_id")
        recoverable_slot_ids: list[str] = []
        for slot_status in group.get("slots") or []:
            if not isinstance(slot_status, dict):
                continue
            slot = slot_status.get("slot")
            if not isinstance(slot, dict):
                continue

            container_state = (
                slot.get("target_container_state")
                if isinstance(slot.get("target_container_state"), dict)
                else _parse_lan_aio_container_state(slot_status)
            )
            cache = (
                slot_status.get("model_cache")
                if isinstance(slot_status.get("model_cache"), dict)
                else {}
            )
            control = (
                slot_status.get("control")
                if isinstance(slot_status.get("control"), dict)
                else {}
            )
            cache_status = str((cache or {}).get("status") or "")
            aio_control = str((control or {}).get("aio") or "")
            state = str((container_state or {}).get("state") or "unknown")
            blockers: list[str] = []
            warnings: list[str] = []

            if active_slot_id:
                blockers.append("physical_slot_has_active_runtime")
            if slot.get("runtime_current"):
                blockers.append("current_slot")
            if not _slot_can_be_selected_for_recover(slot):
                phase = str(slot.get("phase") or "").strip()
                blockers.append(phase or "not_recoverable")
            if state == "running" and not _lan_aio_slot_has_runtime_signal(slot_status):
                warnings.append("target_container_running_without_heartbeat")
            elif state in {"exited", "created", "dead"}:
                warnings.append("stale_target_container")
            elif state == "missing":
                warnings.append("target_container_missing")
            if aio_control == "enabled" and not _lan_aio_slot_has_runtime_signal(
                slot_status
            ):
                warnings.append("control_enabled_without_live_runtime")
            if cache_status in {"missing", "invalid", "unavailable", "failed"}:
                warnings.append(f"model_cache_{cache_status}")

            recover_blockers = list(dict.fromkeys([*blockers, *warnings]))
            if blockers:
                readiness = "blocked"
            elif warnings:
                readiness = "warning"
            else:
                readiness = "ready"

            slot["recover_readiness"] = readiness
            slot["recover_blockers"] = recover_blockers
            slot["recover_blocker_labels"] = [
                _switch_reason_label(reason) for reason in recover_blockers
            ]
            slot["recover_prefer"] = _recover_prefer_for_slot(slot)
            slot_status["recover_readiness"] = readiness
            slot_status["recover_blockers"] = recover_blockers
            if readiness in {"ready", "warning"}:
                slot_id = str(slot.get("id") or "")
                if slot_id:
                    recoverable_slot_ids.append(slot_id)

        group["recoverable_slot_ids"] = recoverable_slot_ids
        group["recoverable_count"] = len(recoverable_slot_ids)


def _annotate_lan_aio_replacement_targets(
    groups: dict[str, dict[str, Any]],
) -> None:
    all_statuses = [
        item
        for group in groups.values()
        for item in group.get("slots") or []
        if isinstance(item, dict) and isinstance(item.get("slot"), dict)
    ]
    current_by_node: dict[str, list[dict[str, Any]]] = {}
    for item in all_statuses:
        slot = item["slot"]
        if not slot.get("runtime_current"):
            continue
        node_id = str(slot.get("node_id") or "")
        if node_id:
            current_by_node.setdefault(node_id, []).append(item)

    for item in all_statuses:
        slot = item["slot"]
        slot["replacement_targets"] = []
        if slot.get("runtime_current") or not slot.get("retargetable"):
            continue

        candidate_profile = str(
            slot.get("configured_profile_id") or slot.get("target_profile_id") or ""
        )
        node_id = str(slot.get("node_id") or "")
        for target_item in current_by_node.get(node_id, []):
            target_slot = target_item["slot"]
            if target_slot.get("id") == slot.get("id"):
                continue
            target_profile = str(target_slot.get("live_runtime_profile") or "")
            disabled_reason = None
            if not target_profile:
                disabled_reason = "missing_live_profile"
            elif target_profile == candidate_profile:
                disabled_reason = "same_profile"
            slot["replacement_targets"].append(
                {
                    "slot_id": target_slot.get("id"),
                    "physical_slot_key": target_slot.get("physical_slot_key"),
                    "node_id": target_slot.get("node_id"),
                    "gpu_index": target_slot.get("gpu_index"),
                    "host_port": target_slot.get("host_port"),
                    "live_runtime_profile": target_slot.get("live_runtime_profile"),
                    "configured_profile_id": target_slot.get("configured_profile_id"),
                    "selectable": disabled_reason is None,
                    "disabled_reason": disabled_reason,
                }
            )


async def get_lan_aio_slots_payload(
    *,
    include_disabled: bool = False,
) -> dict[str, Any]:
    ops = _build_lan_aio_ops()
    slots = ops.select_slots(None, include_disabled=include_disabled)
    slot_status_by_id: dict[str, dict[str, Any]] = {}
    status_error = None
    try:
        status_payload = await _lan_aio_status_payload(
            ops,
            slots,
            include_disabled=include_disabled,
        )
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

    for group in groups.values():
        for slot_status in group.get("slots") or []:
            _annotate_lan_aio_slot_runtime(slot_status, ops.config)
    _annotate_lan_aio_runtime_current(groups)
    _annotate_lan_aio_replacement_targets(groups)
    _annotate_lan_aio_switch_state(groups)
    _annotate_lan_aio_recover_state(groups)

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
    "takeover": ("takeover", "lan-aio-takeover"),
    "stop-old": ("stop-old", "lan-aio-stop-old"),
    "start-disabled": ("start-disabled", "lan-aio-start-disabled"),
    "enable-aio": ("enable-aio", "lan-aio-enable"),
    "recover": ("recover", "lan-aio-recover"),
}


def _lan_aio_recover_status_or_422(
    ops: LanAioProdOps,
    slot: Any,
) -> dict[str, Any]:
    lock_key = physical_slot_key(slot)
    all_slots = getattr(ops, "slots", {}) or {}
    sibling_slots = [
        candidate
        for candidate in all_slots.values()
        if physical_slot_key(candidate) == lock_key
    ]
    if not sibling_slots:
        sibling_slots = [slot]
    try:
        status_payload = ops.status_payload(sibling_slots)
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"failed to verify LAN AIO recover readiness: {exc}",
        ) from exc

    status_by_id: dict[str, dict[str, Any]] = {}
    for item in status_payload.get("slots", []):
        slot_payload = item.get("slot") if isinstance(item, dict) else None
        item_slot_id = slot_payload.get("id") if isinstance(slot_payload, dict) else None
        if item_slot_id:
            status_by_id[str(item_slot_id)] = item

    groups: dict[str, dict[str, Any]] = {}
    for sibling in sibling_slots:
        slot_status = status_by_id.get(sibling.id) or {
            "slot": slot_to_jsonable(sibling, ops.config),
            "workers": [],
            "control": {"legacy": "unknown", "aio": "unknown"},
            "remote_containers": [],
            "model_cache": {"status": "unknown"},
        }
        group = groups.setdefault(
            physical_slot_key(sibling),
            {
                "physical_slot_key": physical_slot_key(sibling),
                "node_id": sibling.node_id,
                "gpu_index": sibling.gpu_index,
                "slots": [],
            },
        )
        group["slots"].append(slot_status)

    for group in groups.values():
        for slot_status in group.get("slots") or []:
            _annotate_lan_aio_slot_runtime(slot_status, ops.config)
    _annotate_lan_aio_runtime_current(groups)
    _annotate_lan_aio_replacement_targets(groups)
    _annotate_lan_aio_switch_state(groups)
    _annotate_lan_aio_recover_state(groups)

    group = groups.get(lock_key) or {}
    selected_status = next(
        (
            item
            for item in group.get("slots") or []
            if str((item.get("slot") or {}).get("id") or "") == slot.id
        ),
        None,
    )
    selected_slot = (selected_status or {}).get("slot") or {}
    if not selected_status or selected_slot.get("recover_readiness") == "blocked":
        labels = selected_slot.get("recover_blocker_labels") or selected_slot.get(
            "recover_blockers"
        ) or []
        detail = " / ".join(str(label) for label in labels) or "not recoverable"
        raise HTTPException(
            status_code=422,
            detail=f"LAN AIO recover blocked for {slot.id}: {detail}",
        )
    return selected_status


def _lan_aio_status_by_slot_id_or_422(
    ops: LanAioProdOps,
    slots: list[Any],
    *,
    context: str,
) -> dict[str, dict[str, Any]]:
    status_by_id: dict[str, dict[str, Any]] = {}
    try:
        status_payload = ops.status_payload(slots)
        for item in status_payload.get("slots", []):
            slot_payload = item.get("slot") if isinstance(item, dict) else None
            item_slot_id = (
                slot_payload.get("id") if isinstance(slot_payload, dict) else None
            )
            if item_slot_id:
                _annotate_lan_aio_slot_runtime(item, ops.config)
                status_by_id[str(item_slot_id)] = item
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"failed to verify LAN AIO {context}: {exc}",
        ) from exc
    return status_by_id


def _validate_lan_aio_replacement_target_or_422(
    ops: LanAioProdOps,
    slot: Any,
    replacement_target: Any,
) -> dict[str, Any]:
    if replacement_target.id == slot.id:
        raise HTTPException(
            status_code=422,
            detail="replacement target must be different from the candidate slot",
        )
    if replacement_target.node_id != slot.node_id:
        raise HTTPException(
            status_code=422,
            detail="replacement target must be on the same GPU node",
        )

    status_by_id = _lan_aio_status_by_slot_id_or_422(
        ops,
        [slot, replacement_target],
        context="replacement target runtime",
    )
    replacement_target_status = status_by_id.get(replacement_target.id)
    if not replacement_target_status or not _lan_aio_slot_has_runtime_signal(
        replacement_target_status
    ):
        raise HTTPException(
            status_code=422,
            detail=f"replacement target is not a current running slot: {replacement_target.id}",
        )
    target_slot_payload = replacement_target_status.get("slot") or {}
    target_live_profile = str(target_slot_payload.get("live_runtime_profile") or "")
    if not target_live_profile:
        raise HTTPException(
            status_code=422,
            detail=(
                "replacement target has no live runtime profile: "
                f"{replacement_target.id}"
            ),
        )
    if target_live_profile == slot.target_profile_id:
        raise HTTPException(
            status_code=422,
            detail=(
                "replacement target already runs the candidate profile: "
                f"{target_live_profile}"
            ),
        )
    return replacement_target_status


def _infer_lan_aio_replacement_target_or_422(
    ops: LanAioProdOps,
    slot: Any,
) -> Any:
    all_slots = list((getattr(ops, "slots", {}) or {}).values())
    if not all_slots:
        all_slots = ops.select_slots(None, include_disabled=True)
    same_node_slots = [
        candidate
        for candidate in all_slots
        if candidate.id != slot.id and candidate.node_id == slot.node_id
    ]
    status_by_id = _lan_aio_status_by_slot_id_or_422(
        ops,
        [slot, *same_node_slots],
        context="replacement target runtime",
    )
    eligible_targets: list[Any] = []
    for candidate in same_node_slots:
        status = status_by_id.get(candidate.id)
        if not status or not _lan_aio_slot_has_runtime_signal(status):
            continue
        target_slot_payload = status.get("slot") or {}
        target_live_profile = str(target_slot_payload.get("live_runtime_profile") or "")
        if not target_live_profile or target_live_profile == slot.target_profile_id:
            continue
        eligible_targets.append(candidate)

    same_physical_targets = [
        candidate
        for candidate in eligible_targets
        if physical_slot_key(candidate) == physical_slot_key(slot)
    ]
    if len(same_physical_targets) == 1:
        return same_physical_targets[0]
    if len(same_physical_targets) > 1:
        ids = ", ".join(candidate.id for candidate in same_physical_targets)
        raise HTTPException(
            status_code=422,
            detail=(
                "multiple same-physical LAN AIO replacement targets are live; "
                f"choose one explicitly: {ids}"
            ),
        )
    if len(eligible_targets) == 1:
        return eligible_targets[0]
    if len(eligible_targets) > 1:
        ids = ", ".join(candidate.id for candidate in eligible_targets)
        raise HTTPException(
            status_code=422,
            detail=(
                "multiple LAN AIO replacement targets are live; choose one "
                f"explicitly: {ids}"
            ),
        )
    raise HTTPException(
        status_code=422,
        detail=f"no current running replacement target found for {slot.id}",
    )


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
    if request.failure_policy not in {"auto_rollback", "none"}:
        raise HTTPException(
            status_code=422,
            detail=f"unsupported LAN AIO failure_policy: {request.failure_policy}",
        )
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

    slot_phase = str(getattr(slot, "phase", "") or "")
    if action == "takeover" and (
        slot_phase == "maintenance_disabled" or slot_phase.startswith("blocked_")
    ):
        raise HTTPException(
            status_code=422,
            detail=f"LAN AIO slot is not available for takeover: {slot.id} phase={slot_phase}",
        )

    replacement_target_slot_id = (request.replacement_target_slot_id or "").strip()
    replacement_target = None
    if replacement_target_slot_id and action != "takeover":
        raise HTTPException(
            status_code=422,
            detail="replacement_target_slot_id is only supported for takeover",
        )
    if (replacement_target_slot_id or action == "takeover") and slot.retargetable:
        if replacement_target_slot_id:
            try:
                replacement_target = ops.select_slots(
                    replacement_target_slot_id,
                    include_disabled=True,
                )[0]
            except KeyError as exc:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "unknown LAN AIO replacement target slot: "
                        f"{replacement_target_slot_id}"
                    ),
                ) from exc
        else:
            replacement_target = _infer_lan_aio_replacement_target_or_422(
                ops,
                slot,
            )
        _validate_lan_aio_replacement_target_or_422(
            ops,
            slot,
            replacement_target,
        )
    elif replacement_target_slot_id:
        if not slot.retargetable:
            raise HTTPException(
                status_code=422,
                detail=f"LAN AIO slot is not retargetable: {slot.id}",
            )

    lock_key = physical_slot_key(replacement_target or slot)
    recover_prefer = None
    if action == "recover":
        recover_status = _lan_aio_recover_status_or_422(ops, slot)
        recover_slot = recover_status.get("slot") or {}
        recover_prefer = str(recover_slot.get("recover_prefer") or "old")

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
    if replacement_target is not None:
        reason = f"{reason}; replace {replacement_target.id}"
    if action == "recover":
        reason = f"{reason}; recover {lock_key} prefer {recover_prefer or 'old'}"
    operation = await _register_operation(
        action=operation_action,
        profile=slot.target_profile_id,
        command=_lan_aio_action_command(
            cli_action,
            slot.id,
            replacement_target_slot_id=(
                replacement_target.id if replacement_target is not None else None
            ),
            failure_policy=request.failure_policy,
            physical_slot=lock_key if action == "recover" else None,
            recover_prefer=recover_prefer,
        ),
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
