from __future__ import annotations

import asyncio
import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from .models import (
    BuildRequest,
    DeploymentExecuteRequest,
    DeploymentPlanRequest,
    MaintenanceRequest,
    OperationStatus,
)
from .release_operator import ReleaseOperatorError, ReleaseOperatorPort
from .store import OperationStore, utc_now


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temp = Path(handle.name)
    os.chmod(temp, 0o600)
    os.replace(temp, path)


class DeploymentService:
    def __init__(
        self,
        operator: ReleaseOperatorPort,
        store: OperationStore,
        data_dir: Path,
        runtime_lock: asyncio.Lock,
    ):
        self.operator = operator
        self.store = store
        self.plan_dir = data_dir / "deployment-plans"
        self.runtime_lock = runtime_lock
        self.build_lock = asyncio.Lock()
        self.tasks: set[asyncio.Task] = set()

    def _spawn(self, coroutine) -> None:
        task = asyncio.create_task(coroutine)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    def resume_build_observation(self) -> None:
        for operation in self.store.active_all(kind="build"):
            sha = (operation.get("request") or {}).get("sha")
            if isinstance(sha, str):
                self._spawn(
                    self._build(operation["operation_id"], sha, dispatch=False)
                )

    async def catalog(self):
        return await self.operator.catalog()

    async def candidate(self):
        return await self.operator.candidate()

    async def environment_status(self, environment: str):
        if environment not in {"test", "prod"}:
            raise HTTPException(404, detail="environment_not_found")
        return await self.operator.environment_status(environment)

    async def create_plan(
        self, request: DeploymentPlanRequest, source_ip: str, request_id: str
    ):
        catalog, candidate, environment_status = await asyncio.gather(
            self.operator.catalog(),
            self.operator.candidate(),
            self.operator.environment_status(request.environment),
        )
        allowed = (
            (catalog.get("environments") or {})
            .get(request.environment, {})
            .get("modules", [])
        )
        if request.module not in allowed:
            raise HTTPException(422, detail="module_not_available")
        if request.candidate_sha != candidate.get("deployable_sha"):
            raise HTTPException(409, detail="candidate_changed")
        if request.maintenance == "rolling" and request.environment != "prod":
            raise HTTPException(422, detail="rolling_only_for_prod")
        if environment_status.get("config_drift"):
            raise HTTPException(409, detail="environment_config_drift")
        if environment_status.get("active_transaction"):
            raise HTTPException(409, detail="environment_transaction_active")
        raw = await self.operator.plan(
            request.environment,
            request.module,
            request.candidate_sha,
            request.maintenance,
        )
        plan_id = f"plan-{uuid.uuid4().hex[:16]}"
        record = {
            "plan_id": plan_id,
            "created_at": utc_now(),
            "environment": request.environment,
            "module": request.module,
            "candidate_sha": request.candidate_sha,
            "maintenance": request.maintenance,
            "expected_config_revision": environment_status.get("config_revision"),
            "audit": {"source_ip": source_ip, "request_id": request_id},
            "plan_token": raw.get("plan_token"),
            "expires_at": raw.get("plan_token_expires_at"),
            "preview": {
                key: value
                for key, value in raw.items()
                if key not in {"plan_token", "plan_token_expires_at"}
            },
        }
        if not record["plan_token"]:
            raise HTTPException(502, detail="release_plan_missing_token")
        _atomic_json(self.plan_dir / f"{plan_id}.json", record)
        return self._public_plan(record)

    def _public_plan(self, record):
        return {
            "plan_id": record["plan_id"],
            "environment": record["environment"],
            "module": record["module"],
            "candidate_sha": record["candidate_sha"],
            "maintenance": record["maintenance"],
            "expires_at": record["expires_at"],
            "preview": record["preview"],
        }

    def _load_plan(self, plan_id: str):
        if not plan_id.startswith("plan-"):
            raise HTTPException(404, detail="deployment_plan_not_found")
        path = self.plan_dir / f"{plan_id}.json"
        if not path.is_file():
            raise HTTPException(404, detail="deployment_plan_not_found")
        return json.loads(path.read_text(encoding="utf-8"))

    async def execute_plan(
        self,
        plan_id: str,
        request: DeploymentExecuteRequest,
        source_ip: str,
        request_id: str,
    ):
        record = self._load_plan(plan_id)
        try:
            expires_at = datetime.fromisoformat(record["expires_at"])
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(409, detail="deployment_plan_invalid") from exc
        if expires_at <= datetime.now(timezone.utc):
            raise HTTPException(409, detail="deployment_plan_expired")
        prefix = "PROD" if record["environment"] == "prod" else "TEST"
        expected = f"{prefix} {record['module']} {record['candidate_sha']}"
        if request.confirmation != expected:
            raise HTTPException(422, detail="confirmation_mismatch")
        if self.runtime_lock.locked() or self.store.active(
            kinds={"switch", "deploy", "maintenance"}
        ):
            raise HTTPException(409, detail="runtime_operation_in_progress")
        operation_id = f"deploy-{uuid.uuid4().hex[:12]}"
        operation = self.store.create(
            operation_id,
            kind="deploy",
            request={
                "environment": record["environment"],
                "module": record["module"],
                "sha": record["candidate_sha"],
                "source_ip": source_ip,
                "request_id": request_id,
            },
        )
        self._spawn(self._execute(operation_id, record))
        return operation

    async def _execute(self, operation_id: str, record: dict):
        async with self.runtime_lock:
            self.store.update(
                operation_id, status=OperationStatus.VALIDATING, stage="preflight"
            )
            try:
                candidate, environment_status = await asyncio.gather(
                    self.operator.candidate(),
                    self.operator.environment_status(record["environment"]),
                )
                if candidate.get("deployable_sha") != record["candidate_sha"]:
                    raise ReleaseOperatorError("candidate_changed")
                if environment_status.get("config_drift"):
                    raise ReleaseOperatorError("environment_config_drift")
                if environment_status.get("active_transaction"):
                    raise ReleaseOperatorError("environment_transaction_active")
                if environment_status.get("config_revision") != record.get(
                    "expected_config_revision"
                ):
                    raise ReleaseOperatorError("environment_config_changed")
                self.store.update(
                    operation_id, status=OperationStatus.RUNNING, stage="deploying"
                )
                await self.operator.deploy(
                    environment=record["environment"],
                    module=record["module"],
                    sha=record["candidate_sha"],
                    maintenance=record["maintenance"],
                    plan_token=record["plan_token"],
                    confirm_prod=record["environment"] == "prod",
                )
                self.store.update(
                    operation_id,
                    status=OperationStatus.SUCCEEDED,
                    stage="completed",
                )
            except ReleaseOperatorError as exc:
                code = str(exc)
                recovery = "recovery" in code or "rollback_failed" in code
                self.store.update(
                    operation_id,
                    status=(
                        OperationStatus.RECOVERY_REQUIRED
                        if recovery
                        else OperationStatus.FAILED
                    ),
                    stage="failed",
                    error_code=code[:120],
                )
            except Exception:
                self.store.update(
                    operation_id,
                    status=OperationStatus.FAILED,
                    stage="failed",
                    error_code="deployment_failed",
                )

    async def start_build(
        self, request: BuildRequest, source_ip: str, request_id: str
    ):
        candidate = await self.operator.candidate()
        if request.expected_main_sha != candidate.get("main_sha"):
            raise HTTPException(409, detail="main_changed")
        if request.confirmation != f"BUILD {request.expected_main_sha}":
            raise HTTPException(422, detail="confirmation_mismatch")
        active = self.store.active(kind="build", request_value=request.expected_main_sha)
        if active:
            return active
        operation_id = f"build-{uuid.uuid4().hex[:12]}"
        operation = self.store.create(
            operation_id,
            kind="build",
            request={
                "sha": request.expected_main_sha,
                "source_ip": source_ip,
                "request_id": request_id,
            },
        )
        self._spawn(self._build(operation_id, request.expected_main_sha))
        return operation

    async def _build(self, operation_id: str, sha: str, *, dispatch: bool = True):
        async with self.build_lock:
            try:
                external_run_id = None
                if dispatch:
                    self.store.update(
                        operation_id,
                        status=OperationStatus.RUNNING,
                        stage="dispatching-ci",
                    )
                    dispatch_result = await self.operator.start_build(sha)
                    external_run_id = dispatch_result.get("run_id")
                self.store.update(
                    operation_id,
                    status=OperationStatus.RUNNING,
                    stage=(
                        "waiting-trusted-ci"
                        if dispatch
                        else "resuming-build-observation"
                    ),
                    external_run_id=external_run_id
                    or self.store.get(operation_id).get("external_run_id"),
                )
                for _ in range(720):
                    status = await self.operator.build_status(sha)
                    bundle = status.get("bundle") or {}
                    if bundle.get("status") == "ready":
                        self.store.update(
                            operation_id,
                            status=OperationStatus.SUCCEEDED,
                            stage="bundle-ready",
                        )
                        return
                    build = status.get("build") or {}
                    ci = status.get("ci") or {}
                    if (
                        build.get("status") == "completed"
                        and build.get("conclusion") not in {None, "success"}
                    ):
                        raise ReleaseOperatorError("trusted_build_failed")
                    if (
                        ci.get("status") == "completed"
                        and ci.get("conclusion") not in {None, "success"}
                    ):
                        raise ReleaseOperatorError("trusted_ci_failed")
                    await asyncio.sleep(20)
                raise ReleaseOperatorError("trusted_build_timed_out")
            except Exception:
                self.store.update(
                    operation_id,
                    status=OperationStatus.FAILED,
                    stage="failed",
                    error_code="trusted_build_dispatch_failed",
                )

    async def set_maintenance(
        self,
        environment: str,
        request: MaintenanceRequest,
        source_ip: str,
        request_id: str,
    ):
        if environment not in {"test", "prod"}:
            raise HTTPException(404, detail="environment_not_found")
        action = "ON" if request.enabled else "OFF"
        prefix = environment.upper()
        if request.confirmation != f"{prefix} MAINTENANCE {action}":
            raise HTTPException(422, detail="confirmation_mismatch")
        current = await self.operator.environment_status(environment)
        enabled = bool((current.get("maintenance") or {}).get("enabled"))
        if enabled != request.expected_enabled:
            raise HTTPException(409, detail="maintenance_state_changed")
        if self.runtime_lock.locked() or self.store.active(
            kinds={"switch", "deploy", "maintenance"}
        ):
            raise HTTPException(409, detail="runtime_operation_in_progress")
        operation_id = f"maintenance-{uuid.uuid4().hex[:12]}"
        operation = self.store.create(
            operation_id,
            kind="maintenance",
            request={
                "environment": environment,
                "enabled": request.enabled,
                "reason": request.reason,
                "source_ip": source_ip,
                "request_id": request_id,
            },
        )
        self._spawn(
            self._maintenance(operation_id, environment, request, source_ip)
        )
        return operation

    async def _maintenance(self, operation_id, environment, request, source_ip):
        async with self.runtime_lock:
            self.store.update(
                operation_id, status=OperationStatus.RUNNING, stage="maintenance"
            )
            try:
                await self.operator.set_maintenance(
                    environment=environment,
                    enabled=request.enabled,
                    expected_enabled=request.expected_enabled,
                    reason=request.reason,
                    operation_id=operation_id,
                    source_ip=source_ip,
                )
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
                    error_code="maintenance_update_failed",
                )
