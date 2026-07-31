from __future__ import annotations

import asyncio
import calendar
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
    DEFAULT_OPERATION_LOG_LINES,
    FINISHED_OPERATION_STATUSES,
    RunPodAdminOperation,
    append_operation_log,
    can_terminate_operation_reason,
    normalized_stored_operation_payload,
    operation_payload,
    summarize_operation_failure,
)
from dashboard.backend.services.runpod_operation_store import (
    FINISHED_OPERATION_TTL_SECONDS,
    RunPodOperationStore,
)
from ops.gpu_pool_controller.providers.runpod import redact_text
from ops.gpu_pool_controller.runpod_profile_catalog import prod_agent_id_from_slot

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
    detached_reconcile_heartbeat_max_age_seconds: int = field(
        default_factory=lambda: int(
            os.getenv(
                "DASHBOARD_RUNPOD_AUTOSCALER_HEARTBEAT_MAX_AGE_SECONDS",
                "300",
            )
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

    async def release_active_lan_aio_slot_if_needed(
        self,
        operation: RunPodAdminOperation,
    ) -> None:
        if operation.active_lan_aio_slot:
            await self.store.release_active_lan_aio_slot(
                operation.active_lan_aio_slot,
                operation.id,
            )

    async def release_manual_add_slot_if_needed(
        self,
        operation: RunPodAdminOperation,
    ) -> None:
        if operation.manual_add_profile and operation.slot:
            await self.store.release_manual_add_slot(
                operation.manual_add_profile,
                operation.slot,
                operation.id,
            )

    async def release_active_locks_if_needed(
        self,
        operation: RunPodAdminOperation,
    ) -> None:
        await self.release_active_add_if_needed(operation)
        await self.release_active_lan_aio_slot_if_needed(operation)
        await self.release_manual_add_slot_if_needed(operation)

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

    @staticmethod
    def _stored_operation_created_at(
        payload: dict[str, Any],
        *,
        fallback: float,
    ) -> float:
        raw = payload.get("created_at")
        if isinstance(raw, (int, float)):
            return float(raw)
        if isinstance(raw, str) and raw:
            try:
                return float(calendar.timegm(time.strptime(raw, "%Y-%m-%dT%H:%M:%SZ")))
            except ValueError:
                pass
        return fallback

    def _detached_add_ready_agents(
        self,
        payload: dict[str, Any],
        *,
        workers_by_agent: dict[str, dict[str, Any]],
        now: float,
    ) -> list[str] | None:
        operation_id = str(payload.get("id") or "")
        if (
            not operation_id
            or operation_id in self.operations
            or payload.get("action") != "add"
            or payload.get("status") != "running"
            or payload.get("terminate_requested")
        ):
            return None
        slots = [str(slot) for slot in payload.get("cleanup_slots") or [] if str(slot)]
        try:
            requested_count = int(payload.get("requested_count") or len(slots))
        except (TypeError, ValueError):
            return None
        if not slots or len(slots) < requested_count:
            return None
        profile = str(payload.get("profile") or "")
        try:
            agent_ids = [
                prod_agent_id_from_slot(slot, profile=profile) for slot in slots
            ]
        except ValueError:
            return None
        for agent_id in agent_ids:
            worker = workers_by_agent.get(agent_id)
            if not worker:
                return None
            if str(worker.get("provider") or "").strip().lower() != "runpod":
                return None
            if str(worker.get("status") or "").strip().lower() not in {
                "idle",
                "running",
            }:
                return None
            control_state = (
                str(worker.get("control_state") or "enabled").strip().lower()
            )
            if control_state != "enabled":
                return None
            try:
                last_seen = float(worker.get("last_seen"))
            except (TypeError, ValueError):
                return None
            heartbeat_age = now - last_seen
            if not (
                0 <= heartbeat_age <= self.detached_reconcile_heartbeat_max_age_seconds
            ):
                return None
        return agent_ids

    async def _reconcile_detached_add_operations(
        self,
        stored_payloads: list[dict[str, Any]],
        *,
        workers_payload: dict[str, Any],
        now: float,
    ) -> list[dict[str, Any]]:
        workers_by_agent = {
            str(worker.get("agent_id") or ""): worker
            for worker in workers_payload.get("workers") or []
            if isinstance(worker, dict) and worker.get("agent_id")
        }
        reconciled: list[dict[str, Any]] = []
        for original in stored_payloads:
            payload = dict(original)
            ready_agents = self._detached_add_ready_agents(
                payload,
                workers_by_agent=workers_by_agent,
                now=now,
            )
            if ready_agents is None:
                reconciled.append(payload)
                continue
            payload["status"] = "succeeded"
            payload["ended_at"] = time.strftime(
                "%Y-%m-%dT%H:%M:%SZ",
                time.gmtime(now),
            )
            payload["exit_code"] = 0
            payload["error"] = None
            log_tail = list(payload.get("log_tail") or [])
            log_tail.append(
                "[dashboard-runpod] reconciled detached add: expected worker is healthy"
            )
            payload["log_tail"] = log_tail[-DEFAULT_OPERATION_LOG_LINES:]
            created_at = self._stored_operation_created_at(payload, fallback=now)
            await self.store.save_operation(
                payload,
                created_at=created_at,
                ttl_seconds=FINISHED_OPERATION_TTL_SECONDS,
            )
            operation_id = str(payload.get("id") or "")
            manual_add_profile = str(payload.get("manual_add_profile") or "")
            slot = str(payload.get("slot") or "")
            if manual_add_profile and slot:
                await self.store.release_manual_add_slot(
                    manual_add_profile, slot, operation_id
                )
            else:
                await self.store.release_active_add(
                    str(payload.get("profile") or ""), operation_id
                )
            self.logger.info(
                "Reconciled detached RunPod add operation %s with healthy agents %s",
                payload.get("id"),
                ",".join(ready_agents),
            )
            reconciled.append(payload)
        return reconciled

    async def operations_payload(
        self,
        *,
        workers_payload: dict[str, Any] | None = None,
        now: float | None = None,
    ) -> dict[str, Any]:
        stored_payloads = await self.store.list_operations(
            limit=self.max_operation_records
        )
        if workers_payload is not None:
            stored_payloads = await self._reconcile_detached_add_operations(
                stored_payloads,
                workers_payload=workers_payload,
                now=time.time() if now is None else float(now),
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
        operations.extend(
            operation_payload(operation) for operation in local_only_operations
        )

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
            await self.release_active_locks_if_needed(operation)
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
        active_lan_aio_slot: str | None = None,
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
            active_lan_aio_slot=active_lan_aio_slot,
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
        if active_lan_aio_slot is not None:
            acquired = await self.store.acquire_active_lan_aio_slot(
                active_lan_aio_slot,
                operation.id,
            )
            if not acquired:
                active_operation_id = await self.store.get_active_lan_aio_slot(
                    active_lan_aio_slot
                )
                if active_add_profile is not None:
                    await self.store.release_active_add(
                        active_add_profile,
                        operation.id,
                    )
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "LAN AIO operation is already active for physical slot "
                        f"{active_lan_aio_slot}: {active_operation_id}"
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

    async def register_manual_add_batch(
        self,
        *,
        profile: str,
        batch_id: str,
        specs: list[dict[str, Any]],
        env: dict[str, str],
        spawn_task_func=None,
    ) -> list[RunPodAdminOperation]:
        operations = [
            RunPodAdminOperation(
                id=uuid.uuid4().hex,
                action="add",
                profile=profile,
                command=list(spec["command"]),
                requested_count=1,
                agent_id=str(spec["agent_id"]),
                slot=str(spec["slot"]),
                batch_id=batch_id,
                manual_add_profile=profile,
                source="manual",
            )
            for spec in specs
        ]
        reservations = {str(operation.slot): operation.id for operation in operations}
        acquired = await self.store.reserve_manual_add_slots(profile, reservations)
        if not acquired:
            raise HTTPException(
                status_code=409,
                detail=f"RunPod manual add slots changed while planning profile {profile}",
            )

        try:
            for operation in operations:
                self.operations[operation.id] = operation
                await self.persist_operation(operation)
        except Exception:
            for operation in operations:
                self.operations.pop(operation.id, None)
                await self.store.release_manual_add_slot(
                    profile, str(operation.slot), operation.id
                )
            raise

        self.prune_operations()
        task_factory = spawn_task_func or asyncio.create_task
        for operation in operations:
            coroutine = self.run_operation(
                operation.id,
                command=operation.command,
                env=env,
            )
            task = task_factory(coroutine)
            if task is None:
                coroutine.close()
            if isinstance(task, asyncio.Task):
                self.operation_tasks.add(task)
                task.add_done_callback(self.operation_tasks.discard)
        return operations

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
            await self.release_active_locks_if_needed(operation)
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
                    operation.error = summarize_operation_failure(operation)
                    if (
                        operation.action == "add"
                        and operation.cleanup_slots
                        and (
                            operation.source == "autoscaler"
                            or operation.manual_add_profile is not None
                        )
                    ):
                        append_operation_log(
                            operation,
                            "[dashboard-runpod] add failed after "
                            "creating RunPod slot; cleanup started",
                        )
                        cleanup_ok = await self.run_termination_cleanup(
                            operation,
                            env=env,
                        )
                        if not cleanup_ok:
                            operation.error = operation.cleanup_error or operation.error
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
            await self.release_active_locks_if_needed(operation)

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
            append_operation_log(
                operation, "[dashboard-runpod] process group already exited"
            )
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
        locked_skips: list[str] = []
        for slot in cleanup_slots:
            try:
                agent_id = prod_agent_id_from_slot(
                    slot,
                    profile=operation.profile,
                    max_manual_slots=self.command_builder.default_prod_max_manual_slots(),
                )
            except ValueError:
                agent_id = ""
            if agent_id and await self.store.get_locked_runpod_worker(agent_id):
                locked_skips.append(agent_id)
                append_operation_log(
                    operation,
                    (
                        "[dashboard-runpod] cleanup down slot "
                        f"{slot} skipped: RunPod worker locked"
                    ),
                )
                await self.persist_operation(operation)
                continue
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

        if locked_skips:
            if operation.cleanup_exit_codes:
                operation.cleanup_status = "partial_locked" if cleanup_ok else "failed"
            else:
                operation.cleanup_status = "skipped_locked"
            operation.cleanup_error = (
                "cleanup skipped locked RunPod worker(s): " + ", ".join(locked_skips)
            )
        else:
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
