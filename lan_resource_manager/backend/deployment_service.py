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
    BulkTestDeployRequest,
    BuildRequest,
    DeploymentExecuteRequest,
    DeploymentPlanRequest,
    GPUReleaseBuildRequest,
    IntegrationRequest,
    MaintenanceRequest,
    OperationStatus,
    RetryIntegrationRequest,
    TestConfigSyncRequest,
    TestRollbackRepairRequest,
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
        try:
            return await self.operator.catalog()
        except ReleaseOperatorError as exc:
            raise HTTPException(
                502, detail="release_catalog_unavailable"
            ) from exc

    async def candidate(self):
        try:
            return await self.operator.candidate()
        except ReleaseOperatorError as exc:
            raise HTTPException(
                502, detail="release_candidate_unavailable"
            ) from exc

    async def environment_status(self, environment: str):
        if environment not in {"test", "prod"}:
            raise HTTPException(404, detail="environment_not_found")
        try:
            return await self.operator.environment_status(environment)
        except ReleaseOperatorError as exc:
            raise HTTPException(
                502, detail="environment_status_unavailable"
            ) from exc

    async def integration_status(self):
        try:
            return await self.operator.integration_status()
        except ReleaseOperatorError as exc:
            raise HTTPException(
                502, detail="integration_status_unavailable"
            ) from exc

    def _runtime_available(self) -> bool:
        return not self.runtime_lock.locked() and not self.store.active(
            kinds={
                "switch",
                "deploy",
                "deploy-all-test",
                "maintenance",
                "integration",
                "integration-retry",
                "gpu-release-build",
                "test-config-sync",
                "test-rollback-repair",
                "workspace-align",
            }
        )

    async def start_integration(
        self,
        request: IntegrationRequest,
        source_ip: str,
        request_id: str,
    ):
        if request.confirmation != f"INTEGRATE {request.expected_main_sha}":
            raise HTTPException(422, detail="confirmation_mismatch")
        candidate = await self.operator.candidate()
        if candidate.get("main_sha") != request.expected_main_sha:
            raise HTTPException(409, detail="main_changed")
        if not self._runtime_available() or self.store.active(kind="build"):
            raise HTTPException(409, detail="runtime_operation_in_progress")
        operation_id = f"integration-{uuid.uuid4().hex[:12]}"
        operation = self.store.create(
            operation_id,
            kind="integration",
            request={
                "sha": request.expected_main_sha,
                "source_ip": source_ip,
                "request_id": request_id,
            },
        )
        self._spawn(
            self._integration(operation_id, request.expected_main_sha)
        )
        return operation

    async def start_gpu_release_build(
        self,
        request: GPUReleaseBuildRequest,
        source_ip: str,
        request_id: str,
    ):
        if request.confirmation != f"GPU BUILD {request.expected_main_sha}":
            raise HTTPException(422, detail="confirmation_mismatch")
        candidate = await self.operator.candidate()
        if candidate.get("main_sha") != request.expected_main_sha:
            raise HTTPException(409, detail="main_changed")
        if not self._runtime_available() or self.store.active(kind="build"):
            raise HTTPException(409, detail="runtime_operation_in_progress")
        operation_id = f"gpu-release-build-{uuid.uuid4().hex[:12]}"
        operation = self.store.create(
            operation_id,
            kind="gpu-release-build",
            request={
                "sha": request.expected_main_sha,
                "source_ip": source_ip,
                "request_id": request_id,
            },
        )
        self._spawn(
            self._gpu_release_build(
                operation_id, request.expected_main_sha
            )
        )
        return operation

    async def _gpu_release_build(self, operation_id: str, sha: str):
        async with self.runtime_lock:
            try:
                self.store.update(
                    operation_id,
                    status=OperationStatus.RUNNING,
                    stage="preparing-gpu-release",
                )
                result = await self.operator.prepare_gpu_release(
                    expected_main_sha=sha,
                    confirmation=f"GPU BUILD {sha}",
                )
                self.store.update(
                    operation_id,
                    status=OperationStatus.SUCCEEDED,
                    stage="gpu-release-ready",
                    result=result,
                )
            except Exception as exc:
                self.store.update(
                    operation_id,
                    status=OperationStatus.FAILED,
                    stage="failed",
                    error_code=str(exc)[:120]
                    or "gpu_release_preparation_failed",
                )

    async def start_test_config_sync(
        self,
        request: TestConfigSyncRequest,
        source_ip: str,
        request_id: str,
    ):
        if request.confirmation != f"TEST CONFIG {request.expected_main_sha}":
            raise HTTPException(422, detail="confirmation_mismatch")
        candidate = await self.operator.candidate()
        if candidate.get("main_sha") != request.expected_main_sha:
            raise HTTPException(409, detail="main_changed")
        if not self._runtime_available() or self.store.active(kind="build"):
            raise HTTPException(409, detail="runtime_operation_in_progress")
        operation_id = f"test-config-sync-{uuid.uuid4().hex[:12]}"
        operation = self.store.create(
            operation_id,
            kind="test-config-sync",
            request={
                "sha": request.expected_main_sha,
                "source_ip": source_ip,
                "request_id": request_id,
            },
        )
        self._spawn(
            self._sync_test_config(
                operation_id, request.expected_main_sha
            )
        )
        return operation

    async def _sync_test_config(self, operation_id: str, sha: str):
        async with self.runtime_lock:
            try:
                self.store.update(
                    operation_id,
                    status=OperationStatus.RUNNING,
                    stage="syncing-test-config",
                )
                result = await self.operator.sync_test_config(
                    expected_main_sha=sha,
                    confirmation=f"TEST CONFIG {sha}",
                )
                self.store.update(
                    operation_id,
                    status=OperationStatus.SUCCEEDED,
                    stage="test-config-synced",
                    result=result,
                )
            except Exception as exc:
                self.store.update(
                    operation_id,
                    status=OperationStatus.FAILED,
                    stage="failed",
                    error_code=str(exc)[:120]
                    or "test_config_sync_failed",
                )

    async def start_test_rollback_repair(
        self,
        request: TestRollbackRepairRequest,
        source_ip: str,
        request_id: str,
    ):
        phrase = f"REPAIR TEST ROLLBACK {request.expected_current_sha}"
        if request.confirmation != phrase:
            raise HTTPException(422, detail="confirmation_mismatch")
        status = await self.operator.environment_status("test")
        if status.get("current_sha") != request.expected_current_sha:
            raise HTTPException(409, detail="test_environment_changed")
        if not self._runtime_available() or self.store.active(kind="build"):
            raise HTTPException(409, detail="runtime_operation_in_progress")
        operation_id = f"test-rollback-repair-{uuid.uuid4().hex[:12]}"
        operation = self.store.create(
            operation_id,
            kind="test-rollback-repair",
            request={
                "sha": request.expected_current_sha,
                "source_ip": source_ip,
                "request_id": request_id,
            },
        )
        self._spawn(
            self._repair_test_rollback(
                operation_id, request.expected_current_sha
            )
        )
        return operation

    async def _repair_test_rollback(self, operation_id: str, sha: str):
        async with self.runtime_lock:
            try:
                self.store.update(
                    operation_id,
                    status=OperationStatus.RUNNING,
                    stage="repairing-test-rollback-materials",
                )
                result = await self.operator.repair_test_rollback(
                    expected_current_sha=sha,
                    confirmation=f"REPAIR TEST ROLLBACK {sha}",
                )
                self.store.update(
                    operation_id,
                    status=OperationStatus.SUCCEEDED,
                    stage="test-rollback-materials-ready",
                    result=result,
                )
            except Exception as exc:
                self.store.update(
                    operation_id,
                    status=OperationStatus.FAILED,
                    stage="failed",
                    error_code=str(exc)[:120]
                    or "test_rollback_repair_failed",
                )

    async def _integration(self, operation_id: str, sha: str):
        async with self.runtime_lock:
            try:
                self.store.update(
                    operation_id,
                    status=OperationStatus.RUNNING,
                    stage="integrating-handoffs",
                )
                await self.operator.integrate_all(
                    expected_main_sha=sha,
                    confirmation=f"INTEGRATE {sha}",
                )
                self.store.update(
                    operation_id,
                    status=OperationStatus.SUCCEEDED,
                    stage="integration-completed",
                )
            except Exception as exc:
                self.store.update(
                    operation_id,
                    status=OperationStatus.FAILED,
                    stage="failed",
                    error_code=str(exc)[:120] or "integration_failed",
                )

    async def start_integration_retry(
        self,
        request: RetryIntegrationRequest,
        source_ip: str,
        request_id: str,
    ):
        if request.confirmation != f"RETRY {request.batch}":
            raise HTTPException(422, detail="confirmation_mismatch")
        status = await self.integration_status()
        failed_ids = {
            str(row.get("id"))
            for row in status.get("queue", {}).get("failed", [])
        }
        if request.batch not in failed_ids:
            raise HTTPException(409, detail="failed_batch_not_found")
        if not self._runtime_available() or self.store.active(kind="build"):
            raise HTTPException(409, detail="runtime_operation_in_progress")
        operation_id = f"integration-retry-{uuid.uuid4().hex[:12]}"
        operation = self.store.create(
            operation_id,
            kind="integration-retry",
            request={
                "batch": request.batch,
                "source_ip": source_ip,
                "request_id": request_id,
            },
        )
        self._spawn(self._retry_integration(operation_id, request.batch))
        return operation

    async def _retry_integration(self, operation_id: str, batch: str):
        async with self.runtime_lock:
            try:
                self.store.update(
                    operation_id,
                    status=OperationStatus.RUNNING,
                    stage="retrying-integration",
                )
                result = await self.operator.retry_integration(
                    batch=batch,
                    confirmation=f"RETRY {batch}",
                )
                self.store.update(
                    operation_id,
                    status=OperationStatus.SUCCEEDED,
                    stage="integration-retry-completed",
                    result=result,
                )
            except Exception as exc:
                self.store.update(
                    operation_id,
                    status=OperationStatus.FAILED,
                    stage="failed",
                    error_code=str(exc)[:120] or "integration_retry_failed",
                )

    async def start_workspace_alignment(
        self,
        request: IntegrationRequest,
        source_ip: str,
        request_id: str,
    ):
        if request.confirmation != f"ALIGN {request.expected_main_sha}":
            raise HTTPException(422, detail="confirmation_mismatch")
        if not self._runtime_available():
            raise HTTPException(409, detail="runtime_operation_in_progress")
        operation_id = f"workspace-align-{uuid.uuid4().hex[:12]}"
        operation = self.store.create(
            operation_id,
            kind="workspace-align",
            request={
                "sha": request.expected_main_sha,
                "source_ip": source_ip,
                "request_id": request_id,
            },
        )
        self._spawn(
            self._align_workspaces(operation_id, request.expected_main_sha)
        )
        return operation

    async def _align_workspaces(self, operation_id: str, sha: str):
        async with self.runtime_lock:
            try:
                self.store.update(
                    operation_id,
                    status=OperationStatus.RUNNING,
                    stage="aligning-workspaces",
                )
                result = await self.operator.align_workspaces(
                    expected_main_sha=sha,
                    confirmation=f"ALIGN {sha}",
                )
                blocked = [
                    row
                    for row in result.get("slots", [])
                    if not str(row.get("status", "")).startswith("aligned")
                ]
                self.store.update(
                    operation_id,
                    status=OperationStatus.SUCCEEDED,
                    stage=(
                        "aligned-with-blockers"
                        if blocked
                        else "alignment-completed"
                    ),
                    result={"slots": result.get("slots", [])},
                )
            except Exception as exc:
                self.store.update(
                    operation_id,
                    status=OperationStatus.FAILED,
                    stage="failed",
                    error_code=str(exc)[:120] or "workspace_alignment_failed",
                )

    async def start_bulk_test_deploy(
        self,
        request: BulkTestDeployRequest,
        source_ip: str,
        request_id: str,
    ):
        if request.confirmation != f"TEST ALL {request.candidate_sha}":
            raise HTTPException(422, detail="confirmation_mismatch")
        catalog, candidate = await asyncio.gather(
            self.operator.catalog(), self.operator.candidate()
        )
        if candidate.get("deployable_sha") != request.candidate_sha:
            raise HTTPException(409, detail="candidate_changed")
        modules = list(
            ((catalog.get("environments") or {}).get("test") or {}).get(
                "modules", []
            )
        )
        if not modules:
            raise HTTPException(409, detail="test_modules_unavailable")
        if not self._runtime_available():
            raise HTTPException(409, detail="runtime_operation_in_progress")
        operation_id = f"deploy-all-test-{uuid.uuid4().hex[:12]}"
        operation = self.store.create(
            operation_id,
            kind="deploy-all-test",
            request={
                "sha": request.candidate_sha,
                "modules": ",".join(modules),
                "source_ip": source_ip,
                "request_id": request_id,
            },
        )
        self._spawn(
            self._bulk_test_deploy(
                operation_id, request.candidate_sha, modules
            )
        )
        return operation

    async def _bulk_test_deploy(
        self, operation_id: str, sha: str, modules: list[str]
    ):
        async with self.runtime_lock:
            completed: list[str] = []
            try:
                for module in modules:
                    self.store.update(
                        operation_id,
                        status=OperationStatus.RUNNING,
                        stage=f"planning-{module}",
                    )
                    plan = await self.operator.plan(
                        "test", module, sha, "planner"
                    )
                    token = plan.get("plan_token")
                    if not token:
                        raise ReleaseOperatorError(
                            f"release_plan_missing_token:{module}"
                        )
                    self.store.update(
                        operation_id,
                        status=OperationStatus.RUNNING,
                        stage=f"deploying-{module}",
                    )
                    await self.operator.deploy(
                        environment="test",
                        module=module,
                        sha=sha,
                        maintenance="planner",
                        plan_token=token,
                        confirm_prod=False,
                    )
                    completed.append(module)
                self.store.update(
                    operation_id,
                    status=OperationStatus.SUCCEEDED,
                    stage="all-test-modules-deployed",
                    result={"completed_modules": completed},
                )
            except Exception as exc:
                self.store.update(
                    operation_id,
                    status=OperationStatus.FAILED,
                    stage="failed",
                    error_code=str(exc)[:120] or "bulk_test_deploy_failed",
                    result={"completed_modules": completed},
                )

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
