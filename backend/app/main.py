import logging
import uuid
from contextlib import asynccontextmanager
from functools import partial
from typing import Annotated, Optional

from app.config import settings
from app.dependencies import get_queue_manager
from app.main_bootstrap import (
    check_zombie_tasks_loop as check_zombie_tasks_loop_helper,
    get_minio_client as get_minio_client_helper,
    lifespan as lifespan_helper,
    verify_token as verify_token_helper,
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
    build_result_url as build_result_url_helper,
    build_system_status_response as build_system_status_response_helper,
    build_system_workers_response as build_system_workers_response_helper,
    build_task_status_response as build_task_status_response_helper,
    cancel_task_or_404 as cancel_task_or_404_helper,
    serve_task_result_file as serve_task_result_file_helper,
)
from app.main_t2i_helpers import (
    build_t2i_terminal_response as build_t2i_terminal_response_helper,
    build_task_event_channel as build_task_event_channel_helper,
    close_task_event_subscription as close_task_event_subscription_helper,
    decode_t2i_pubsub_message as decode_t2i_pubsub_message_helper,
    enqueue_t2i_task as enqueue_t2i_task_helper,
    get_immediate_t2i_terminal_response as get_immediate_t2i_terminal_response_helper,
    optional_t2i_task_subscription as optional_t2i_task_subscription_helper,
    prepare_t2i_request_payload as prepare_t2i_request_payload_helper,
    resolve_t2i_priority as resolve_t2i_priority_helper,
    submit_t2i_task_request as submit_t2i_task_request_helper,
    subscribe_task_events as subscribe_task_events_helper,
    validate_t2i_prompt as validate_t2i_prompt_helper,
    wait_for_t2i_sync_result as wait_for_t2i_sync_result_helper,
    wait_for_t2i_terminal_response as wait_for_t2i_terminal_response_helper,
)
from app.main_simple_task_routes import (
    SIMPLE_TASK_ROUTE_SPECS as SIMPLE_TASK_ROUTE_SPECS_HELPER,
    SIMPLE_TASK_TYPE_MAP as SIMPLE_TASK_TYPE_MAP_HELPER,
    enqueue_configured_task as enqueue_configured_task_helper,
    register_simple_task_routes,
)
from app.main_status_result_routes import (
    TASK_RESULT_ROUTE_SPECS as TASK_RESULT_ROUTE_SPECS_HELPER,
    TASK_STATUS_ROUTE_SPECS as TASK_STATUS_ROUTE_SPECS_HELPER,
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
    Query,
    Request,
)
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from minio import Minio
from src.workflow_mapping_validation import validate_workflow_directory

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(fastapi_app: FastAPI):
    async with lifespan_helper(
        fastapi_app=fastapi_app,
        settings=settings,
        logger=logger,
        check_zombie_tasks_loop_func=check_zombie_tasks_loop,
        validate_workflows_func=validate_workflow_directory,
    ):
        yield


app = FastAPI(title="ComfyUI Middleware", lifespan=lifespan)
app.add_middleware(CorrelationIdMiddleware, header_name="X-Trace-ID")
app.include_router(agent.router)
security = HTTPBearer()


def get_minio_client(request: Request) -> Optional[Minio]:
    return get_minio_client_helper(request)


async def check_zombie_tasks_loop():
    await check_zombie_tasks_loop_helper(
        settings=settings,
        queue_manager_cls=QueueManager,
        logger=logger,
    )


async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    return verify_token_helper(
        credentials=credentials,
        expected_token=settings.auth_token,
    )


QueueManagerDep = Annotated[QueueManager, Depends(get_queue_manager)]
AuthTokenDep = Annotated[str, Depends(verify_token)]
MinioClientDep = Annotated[Optional[Minio], Depends(get_minio_client)]
SIMPLE_TASK_ROUTE_SPECS = SIMPLE_TASK_ROUTE_SPECS_HELPER
SIMPLE_TASK_TYPE_MAP = SIMPLE_TASK_TYPE_MAP_HELPER
TASK_STATUS_ROUTE_SPECS = TASK_STATUS_ROUTE_SPECS_HELPER
TASK_RESULT_ROUTE_SPECS = TASK_RESULT_ROUTE_SPECS_HELPER

def _build_result_url(result_path: str) -> str:
    return build_result_url_helper(
        result_path=result_path,
        settings=settings,
    )

_build_t2i_terminal_response_func = partial(
    build_t2i_terminal_response_helper,
    response_cls=T2ITaskResponse,
    build_result_url_func=_build_result_url,
    logger=logger,
)
_wait_for_t2i_terminal_response_func = partial(
    wait_for_t2i_terminal_response_helper,
    decode_message_func=decode_t2i_pubsub_message_helper,
    build_terminal_response_func=_build_t2i_terminal_response_func,
)
_subscribe_task_events_func = partial(
    subscribe_task_events_helper,
    build_channel_func=build_task_event_channel_helper,
)
_optional_t2i_task_subscription_func = partial(
    optional_t2i_task_subscription_helper,
    subscribe_task_events_func=_subscribe_task_events_func,
    close_task_event_subscription_func=close_task_event_subscription_helper,
)
_enqueue_t2i_task_func = partial(
    enqueue_t2i_task_helper,
    task_type=TaskType.T2I_PORNMASTER_TURBO,
    logger=logger,
)
_get_immediate_t2i_terminal_response_func = partial(
    get_immediate_t2i_terminal_response_helper,
    build_terminal_response_func=_build_t2i_terminal_response_func,
)
_wait_for_t2i_sync_result_func = partial(
    wait_for_t2i_sync_result_helper,
    logger=logger,
    get_immediate_response_func=_get_immediate_t2i_terminal_response_func,
    wait_for_terminal_response_func=_wait_for_t2i_terminal_response_func,
)
_submit_t2i_task_request_func = partial(
    submit_t2i_task_request_helper,
    response_cls=T2ITaskResponse,
    optional_subscription_func=_optional_t2i_task_subscription_func,
    enqueue_t2i_task_func=_enqueue_t2i_task_func,
    wait_for_sync_result_func=_wait_for_t2i_sync_result_func,
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
        task_id, task_priority, params = prepare_t2i_request_payload_helper(
            request,
            default_priority=priority,
            uuid_factory=uuid.uuid4,
            validate_prompt_func=validate_t2i_prompt_helper,
            resolve_priority_func=resolve_t2i_priority_helper,
        )
    except HTTPException:
        logger.error(f"[{request_id}] Invalid prompt: {request.get('prompt')}")
        raise

    return await _submit_t2i_task_request_func(
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
    build_task_status_response_func=partial(
        build_task_status_response_helper,
        build_result_url_func=_build_result_url,
    ),
)

register_task_result_routes(
    app=app,
    queue_manager_dep=QueueManagerDep,
    minio_client_dep=MinioClientDep,
    serve_task_result_file_func=partial(
        serve_task_result_file_helper,
        settings=settings,
        logger=logger,
    ),
)


@app.get("/system/workers", response_model=SystemWorkersResponse)
async def get_system_workers(queue_manager: QueueManagerDep):
    return await build_system_workers_response_helper(queue_manager)


@app.get("/system/status", response_model=SystemStatusResponse)
async def get_system_status(queue_manager: QueueManagerDep):
    return await build_system_status_response_helper(queue_manager)
