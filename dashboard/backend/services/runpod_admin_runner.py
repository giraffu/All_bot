from __future__ import annotations

import asyncio
import logging
import os
import signal
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from dashboard.backend.services.runpod_admin_commands import RunPodAdminCommandBuilder
from dashboard.backend.services.runpod_admin_operation import (
    FINISHED_OPERATION_STATUSES,
    RunPodAdminOperation,
    append_operation_log,
    can_terminate_operation_reason,
    normalized_stored_operation_payload,
    operation_payload,
)
from dashboard.backend.services.runpod_operation_store import (
    FINISHED_OPERATION_TTL_SECONDS,
    RunPodOperationStore,
)
from ops.gpu_pool_controller.providers.runpod import redact_text

CreateSubprocessExec = Callable[..., Awaitable[Any]]
KillProcessGroup = Callable[[int, int], None]


@dataclass
class RunPodAdminOperationRunner:
    store: RunPodOperationStore
    command_builder: RunPodAdminCommandBuilder
    project_root: Path
    logger: logging.Logger
    create_subprocess_exec: CreateSubprocessExec | None = None
    kill_process_group: KillProcessGroup | None = None
    operations: dict[str, RunPodAdminOperation] = field(default_factory=dict)
    operation_tasks: set[asyncio.Task] = field(default_factory=set)
    max_operation_records: int = field(
        default_factory=lambda: int(
            os.getenv("DASHBOARD_RUNPOD_MAX_OPERATION_RECORDS", "100")
        )
    )

    def set_store(self, store: RunPodOperationStore) -> None:
        self.store = store

    async def persist_operation(self, operation: RunPodAdminOperation) -> None:
        ttl_seconds = (
            FINISHED_OPERATION_TTL_SECONDS
            if operation.status in FINISHED_OPERATION_STATUSES
            else None
        )
        await self.store.save_operation(
            operation_payload(operation),
            created_at=operation.created_at,
            ttl_seconds=ttl_seconds,
        )
        await self.store.prune_operations(max_records=self.max_operation_records)

    async def release_active_add_if_needed(
        self,
        operation: RunPodAdminOperation,
    ) -> None:
        if operation.active_add_profile:
            await self.store.release_active_add(
                operation.active_add_profile,
                operation.id,
            )

    async def active_add_operation_for_profile(
        self,
        profile: str,
    ) -> dict[str, Any] | None:
        for operation in self.operations.values():
            if (
                operation.action == "add"
                and operation.profile == profile
                and operation.status not in FINISHED_OPERATION_STATUSES
            ):
                return operation_payload(operation)

        active_operation_id = await self.store.get_active_add(profile)
        if not active_operation_id:
            return None
        payload = await self.store.get_operation(active_operation_id)
        if payload is None:
            await self.store.release_active_add(profile, active_operation_id)
            return None
        if payload.get("status") in FINISHED_OPERATION_STATUSES:
            await self.store.release_active_add(profile, active_operation_id)
            return None
        return normalized_stored_operation_payload(payload)

    def prune_operations(self) -> None:
        if self.max_operation_records <= 0:
            return
        if len(self.operations) <= self.max_operation_records:
            return
        finished = [
            operation
            for operation in self.operations.values()
            if operation.status in FINISHED_OPERATION_STATUSES
        ]
        finished.sort(key=lambda item: item.ended_at or item.created_at)
        overflow = len(self.operations) - self.max_operation_records
        for operation in finished[:overflow]:
            self.operations.pop(operation.id, None)

    async def operations_payload(self) -> dict[str, Any]:
        stored_payloads = await self.store.list_operations(
            limit=self.max_operation_records
        )
        operations: list[dict[str, Any]] = []
        seen_operation_ids: set[str] = set()
        for payload in stored_payloads:
            operation_id = str(payload.get("id") or "")
            local_operation = self.operations.get(operation_id)
            if local_operation is not None:
                operations.append(operation_payload(local_operation))
            else:
                operations.append(normalized_stored_operation_payload(payload))
            seen_operation_ids.add(operation_id)

        local_only_operations = [
            operation
            for operation in self.operations.values()
            if operation.id not in seen_operation_ids
        ]
        local_only_operations.sort(key=lambda item: item.created_at, reverse=True)
        operations.extend(operation_payload(operation) for operation in local_only_operations)

        return {
            "operations": operations,
            "count": len(operations),
        }

    async def terminate_operation_payload(self, operation_id: str) -> dict[str, Any]:
        operation = self.operations.get(operation_id)
        if operation is None:
            stored_operation = await self.store.get_operation(operation_id)
            if stored_operation is not None:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "RunPod operation is detached from this Dashboard process; "
                        "refusing to terminate by PID"
                    ),
                )
            raise HTTPException(status_code=404, detail="RunPod operation not found")

        if operation.terminate_requested:
            return {"status": "accepted", "operation": operation_payload(operation)}

        can_terminate_reason = can_terminate_operation_reason(operation)
        if can_terminate_reason is not None:
            raise HTTPException(status_code=409, detail=can_terminate_reason)

        operation.terminate_requested = True
        append_operation_log(operation, "[dashboard-runpod] terminate requested")

        if operation.process is not None:
            operation.status = "terminating"
            operation.cleanup_status = operation.cleanup_status or "pending"
            self.terminate_process_group(operation)
        elif operation.status == "pending":
            operation.status = "terminated"
            operation.cleanup_status = "skipped"
            operation.ended_at = time.time()
            append_operation_log(
                operation,
                "[dashboard-runpod] operation terminated before process start",
            )
        else:
            operation.status = "terminating"

        await self.persist_operation(operation)
        if operation.status in FINISHED_OPERATION_STATUSES:
            await self.release_active_add_if_needed(operation)
        return {"status": "accepted", "operation": operation_payload(operation)}

    async def register_operation(
        self,
        *,
        action: str,
        profile: str,
        command: list[str],
        env: dict[str, str],
        requested_count: int | None = None,
        agent_id: str | None = None,
        slot: str | None = None,
        active_add_profile: str | None = None,
        source: str = "manual",
        trigger_reason: str | None = None,
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
            active_add_profile=active_add_profile,
            source=source,
            trigger_reason=trigger_reason,
        )
        if active_add_profile is not None:
            acquired = await self.store.acquire_active_add(
                active_add_profile,
                operation.id,
            )
            if not acquired:
                active_operation_id = await self.store.get_active_add(
                    active_add_profile
                )
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "RunPod add operation is already active for profile "
                        f"{active_add_profile}: {active_operation_id}"
                    ),
                )

        self.operations[operation.id] = operation
        self.prune_operations()
        await self.persist_operation(operation)
        coroutine = self.run_operation(operation.id, command=command, env=env)
        task_factory = spawn_task_func or asyncio.create_task
        task = task_factory(coroutine)
        if task is None:
            coroutine.close()
        if isinstance(task, asyncio.Task):
            self.operation_tasks.add(task)
            task.add_done_callback(self.operation_tasks.discard)
        return operation

    async def run_operation(
        self,
        operation_id: str,
        *,
        command: list[str],
        env: dict[str, str],
    ) -> None:
        operation = self.operations.get(operation_id)
        if operation is None:
            return
        if operation.terminate_requested:
            operation.status = "terminated"
            operation.cleanup_status = "skipped"
            operation.ended_at = time.time()
            await self.persist_operation(operation)
            await self.release_active_add_if_needed(operation)
            return
        operation.status = "running"
        operation.started_at = time.time()
        await self.persist_operation(operation)
        try:
            process = await self._create_subprocess_exec(
                *command,
                cwd=str(self.project_root),
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                start_new_session=True,
            )
            operation.process = process
            operation.pid = process.pid
            await self.persist_operation(operation)
            if operation.terminate_requested:
                operation.status = "terminating"
                self.terminate_process_group(operation)
                await self.persist_operation(operation)
            assert process.stdout is not None
            while True:
                raw = await process.stdout.readline()
                if not raw:
                    break
                append_operation_log(operation, raw.decode("utf-8", errors="replace"))
                await self.persist_operation(operation)
            operation.exit_code = await process.wait()
            await self.persist_operation(operation)
            if operation.terminate_requested:
                cleanup_ok = await self.run_termination_cleanup(operation, env=env)
                operation.status = "terminated" if cleanup_ok else "terminate_failed"
                if not cleanup_ok:
                    operation.error = operation.cleanup_error
            else:
                operation.status = "succeeded" if operation.exit_code == 0 else "failed"
                if operation.exit_code != 0:
                    operation.error = (
                        f"runpod operation exited with code {operation.exit_code}"
                    )
        except Exception as exc:
            if operation.terminate_requested:
                operation.status = "terminate_failed"
                operation.error = redact_text(str(exc))
                operation.cleanup_error = operation.error
            else:
                operation.status = "failed"
                operation.error = redact_text(str(exc))
                self.logger.exception("RunPod dashboard operation failed")
        finally:
            operation.process = None
            operation.ended_at = time.time()
            await self.persist_operation(operation)
            await self.release_active_add_if_needed(operation)

    def terminate_process_group(self, operation: RunPodAdminOperation) -> None:
        process = operation.process
        pid = int(operation.pid or getattr(process, "pid", 0) or 0)
        if process is None or pid <= 0:
            append_operation_log(
                operation, "[dashboard-runpod] no process was available to kill"
            )
            return
        try:
            self._kill_process_group(pid, signal.SIGTERM)
            append_operation_log(
                operation, f"[dashboard-runpod] sent SIGTERM to process group {pid}"
            )
        except ProcessLookupError:
            append_operation_log(operation, "[dashboard-runpod] process group already exited")
        except Exception as exc:
            append_operation_log(
                operation,
                "[dashboard-runpod] failed to kill process group: "
                f"{redact_text(str(exc))}",
            )
            try:
                process.terminate()
            except ProcessLookupError:
                pass

    async def run_termination_cleanup(
        self,
        operation: RunPodAdminOperation,
        *,
        env: dict[str, str],
    ) -> bool:
        if operation.action != "add":
            operation.cleanup_status = "skipped"
            await self.persist_operation(operation)
            return True

        cleanup_slots = list(dict.fromkeys(operation.cleanup_slots))
        if not cleanup_slots:
            operation.cleanup_status = "skipped"
            append_operation_log(
                operation,
                "[dashboard-runpod] no created RunPod slot was recorded; cleanup skipped",
            )
            await self.persist_operation(operation)
            return True

        operation.cleanup_status = "running"
        await self.persist_operation(operation)
        cleanup_ok = True
        for slot in cleanup_slots:
            command = self.command_builder.base_command(
                "down", profile=operation.profile, slot=slot
            )
            command.append("--execute")
            operation.cleanup_commands.append(command)
            append_operation_log(
                operation, f"[dashboard-runpod] cleanup down slot {slot} started"
            )
            await self.persist_operation(operation)
            exit_code = await self.run_cleanup_command(
                operation, command=command, env=env
            )
            operation.cleanup_exit_codes.append(exit_code)
            await self.persist_operation(operation)
            if exit_code != 0:
                cleanup_ok = False
                operation.cleanup_error = (
                    f"runpod cleanup down slot {slot} exited with code {exit_code}"
                )
                append_operation_log(
                    operation, f"[dashboard-runpod] cleanup down slot {slot} failed"
                )
                await self.persist_operation(operation)

        operation.cleanup_status = "succeeded" if cleanup_ok else "failed"
        await self.persist_operation(operation)
        return cleanup_ok

    async def run_cleanup_command(
        self,
        operation: RunPodAdminOperation,
        *,
        command: list[str],
        env: dict[str, str],
    ) -> int:
        process = await self._create_subprocess_exec(
            *command,
            cwd=str(self.project_root),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=True,
        )
        assert process.stdout is not None
        while True:
            raw = await process.stdout.readline()
            if not raw:
                break
            append_operation_log(operation, raw.decode("utf-8", errors="replace"))
            await self.persist_operation(operation)
        return await process.wait()

    async def _create_subprocess_exec(self, *args, **kwargs):
        create_subprocess_exec = (
            self.create_subprocess_exec or asyncio.create_subprocess_exec
        )
        return await create_subprocess_exec(*args, **kwargs)

    def _kill_process_group(self, pid: int, sig: int) -> None:
        kill_process_group = self.kill_process_group or os.killpg
        kill_process_group(pid, sig)
