from __future__ import annotations

import json
import os
import re
import socket
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from ops.gpu_pool_controller.providers.runpod import redact_text

DEFAULT_OPERATION_LOG_LINES = int(
    os.getenv("DASHBOARD_RUNPOD_OPERATION_LOG_LINES", "160")
)
FINISHED_OPERATION_STATUSES = {
    "succeeded",
    "failed",
    "terminated",
    "terminate_failed",
}
TERMINABLE_OPERATION_STATUSES = {"pending", "running", "terminating"}
RUNPOD_OPERATION_OWNER_ID = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex}"
RUNPOD_CREATE_SLOT_LOG_RE = re.compile(
    r"\brunpod_create_pod_(?P<slot>\d+):\s*(?:running|ok)\b"
)


@dataclass
class RunPodAdminOperation:
    id: str
    action: str
    profile: str
    command: list[str]
    created_at: float = field(default_factory=time.time)
    owner_id: str = field(default_factory=lambda: RUNPOD_OPERATION_OWNER_ID)
    requested_count: int | None = None
    agent_id: str | None = None
    slot: str | None = None
    status: str = "pending"
    started_at: float | None = None
    ended_at: float | None = None
    pid: int | None = None
    exit_code: int | None = None
    error: str | None = None
    terminate_requested: bool = False
    cleanup_slots: list[str] = field(default_factory=list)
    cleanup_status: str | None = None
    cleanup_error: str | None = None
    cleanup_commands: list[list[str]] = field(default_factory=list)
    cleanup_exit_codes: list[int] = field(default_factory=list)
    log_lines: list[str] = field(default_factory=list)
    active_add_profile: str | None = None
    active_lan_aio_slot: str | None = None
    source: str = "manual"
    trigger_reason: str | None = None
    process: Any | None = field(default=None, repr=False)


def now_iso(timestamp: float | None) -> str | None:
    if timestamp is None:
        return None
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(timestamp))


def redacted_command(command: list[str]) -> list[str]:
    return [redact_text(str(part)) for part in command]


def append_operation_log(operation: RunPodAdminOperation, line: str) -> None:
    clean = redact_text(line.rstrip())
    if not clean:
        return
    record_cleanup_slots_from_log(operation, clean)
    operation.log_lines.append(clean)
    if len(operation.log_lines) > DEFAULT_OPERATION_LOG_LINES:
        operation.log_lines = operation.log_lines[-DEFAULT_OPERATION_LOG_LINES:]


def record_cleanup_slots_from_log(
    operation: RunPodAdminOperation,
    line: str,
) -> None:
    if operation.action != "add":
        return
    for match in RUNPOD_CREATE_SLOT_LOG_RE.finditer(line):
        slot = f"{int(match.group('slot')):02d}"
        if slot not in operation.cleanup_slots:
            operation.cleanup_slots.append(slot)


def operation_attached(
    operation: RunPodAdminOperation,
    *,
    owner_id: str = RUNPOD_OPERATION_OWNER_ID,
) -> bool:
    return operation.owner_id == owner_id and operation.process is not None


def can_terminate_operation(
    operation: RunPodAdminOperation,
    *,
    owner_id: str = RUNPOD_OPERATION_OWNER_ID,
) -> bool:
    return can_terminate_operation_reason(operation, owner_id=owner_id) is None


def can_terminate_operation_reason(
    operation: RunPodAdminOperation,
    *,
    owner_id: str = RUNPOD_OPERATION_OWNER_ID,
) -> str | None:
    if operation.action != "add":
        return "only RunPod add operations can be terminated"
    if operation.status not in TERMINABLE_OPERATION_STATUSES:
        return f"RunPod operation is already {operation.status}"
    if operation.terminate_requested:
        return "termination already requested"
    if operation.status != "pending" and not operation_attached(
        operation, owner_id=owner_id
    ):
        return "operation is detached from this Dashboard process"
    return None


def operation_payload(
    operation: RunPodAdminOperation,
    *,
    owner_id: str = RUNPOD_OPERATION_OWNER_ID,
    log_lines: int = DEFAULT_OPERATION_LOG_LINES,
) -> dict[str, Any]:
    can_terminate_reason = can_terminate_operation_reason(
        operation, owner_id=owner_id
    )
    return {
        "id": operation.id,
        "action": operation.action,
        "profile": operation.profile,
        "owner_id": operation.owner_id,
        "attached": operation_attached(operation, owner_id=owner_id),
        "requested_count": operation.requested_count,
        "agent_id": operation.agent_id,
        "slot": operation.slot,
        "status": operation.status,
        "created_at": now_iso(operation.created_at),
        "started_at": now_iso(operation.started_at),
        "ended_at": now_iso(operation.ended_at),
        "pid": operation.pid,
        "exit_code": operation.exit_code,
        "error": operation.error,
        "terminate_requested": operation.terminate_requested,
        "can_terminate": can_terminate_reason is None,
        "can_terminate_reason": can_terminate_reason,
        "cleanup_slots": list(operation.cleanup_slots),
        "cleanup_status": operation.cleanup_status,
        "cleanup_error": operation.cleanup_error,
        "cleanup_commands": [
            redacted_command(command) for command in operation.cleanup_commands
        ],
        "cleanup_exit_codes": list(operation.cleanup_exit_codes),
        "log_tail": list(operation.log_lines[-log_lines:]),
        "command": redacted_command(operation.command),
        "active_lan_aio_slot": operation.active_lan_aio_slot,
        "source": operation.source,
        "trigger_reason": operation.trigger_reason,
    }


def _lan_aio_failed_checks_from_payload(payload: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for slot_result in payload.get("slots") or []:
        if not isinstance(slot_result, dict):
            continue
        slot = str(slot_result.get("slot") or "unknown-slot")
        for check in slot_result.get("checks") or []:
            if not isinstance(check, dict) or check.get("ok") is not False:
                continue
            name = str(check.get("name") or "unknown_check")
            detail = str(check.get("error") or check.get("output") or "failed")
            if name == "docker_registry_or_image_present":
                flags = []
                for key in (
                    "registry_configured",
                    "remote_image_present",
                    "runner_image_present",
                ):
                    if key in check:
                        flags.append(f"{key}={check.get(key)}")
                image_ref = check.get("image_ref")
                if image_ref:
                    flags.append(f"image={image_ref}")
                if flags:
                    detail = f"{detail} ({', '.join(flags)})"
            failures.append(f"{slot} {name}: {detail}")
    return failures


def summarize_operation_failure(operation: RunPodAdminOperation) -> str:
    default = f"runpod operation exited with code {operation.exit_code}"
    if not operation.action.startswith("lan-aio"):
        return default
    marker = "preflight failed "
    for line in reversed(operation.log_lines):
        if marker not in line:
            continue
        _, _, payload_text = line.partition(marker)
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError:
            return line.strip()
        failures = _lan_aio_failed_checks_from_payload(payload)
        if failures:
            return "LAN AIO preflight failed: " + "; ".join(failures[:3])
        return "LAN AIO preflight failed"
    for line in reversed(operation.log_lines):
        if "RuntimeError:" in line:
            return line.split("RuntimeError:", 1)[1].strip()
    return default


def normalized_stored_operation_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    normalized.setdefault("owner_id", "")
    normalized.setdefault("source", "manual")
    normalized.setdefault("trigger_reason", None)
    normalized["attached"] = False
    action = normalized.get("action")
    status = normalized.get("status")
    terminate_requested = bool(normalized.get("terminate_requested"))
    if action != "add":
        reason = "only RunPod add operations can be terminated"
    elif status not in TERMINABLE_OPERATION_STATUSES:
        reason = f"RunPod operation is already {status}"
    elif terminate_requested:
        reason = "termination already requested"
    else:
        reason = "operation is detached from this Dashboard process"
    normalized["can_terminate"] = False
    normalized["can_terminate_reason"] = reason
    return normalized
