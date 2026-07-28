from __future__ import annotations

import asyncio
import re
import uuid

from fastapi import HTTPException

from .models import (
    ModuleBuildRequest,
    ModuleDeployRequest,
    OperationStatus,
    WorkspaceSelectionRequest,
)
from .release_operator import ReleaseOperatorError, ReleaseOperatorPort
from .store import OperationStore


MODULE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,79}$")


class DeploymentService:
    def __init__(
        self,
        operator: ReleaseOperatorPort,
        store: OperationStore,
        _data_dir,
        runtime_lock: asyncio.Lock,
    ):
        self.operator = operator
        self.store = store
        self.runtime_lock = runtime_lock
        self.tasks: set[asyncio.Task] = set()

    def _spawn(self, coroutine) -> None:
        task = asyncio.create_task(coroutine)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    def _available(self) -> bool:
        return not self.runtime_lock.locked() and not self.store.active(
            kinds={
                "switch",
                "workspace-integrate",
                "workspace-align",
                "module-build",
                "module-deploy",
            }
        )

    async def catalog(self):
        try:
            return await self.operator.catalog()
        except ReleaseOperatorError as exc:
            raise HTTPException(502, detail="release_catalog_unavailable") from exc

    async def integration_status(self):
        try:
            return await self.operator.integration_status()
        except ReleaseOperatorError as exc:
            raise HTTPException(502, detail="workspace_scan_unavailable") from exc

    async def module_status(self, environment: str, module: str):
        if environment not in {"test", "prod"} or not MODULE_RE.fullmatch(module):
            raise HTTPException(404, detail="module_status_target_not_found")
        try:
            return await self.operator.module_status(
                environment=environment, module=module
            )
        except ReleaseOperatorError as exc:
            raise HTTPException(502, detail="module_status_unavailable") from exc

    @staticmethod
    def _slots(request: WorkspaceSelectionRequest) -> list[str]:
        slots = sorted(request.slots)
        if len(slots) != len(set(slots)):
            raise HTTPException(422, detail="duplicate_slots")
        return slots

    async def start_integration(
        self,
        request: WorkspaceSelectionRequest,
        source_ip: str,
        request_id: str,
    ):
        slots = self._slots(request)
        phrase = f"INTEGRATE {','.join(slots)} {request.expected_main_sha}"
        if request.confirmation != phrase:
            raise HTTPException(422, detail="confirmation_mismatch")
        status = await self.integration_status()
        if status.get("main_sha") != request.expected_main_sha:
            raise HTTPException(409, detail="main_changed")
        pending: dict[str, list[str]] = {slot: [] for slot in slots}
        for row in (status.get("queue") or {}).get("pending", []):
            slot = str(row.get("slot"))
            head = str(row.get("head"))
            if slot in pending:
                pending[slot].append(head)
        pending = {slot: heads for slot, heads in pending.items() if heads}
        if set(pending) != set(slots):
            raise HTTPException(409, detail="selected_handoff_unavailable")
        if not self._available():
            raise HTTPException(409, detail="runtime_operation_in_progress")
        return self._start(
            "workspace-integrate",
            {"sha": request.expected_main_sha, "slots": ",".join(slots)},
            source_ip,
            request_id,
            self._integrate(request.expected_main_sha, slots, pending),
        )

    async def _integrate(
        self, sha: str, slots: list[str], heads: dict[str, list[str]]
    ):
        return await self.operator.integrate_slots(
            expected_main_sha=sha,
            slots=slots,
            heads=heads,
            confirmation=f"INTEGRATE {','.join(slots)} {sha}",
        )

    async def start_alignment(
        self,
        request: WorkspaceSelectionRequest,
        source_ip: str,
        request_id: str,
    ):
        slots = self._slots(request)
        phrase = f"ALIGN {','.join(slots)} {request.expected_main_sha}"
        if request.confirmation != phrase:
            raise HTTPException(422, detail="confirmation_mismatch")
        status = await self.integration_status()
        if status.get("main_sha") != request.expected_main_sha:
            raise HTTPException(409, detail="main_changed")
        if not self._available():
            raise HTTPException(409, detail="runtime_operation_in_progress")
        return self._start(
            "workspace-align",
            {"sha": request.expected_main_sha, "slots": ",".join(slots)},
            source_ip,
            request_id,
            self.operator.align_slots(
                expected_main_sha=request.expected_main_sha,
                slots=slots,
                confirmation=phrase,
            ),
        )

    @staticmethod
    def _modules(modules: list[str]) -> list[str]:
        result = sorted(modules)
        if (
            len(result) != len(set(result))
            or not all(MODULE_RE.fullmatch(module) for module in result)
        ):
            raise HTTPException(422, detail="invalid_modules")
        return result

    async def start_build(
        self, request: ModuleBuildRequest, source_ip: str, request_id: str
    ):
        modules = self._modules(request.modules)
        phrase = f"BUILD {','.join(modules)} {request.sha}"
        if request.confirmation != phrase:
            raise HTTPException(422, detail="confirmation_mismatch")
        scan = await self.integration_status()
        if scan.get("main_sha") != request.sha:
            raise HTTPException(409, detail="main_changed")
        catalog = (await self.catalog()).get("modules") or {}
        if any(module not in catalog for module in modules):
            raise HTTPException(422, detail="module_not_available")
        if not self._available():
            raise HTTPException(409, detail="runtime_operation_in_progress")
        return self._start(
            "module-build",
            {"sha": request.sha, "modules": ",".join(modules)},
            source_ip,
            request_id,
            self.operator.build_modules(
                sha=request.sha,
                modules=modules,
                confirmation=phrase,
            ),
        )

    async def start_deploy(
        self, request: ModuleDeployRequest, source_ip: str, request_id: str
    ):
        modules = self._modules(list(request.artifacts))
        if request.environment == "test" and len(modules) > 2:
            raise HTTPException(422, detail="test_module_limit")
        phrase = f"DEPLOY {request.environment.upper()} {','.join(modules)}"
        if request.confirmation != phrase:
            raise HTTPException(422, detail="confirmation_mismatch")
        catalog = (await self.catalog()).get("modules") or {}
        if any(
            module not in catalog
            or catalog[module].get("build_only")
            or request.environment not in catalog[module].get("environments", [])
            for module in modules
        ):
            raise HTTPException(422, detail="module_not_available")
        if not self._available():
            raise HTTPException(409, detail="runtime_operation_in_progress")
        return self._start(
            "module-deploy",
            {
                "environment": request.environment,
                "modules": ",".join(modules),
            },
            source_ip,
            request_id,
            self.operator.deploy_modules(
                environment=request.environment,
                artifacts=request.artifacts,
                targets={
                    name: target.model_dump()
                    for name, target in request.targets.items()
                },
                confirmation=phrase,
            ),
        )

    def _start(
        self,
        kind: str,
        request: dict[str, str],
        source_ip: str,
        request_id: str,
        coroutine,
    ):
        operation_id = f"{kind}-{uuid.uuid4().hex[:12]}"
        operation = self.store.create(
            operation_id,
            kind=kind,
            request={
                **request,
                "source_ip": source_ip,
                "request_id": request_id,
            },
        )
        self._spawn(self._execute(operation_id, coroutine))
        return operation

    async def _execute(self, operation_id: str, coroutine):
        async with self.runtime_lock:
            try:
                self.store.update(
                    operation_id,
                    status=OperationStatus.RUNNING,
                    stage="executing",
                )
                result = await coroutine
                self.store.update(
                    operation_id,
                    status=OperationStatus.SUCCEEDED,
                    stage="completed",
                    result=result,
                )
            except Exception as exc:
                self.store.update(
                    operation_id,
                    status=OperationStatus.FAILED,
                    stage="failed",
                    error_code=str(exc)[:120] or "operation_failed",
                )
