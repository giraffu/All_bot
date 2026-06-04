import logging
import uuid
from contextlib import asynccontextmanager
from typing import Annotated, Optional

# Execution-plane FastAPI entrypoint.
# This app exposes Central API and worker-facing orchestration routes only.
# New user-facing Web/BFF capabilities must be added under `src/web_api`.

from app.config import settings
from app.dependencies import get_queue_manager
from app.main_bootstrap import (
    build_request_state_getter,
    build_verify_token_dependency,
    build_zombie_tasks_loop_runner,
    lifespan as lifespan_helper,
)
from app.models import (
    SystemStatusResponse,
    SystemWorkersResponse,
    T2ITaskResponse,
    TaskResponse,
    TaskStatusResponse,
    TaskType,
)
from app.main_response_helpers import (
    build_system_status_response as build_system_status_response_helper,
    build_system_workers_response as build_system_workers_response_helper,
    cancel_task_or_404 as cancel_task_or_404_helper,
)
from app.main_t2i_wiring import build_t2i_wiring
from app.main_simple_task_routes import (
    enqueue_configured_task as enqueue_configured_task_helper,
    register_simple_task_routes,
)
from app.main_status_result_routes import (
    register_task_result_routes,
    register_task_status_routes,
)
from app.queue_manager import QueueManager
from app.routers import agent
from asgi_correlation_id import CorrelationIdMiddleware
from fastapi import (
    Body,
    Depends,
    FastAPI,
    HTTPException,
    Query,
)
from fastapi.security import HTTPBearer
from minio import Minio

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(fastapi_app: FastAPI):
    async with lifespan_helper(
        fastapi_app=fastapi_app,
        settings=settings,
        logger=logger,
        check_zombie_tasks_loop_func=_check_zombie_tasks_loop,
    ):
        yield


app = FastAPI(title="ComfyUI Middleware", lifespan=lifespan)
app.add_middleware(CorrelationIdMiddleware, header_name="X-Trace-ID")
app.include_router(agent.router)
security = HTTPBearer()
get_minio_client = build_request_state_getter(attr_name="minio_client")
_check_zombie_tasks_loop = build_zombie_tasks_loop_runner(
    settings=settings,
    queue_manager_cls=QueueManager,
    logger=logger,
)
verify_token = build_verify_token_dependency(
    expected_token=settings.auth_token,
    security=security,
)


QueueManagerDep = Annotated[QueueManager, Depends(get_queue_manager)]
AuthTokenDep = Annotated[str, Depends(verify_token)]
MinioClientDep = Annotated[Optional[Minio], Depends(get_minio_client)]
_t2i_wiring = build_t2i_wiring(
    response_cls=T2ITaskResponse,
    task_type=TaskType.T2I_PORNMASTER_TURBO,
    settings=settings,
    logger=logger,
)


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "central-api"}


register_simple_task_routes(
    app=app,
    task_response_model=TaskResponse,
    queue_manager_dep=QueueManagerDep,
    auth_token_dep=AuthTokenDep,
    enqueue_configured_task_func=enqueue_configured_task_helper,
)


@app.post("/api/v1/workflows/t2i-pornmaster-turbo", response_model=T2ITaskResponse)
async def create_t2i_pornmaster_turbo_task(
    request: Annotated[dict, Body()],
    queue_manager: QueueManagerDep,
    _token: AuthTokenDep,
    async_mode: Annotated[bool, Query(alias="async")] = True,
    priority: Annotated[int, Query()] = 0,
):
    request_id = str(uuid.uuid4())
    logger.info(f"[{request_id}] Received T2I task request: {request}")

    try:
        task_id, task_priority, params = _t2i_wiring.prepare_task_request_func(
            request,
            default_priority=priority,
        )
    except HTTPException:
        logger.error(f"[{request_id}] Invalid prompt: {request.get('prompt')}")
        raise

    return await _t2i_wiring.submit_task_request_func(
        async_mode=async_mode,
        queue_manager=queue_manager,
        task_id=task_id,
        params=params,
        task_priority=task_priority,
        request_id=request_id,
    )


@app.delete("/api/tasks/{task_id}")
async def cancel_task(
    task_id: str,
    queue_manager: QueueManagerDep,
    _token: AuthTokenDep,
):
    return await cancel_task_or_404_helper(queue_manager, task_id)


register_task_status_routes(
    app=app,
    task_status_response_model=TaskStatusResponse,
    queue_manager_dep=QueueManagerDep,
    build_task_status_response_func=_t2i_wiring.build_task_status_response_func,
)

register_task_result_routes(
    app=app,
    queue_manager_dep=QueueManagerDep,
    minio_client_dep=MinioClientDep,
    serve_task_result_file_func=_t2i_wiring.serve_task_result_file_func,
)


@app.get("/system/workers", response_model=SystemWorkersResponse)
async def get_system_workers(queue_manager: QueueManagerDep):
    return await build_system_workers_response_helper(queue_manager)


@app.get("/system/status", response_model=SystemStatusResponse)
async def get_system_status(queue_manager: QueueManagerDep):
    return await build_system_status_response_helper(queue_manager)
