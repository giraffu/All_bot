import logging
import uuid
from contextlib import asynccontextmanager
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
from app.main_t2i_facade_seams import (
    create_t2i_pornmaster_turbo_task_seam,
    enqueue_t2i_task_seam,
    get_immediate_t2i_terminal_response_seam,
    optional_t2i_task_subscription_seam,
    submit_t2i_task_request_seam,
    wait_for_t2i_sync_result_seam,
)
from app.main_t2i_helpers import (
    build_t2i_terminal_response as build_t2i_terminal_response_helper,
    build_t2i_success_response as build_t2i_success_response_helper,
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
from fastapi.responses import FileResponse
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


def _split_task_request(request_model):
    params = request_model.dict()
    task_id = params.pop("task_id")
    priority = params.pop("priority", 0)
    return task_id, priority, params


async def _enqueue_task_from_request(
    *,
    request_model,
    task_type: TaskType,
    queue_manager: QueueManager,
) -> TaskResponse:
    task_id, priority, params = _split_task_request(request_model)
    await queue_manager.enqueue_task(task_type, params, priority, task_id)
    return TaskResponse(task_id=task_id)


async def _enqueue_configured_task(
    *,
    request_model,
    task_key: str,
    queue_manager: QueueManager,
) -> TaskResponse:
    return await _enqueue_task_from_request(
        request_model=request_model,
        task_type=SIMPLE_TASK_TYPE_MAP[task_key],
        queue_manager=queue_manager,
    )


def _build_result_url(result_path: str) -> str:
    return build_result_url_helper(
        result_path=result_path,
        settings=settings,
    )


def _build_task_event_channel(task_id: str) -> str:
    return build_task_event_channel_helper(task_id)


def _validate_t2i_prompt(prompt: object) -> str:
    return validate_t2i_prompt_helper(prompt)


def _resolve_t2i_priority(request_body: dict, default_priority: int) -> int:
    return resolve_t2i_priority_helper(request_body, default_priority)


def _prepare_t2i_request_payload(
    request_body: dict,
    *,
    default_priority: int,
) -> tuple[str, int, dict[str, str]]:
    return prepare_t2i_request_payload_helper(
        request_body,
        default_priority=default_priority,
        uuid_factory=uuid.uuid4,
        validate_prompt_func=_validate_t2i_prompt,
        resolve_priority_func=_resolve_t2i_priority,
    )


def _build_t2i_success_response(*, task_id: str, result_path: str) -> T2ITaskResponse:
    return build_t2i_success_response_helper(
        task_id=task_id,
        result_path=result_path,
        response_cls=T2ITaskResponse,
        build_result_url_func=_build_result_url,
    )


def _build_t2i_terminal_response(
    *,
    task_id: str,
    status: str | None,
    result_path: str | None,
    error_msg: str | None,
    request_id: str,
) -> T2ITaskResponse | None:
    return build_t2i_terminal_response_helper(
        task_id=task_id,
        status=status,
        result_path=result_path,
        error_msg=error_msg,
        request_id=request_id,
        response_cls=T2ITaskResponse,
        build_result_url_func=_build_result_url,
        logger=logger,
    )


def _decode_t2i_pubsub_message(data: str | bytes) -> dict | None:
    return decode_t2i_pubsub_message_helper(data)


async def _wait_for_t2i_terminal_response(
    *,
    pubsub,
    task_id: str,
    request_id: str,
    timeout: int,
) -> T2ITaskResponse:
    return await wait_for_t2i_terminal_response_helper(
        pubsub=pubsub,
        task_id=task_id,
        request_id=request_id,
        timeout=timeout,
        decode_message_func=_decode_t2i_pubsub_message,
        build_terminal_response_func=_build_t2i_terminal_response,
    )


async def _subscribe_task_events(queue_manager: QueueManager, task_id: str):
    return await subscribe_task_events_helper(
        queue_manager=queue_manager,
        task_id=task_id,
        build_channel_func=_build_task_event_channel,
    )


async def _close_task_event_subscription(*, pubsub, channel: str) -> None:
    await close_task_event_subscription_helper(pubsub=pubsub, channel=channel)


@asynccontextmanager
async def _optional_t2i_task_subscription(
    *,
    async_mode: bool,
    queue_manager: QueueManager,
    task_id: str,
):
    async with optional_t2i_task_subscription_seam(
        async_mode=async_mode,
        queue_manager=queue_manager,
        task_id=task_id,
        optional_t2i_task_subscription_helper=optional_t2i_task_subscription_helper,
        subscribe_task_events_func=_subscribe_task_events,
        close_task_event_subscription_func=_close_task_event_subscription,
    ) as subscription:
        yield subscription


async def _enqueue_t2i_task(
    *,
    queue_manager: QueueManager,
    task_id: str,
    params: dict,
    priority: int,
    request_id: str,
) -> None:
    await enqueue_t2i_task_seam(
        queue_manager=queue_manager,
        task_id=task_id,
        params=params,
        priority=priority,
        request_id=request_id,
        logger=logger,
        enqueue_t2i_task_helper=enqueue_t2i_task_helper,
    )


async def _get_immediate_t2i_terminal_response(
    *,
    queue_manager: QueueManager,
    task_id: str,
    request_id: str,
) -> T2ITaskResponse | None:
    return await get_immediate_t2i_terminal_response_seam(
        queue_manager=queue_manager,
        task_id=task_id,
        request_id=request_id,
        get_immediate_t2i_terminal_response_helper=get_immediate_t2i_terminal_response_helper,
        build_terminal_response_func=_build_t2i_terminal_response,
    )


async def _wait_for_t2i_sync_result(
    *,
    pubsub,
    task_id: str,
    request_id: str,
    queue_manager: QueueManager,
    timeout: int = 60,
) -> T2ITaskResponse:
    return await wait_for_t2i_sync_result_seam(
        pubsub=pubsub,
        task_id=task_id,
        request_id=request_id,
        queue_manager=queue_manager,
        timeout=timeout,
        logger=logger,
        wait_for_t2i_sync_result_helper=wait_for_t2i_sync_result_helper,
        get_immediate_response_func=_get_immediate_t2i_terminal_response,
        wait_for_terminal_response_func=_wait_for_t2i_terminal_response,
    )


async def _submit_t2i_task_request(
    *,
    async_mode: bool,
    queue_manager: QueueManager,
    task_id: str,
    params: dict[str, str],
    task_priority: int,
    request_id: str,
) -> T2ITaskResponse:
    return await submit_t2i_task_request_seam(
        async_mode=async_mode,
        queue_manager=queue_manager,
        task_id=task_id,
        params=params,
        task_priority=task_priority,
        request_id=request_id,
        response_cls=T2ITaskResponse,
        logger=logger,
        submit_t2i_task_request_helper=submit_t2i_task_request_helper,
        optional_subscription_func=_optional_t2i_task_subscription,
        enqueue_t2i_task_func=_enqueue_t2i_task,
        wait_for_sync_result_func=_wait_for_t2i_sync_result,
    )


async def _build_task_status_response(
    *,
    task_id: str,
    queue_manager: QueueManager,
    include_image_url: bool = False,
    include_task_type: bool = False,
) -> TaskStatusResponse:
    return await build_task_status_response_helper(
        task_id=task_id,
        queue_manager=queue_manager,
        include_image_url=include_image_url,
        include_task_type=include_task_type,
        build_result_url_func=_build_result_url,
    )


async def _serve_task_result_file(
    *,
    task_id: str,
    ready_error_detail: str,
    queue_manager: QueueManager,
    minio_client: Optional[Minio],
) -> FileResponse:
    return await serve_task_result_file_helper(
        task_id=task_id,
        ready_error_detail=ready_error_detail,
        queue_manager=queue_manager,
        minio_client=minio_client,
        settings=settings,
        logger=logger,
    )


async def _build_system_workers_response(queue_manager: QueueManager) -> SystemWorkersResponse:
    return await build_system_workers_response_helper(queue_manager)


async def _build_system_status_response(queue_manager: QueueManager) -> SystemStatusResponse:
    return await build_system_status_response_helper(queue_manager)


async def _cancel_task_or_404(queue_manager: QueueManager, task_id: str):
    return await cancel_task_or_404_helper(queue_manager, task_id)


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "central-api"}


register_simple_task_routes(
    app=app,
    task_response_model=TaskResponse,
    queue_manager_dep=QueueManagerDep,
    auth_token_dep=AuthTokenDep,
    enqueue_configured_task_func=_enqueue_configured_task,
)


@app.post("/api/v1/workflows/t2i-pornmaster-turbo", response_model=T2ITaskResponse)
async def create_t2i_pornmaster_turbo_task(
    request: Annotated[dict, Body()],
    queue_manager: QueueManagerDep,
    _token: AuthTokenDep,
    async_mode: Annotated[bool, Query(alias="async")] = True,
    priority: Annotated[int, Query()] = 0,
):
    return await create_t2i_pornmaster_turbo_task_seam(
        request=request,
        queue_manager=queue_manager,
        async_mode=async_mode,
        priority=priority,
        request_id=str(uuid.uuid4()),
        logger=logger,
        prepare_t2i_request_payload_func=_prepare_t2i_request_payload,
        submit_t2i_task_request_func=_submit_t2i_task_request,
    )


@app.delete("/api/tasks/{task_id}")
async def cancel_task(
    task_id: str,
    queue_manager: QueueManagerDep,
    _token: AuthTokenDep,
):
    return await _cancel_task_or_404(queue_manager, task_id)


register_task_status_routes(
    app=app,
    task_status_response_model=TaskStatusResponse,
    queue_manager_dep=QueueManagerDep,
    build_task_status_response_func=_build_task_status_response,
)

register_task_result_routes(
    app=app,
    queue_manager_dep=QueueManagerDep,
    minio_client_dep=MinioClientDep,
    serve_task_result_file_func=_serve_task_result_file,
)


@app.get("/system/workers", response_model=SystemWorkersResponse)
async def get_system_workers(queue_manager: QueueManagerDep):
    return await _build_system_workers_response(queue_manager)


@app.get("/system/status", response_model=SystemStatusResponse)
async def get_system_status(queue_manager: QueueManagerDep):
    return await _build_system_status_response(queue_manager)
