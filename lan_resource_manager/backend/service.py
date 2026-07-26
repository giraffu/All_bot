from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from .config import Settings
from .models import OperationStatus, SwitchRequest
from .operator import OperatorError, OperatorPort
from .store import OperationStore, utc_now


class FleetService:
    def __init__(
        self,
        settings: Settings,
        operator: OperatorPort,
        store: OperationStore,
        runtime_lock: asyncio.Lock | None = None,
    ):
        self.settings = settings
        self.operator = operator
        self.store = store
        self._task: asyncio.Task | None = None
        self._lock = runtime_lock or asyncio.Lock()

    async def fleet(self) -> dict[str, Any]:
        catalog, ledger = await asyncio.gather(
            self.operator.list_slots(), self.operator.read_ledger()
        )
        snapshot = self.store.load_snapshot()
        slots = catalog.get("slots") or []
        by_physical: dict[str, list[dict[str, Any]]] = {}
        for slot in slots:
            by_physical.setdefault(slot["physical_slot_key"], []).append(slot)

        live_rows = {}
        if snapshot:
            for row in snapshot.get("payload", {}).get("slots") or []:
                live_rows[row["slot"]["id"]] = row
        ledger_slots = ledger.get("physical_slots") or {}
        physical_slots = []
        for key, candidates in sorted(by_physical.items()):
            physical = ledger_slots.get(key) or {}
            current = physical.get("current") or {}
            current_id = current.get("slot_id")
            current_live = live_rows.get(current_id) if current_id else None
            cache = {
                item.get("profile"): item
                for item in physical.get("cached_profiles") or []
            }
            candidate_rows = []
            for candidate in candidates:
                stable = (
                    candidate.get("enabled") is True
                    and candidate.get("retargetable") is True
                    and candidate.get("phase") == "catalog_ready"
                )
                candidate_rows.append(
                    {
                        "slot_id": candidate["id"],
                        "profile": candidate["target_profile_id"],
                        "phase": candidate.get("phase"),
                        "enabled": bool(candidate.get("enabled")),
                        "retargetable": bool(candidate.get("retargetable")),
                        "switchable": stable and candidate["id"] != current_id,
                        "task_types": candidate.get("target_task_types") or [],
                        "cache": cache.get(candidate["target_profile_id"]),
                        "notes": candidate.get("notes"),
                    }
                )
            worker = None
            if current_live:
                workers = current_live.get("workers") or []
                worker = workers[0] if workers else None
            physical_slots.append(
                {
                    "physical_slot": key,
                    "node_id": candidates[0]["node_id"],
                    "gpu_index": candidates[0]["gpu_index"],
                    "host_port": (current or candidates[0]).get("host_port"),
                    "current": (
                        {
                            key: current.get(key)
                            for key in (
                                "slot_id",
                                "profile",
                                "state",
                                "host_port",
                                "last_verified_at",
                            )
                            if current.get(key) is not None
                        }
                        or None
                    ),
                    "intentionally_empty": physical.get("intentionally_empty"),
                    "worker": worker,
                    "candidates": candidate_rows,
                    "blocked_observations": physical.get("blocked_observations") or [],
                    "last_verified_at": physical.get("last_verified_at"),
                }
            )

        state = (snapshot or {}).get("payload", {}).get("state") or {}
        captured_at = (snapshot or {}).get("captured_at")
        stale = True
        if captured_at:
            age = (
                datetime.now(timezone.utc)
                - datetime.fromisoformat(captured_at)
            ).total_seconds()
            stale = age > self.settings.live_stale_seconds
        return {
            "physical_slots": physical_slots,
            "state": {
                "status": state.get("status", "unknown"),
                "drift": state.get("drift") or [],
                "captured_at": captured_at,
                "stale": stale,
            },
            "active_operation": self.store.active(
                kinds={"refresh", "switch", "deploy", "maintenance"}
            ),
        }

    async def start_refresh(self) -> dict:
        async with self._lock:
            active = self.store.active(kind="refresh")
            if active:
                return active
            operation_id = f"refresh-{uuid.uuid4().hex[:12]}"
            operation = self.store.create(operation_id, kind="refresh", request={})
            self._task = asyncio.create_task(self._refresh(operation_id))
            return operation

    async def _refresh(self, operation_id: str) -> None:
        self.store.update(
            operation_id, status=OperationStatus.RUNNING, stage="live-status"
        )
        try:
            payload = await self.operator.status()
            self.store.save_snapshot({"captured_at": utc_now(), "payload": payload})
            self.store.update(
                operation_id,
                status=OperationStatus.SUCCEEDED,
                stage="completed",
            )
        except Exception:
            self.store.update(
                operation_id,
                status=OperationStatus.FAILED,
                stage="failed",
                error_code="operator_status_failed",
            )

    async def start_switch(
        self,
        node_id: str,
        gpu_index: int,
        request: SwitchRequest,
    ) -> dict:
        async with self._lock:
            if self.store.active(
                kinds={"refresh", "switch", "deploy", "maintenance"}
            ):
                raise HTTPException(409, detail="operation_in_progress")
            catalog = await self.operator.list_slots()
            physical_slot = f"{node_id}:gpu{gpu_index}"
            candidates = [
                slot
                for slot in catalog.get("slots") or []
                if slot.get("physical_slot_key") == physical_slot
            ]
            target = next(
                (
                    item
                    for item in candidates
                    if item.get("id") == request.target_slot_id
                ),
                None,
            )
            if not target:
                raise HTTPException(404, detail="target_slot_not_found")
            if not (
                target.get("enabled") is True
                and target.get("retargetable") is True
                and target.get("phase") == "catalog_ready"
            ):
                raise HTTPException(422, detail="target_slot_not_stable")
            if request.confirmation_profile != target.get("target_profile_id"):
                raise HTTPException(422, detail="confirmation_profile_mismatch")
            operation_id = f"web-switch-{uuid.uuid4().hex[:12]}"
            operation = self.store.create(
                operation_id,
                kind="switch",
                request={
                    "physical_slot": physical_slot,
                    "target_slot_id": request.target_slot_id,
                    "target_profile": target.get("target_profile_id"),
                    "expected_current_slot_id": request.expected_current_slot_id,
                },
            )
            self._task = asyncio.create_task(
                self._switch(
                    operation_id=operation_id,
                    physical_slot=physical_slot,
                    target_slot_id=request.target_slot_id,
                    expected_current_slot_id=request.expected_current_slot_id,
                )
            )
            return operation

    async def _switch(
        self,
        *,
        operation_id: str,
        physical_slot: str,
        target_slot_id: str,
        expected_current_slot_id: str | None,
    ) -> None:
        self.store.update(
            operation_id, status=OperationStatus.VALIDATING, stage="live-status"
        )
        try:
            status = await self.operator.status(target_slot_id)
            state = status.get("state") or {}
            if state.get("status") != "passed":
                self.store.update(
                    operation_id,
                    status=OperationStatus.FAILED,
                    stage="blocked",
                    error_code="fleet_state_blocked",
                )
                return
            ledger = await self.operator.read_ledger()
            physical = (ledger.get("physical_slots") or {}).get(physical_slot) or {}
            current = physical.get("current") or {}
            current_slot_id = current.get("slot_id")
            if current_slot_id != expected_current_slot_id:
                self.store.update(
                    operation_id,
                    status=OperationStatus.FAILED,
                    stage="blocked",
                    error_code="current_slot_changed",
                )
                return
            if not current_slot_id and not physical.get("intentionally_empty"):
                self.store.update(
                    operation_id,
                    status=OperationStatus.FAILED,
                    stage="blocked",
                    error_code="empty_slot_not_reconciled",
                )
                return
            if current_slot_id == target_slot_id:
                self.store.update(
                    operation_id,
                    status=OperationStatus.FAILED,
                    stage="blocked",
                    error_code="target_already_current",
                )
                return

            async def progress(stage: str) -> None:
                self.store.update(
                    operation_id,
                    status=OperationStatus.RUNNING,
                    stage=stage,
                )

            self.store.update(
                operation_id, status=OperationStatus.RUNNING, stage="executing"
            )
            await self.operator.execute_switch(
                physical_slot=physical_slot,
                target_slot_id=target_slot_id,
                current_slot_id=current_slot_id,
                operation_id=operation_id,
                progress=progress,
            )
            self.store.update(
                operation_id,
                status=OperationStatus.SUCCEEDED,
                stage="refreshing",
            )
            refreshed = await self.operator.status()
            self.store.save_snapshot({"captured_at": utc_now(), "payload": refreshed})
            self.store.update(
                operation_id,
                status=OperationStatus.SUCCEEDED,
                stage="completed",
            )
        except OperatorError as exc:
            value = str(exc).lower()
            rolled_back = "rollback completed" in value or "recovery_status=succeeded" in value
            recovery_required = "recovery_status=failed" in value
            self.store.update(
                operation_id,
                status=(
                    OperationStatus.RECOVERY_REQUIRED
                    if recovery_required
                    else OperationStatus.ROLLED_BACK
                    if rolled_back
                    else OperationStatus.FAILED
                ),
                stage="failed",
                error_code=(
                    "recovery_required"
                    if recovery_required
                    else "switch_rolled_back"
                    if rolled_back
                    else "operator_switch_failed"
                ),
            )
        except Exception:
            self.store.update(
                operation_id,
                status=OperationStatus.FAILED,
                stage="failed",
                error_code="unexpected_switch_failure",
            )

    def operation(self, operation_id: str) -> dict:
        value = self.store.get(operation_id)
        if not value:
            raise HTTPException(404, detail="operation_not_found")
        return value
