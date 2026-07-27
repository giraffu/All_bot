from __future__ import annotations

import asyncio
import json
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .config import Settings
from .deployment_service import DeploymentService
from .models import (
    BulkTestDeployRequest,
    BuildRequest,
    DeploymentExecuteRequest,
    DeploymentPlanRequest,
    GPUReleaseBuildRequest,
    IntegrationRequest,
    MaintenanceRequest,
    RetryIntegrationRequest,
    TestConfigSyncRequest,
    TestRollbackRepairRequest,
    SwitchRequest,
    TERMINAL_OPERATION_STATUSES,
)
from .operator import CliLanAioOperator, OperatorPort
from .release_operator import ReleaseOperatorPort, UnixReleaseOperator
from .security import LocalSecurityMiddleware
from .service import FleetService
from .store import OperationStore


def create_app(
    settings: Settings | None = None,
    operator: OperatorPort | None = None,
    release_operator: ReleaseOperatorPort | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    csrf_token = secrets.token_urlsafe(32)
    store = OperationStore(settings.data_dir)
    runtime_lock = asyncio.Lock()
    service = FleetService(
        settings,
        operator or CliLanAioOperator(settings),
        store,
        runtime_lock=runtime_lock,
    )
    deployment = DeploymentService(
        release_operator or UnixReleaseOperator(settings),
        store,
        settings.data_dir,
        runtime_lock,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        deployment.resume_build_observation()
        yield

    app = FastAPI(
        title="LAN AIO Resource Manager",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.service = service
    app.state.csrf_token = csrf_token
    app.state.deployment_service = deployment
    app.add_middleware(
        LocalSecurityMiddleware, settings=settings, csrf_token=csrf_token
    )
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=list(settings.allowed_hosts)
    )

    @app.get("/api/health")
    async def health():
        return {"ok": True}

    @app.get("/api/v1/security/csrf")
    async def csrf():
        return {"csrf_token": csrf_token}

    @app.get("/api/v1/fleet")
    async def fleet():
        return await service.fleet()

    @app.post("/api/v1/fleet/refresh", status_code=202)
    async def refresh():
        return await service.start_refresh()

    @app.post(
        "/api/v1/physical-slots/{node_id}/{gpu_index}/switches",
        status_code=202,
    )
    async def switch(node_id: str, gpu_index: int, payload: SwitchRequest):
        return await service.start_switch(node_id, gpu_index, payload)

    @app.get("/api/v1/deployments/catalog")
    async def deployment_catalog():
        return await deployment.catalog()

    @app.get("/api/v1/integration/status")
    async def integration_status():
        return await deployment.integration_status()

    @app.post("/api/v1/integration/run", status_code=202)
    async def integration_run(payload: IntegrationRequest, request: Request):
        source_ip = request.client.host if request.client else "unknown"
        return await deployment.start_integration(
            payload, source_ip, request.state.request_id
        )

    @app.post("/api/v1/integration/retry", status_code=202)
    async def integration_retry(
        payload: RetryIntegrationRequest, request: Request
    ):
        source_ip = request.client.host if request.client else "unknown"
        return await deployment.start_integration_retry(
            payload, source_ip, request.state.request_id
        )

    @app.post("/api/v1/workspaces/align", status_code=202)
    async def align_workspaces(payload: IntegrationRequest, request: Request):
        source_ip = request.client.host if request.client else "unknown"
        return await deployment.start_workspace_alignment(
            payload, source_ip, request.state.request_id
        )

    @app.get("/api/v1/releases/candidate")
    async def release_candidate():
        return await deployment.candidate()

    @app.post("/api/v1/releases/builds", status_code=202)
    async def release_build(payload: BuildRequest, request: Request):
        source_ip = request.client.host if request.client else "unknown"
        return await deployment.start_build(
            payload, source_ip, request.state.request_id
        )

    @app.post("/api/v1/releases/gpu-builds", status_code=202)
    async def gpu_release_build(
        payload: GPUReleaseBuildRequest, request: Request
    ):
        source_ip = request.client.host if request.client else "unknown"
        return await deployment.start_gpu_release_build(
            payload, source_ip, request.state.request_id
        )

    @app.get("/api/v1/environments/{environment}/status")
    async def environment_status(environment: str):
        return await deployment.environment_status(environment)

    @app.post("/api/v1/environments/test/config-sync", status_code=202)
    async def test_config_sync(
        payload: TestConfigSyncRequest, request: Request
    ):
        source_ip = request.client.host if request.client else "unknown"
        return await deployment.start_test_config_sync(
            payload, source_ip, request.state.request_id
        )

    @app.post("/api/v1/environments/test/rollback-repair", status_code=202)
    async def test_rollback_repair(
        payload: TestRollbackRepairRequest, request: Request
    ):
        source_ip = request.client.host if request.client else "unknown"
        return await deployment.start_test_rollback_repair(
            payload, source_ip, request.state.request_id
        )

    @app.post("/api/v1/deployment-plans", status_code=201)
    async def deployment_plan(payload: DeploymentPlanRequest, request: Request):
        source_ip = request.client.host if request.client else "unknown"
        return await deployment.create_plan(
            payload, source_ip, request.state.request_id
        )

    @app.post("/api/v1/deployment-plans/{plan_id}/execute", status_code=202)
    async def execute_deployment_plan(
        plan_id: str, payload: DeploymentExecuteRequest, request: Request
    ):
        source_ip = request.client.host if request.client else "unknown"
        return await deployment.execute_plan(
            plan_id, payload, source_ip, request.state.request_id
        )

    @app.post(
        "/api/v1/environments/{environment}/maintenance", status_code=202
    )
    async def update_maintenance(
        environment: str, payload: MaintenanceRequest, request: Request
    ):
        source_ip = request.client.host if request.client else "unknown"
        return await deployment.set_maintenance(
            environment, payload, source_ip, request.state.request_id
        )

    @app.post("/api/v1/environments/test/deploy-all", status_code=202)
    async def deploy_all_test(payload: BulkTestDeployRequest, request: Request):
        source_ip = request.client.host if request.client else "unknown"
        return await deployment.start_bulk_test_deploy(
            payload, source_ip, request.state.request_id
        )

    @app.get("/api/v1/operations/{operation_id}")
    async def operation(operation_id: str):
        return service.operation(operation_id)

    @app.get("/api/v1/operations/{operation_id}/events")
    async def operation_events(operation_id: str, request: Request):
        async def events():
            last_updated = None
            while not await request.is_disconnected():
                item = service.operation(operation_id)
                if item["updated_at"] != last_updated:
                    last_updated = item["updated_at"]
                    yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
                if item["status"] in {
                    str(status) for status in TERMINAL_OPERATION_STATUSES
                }:
                    break
                await asyncio.sleep(0.5)

        return StreamingResponse(events(), media_type="text/event-stream")

    static_dir = Path(__file__).resolve().parents[1] / "frontend/dist"
    if static_dir.exists():
        app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        async def spa(path: str):
            candidate = static_dir / path
            if path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(static_dir / "index.html")

    return app


app = create_app()
