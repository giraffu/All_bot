from __future__ import annotations

import asyncio
import json
import secrets
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .config import Settings
from .deployment_service import DeploymentService
from .models import (
    ModuleBuildRequest,
    ModuleDeployRequest,
    SwitchRequest,
    TERMINAL_OPERATION_STATUSES,
    WorkspaceSelectionRequest,
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

    app = FastAPI(
        title="LAN AIO Resource Manager",
        docs_url=None,
        redoc_url=None,
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

    @app.get("/api/v1/workspaces/scan")
    async def workspace_scan():
        return await deployment.integration_status()

    @app.post("/api/v1/workspaces/integrate", status_code=202)
    async def integrate_workspaces(
        payload: WorkspaceSelectionRequest, request: Request
    ):
        source_ip = request.client.host if request.client else "unknown"
        return await deployment.start_integration(
            payload, source_ip, request.state.request_id
        )

    @app.post("/api/v1/workspaces/align", status_code=202)
    async def align_workspaces(
        payload: WorkspaceSelectionRequest, request: Request
    ):
        source_ip = request.client.host if request.client else "unknown"
        return await deployment.start_alignment(
            payload, source_ip, request.state.request_id
        )

    @app.post("/api/v1/modules/build", status_code=202)
    async def build_modules(payload: ModuleBuildRequest, request: Request):
        source_ip = request.client.host if request.client else "unknown"
        return await deployment.start_build(
            payload, source_ip, request.state.request_id
        )

    @app.post("/api/v1/modules/deploy", status_code=202)
    async def deploy_modules(
        payload: ModuleDeployRequest, request: Request
    ):
        source_ip = request.client.host if request.client else "unknown"
        return await deployment.start_deploy(
            payload, source_ip, request.state.request_id
        )

    @app.get("/api/v1/modules/{environment}/{module}/status")
    async def module_status(environment: str, module: str):
        return await deployment.module_status(environment, module)

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
