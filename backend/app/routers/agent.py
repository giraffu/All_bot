import logging
from typing import Annotated, Any, Dict, Optional

# Worker/agent protocol routes only.
# User-facing Web APIs must stay in `src/web_api` to keep the entrypoint split clear.

from app.agent_router_helpers import (
    append_text_delta_payload,
    check_task_payload,
    complete_task_payload,
    get_agent_control_payload,
    heartbeat_payload,
    peek_task_payload,
    pop_task_payload,
    set_agent_control_payload,
    task_heartbeat_payload,
    update_status_payload,
    verify_agent_token,
)
from app.config import settings
from app.dependencies import get_minio_client, get_queue_manager
from app.queue_manager import QueueManager
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from pydantic import Field
from src.services.task_text_stream_store import TextStreamConflictError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent/task", tags=["agent"])
QueueManagerDep = Annotated[QueueManager, Depends(get_queue_manager)]
MinioClientDep = Annotated[Any, Depends(get_minio_client)]


class StatusUpdateRequest(BaseModel):
    task_id: str
    agent_id: str
    status: str
    progress: float = 0.0
    error: str = ""
    execution_phase: Optional[str] = None
    cancel_locked: Optional[bool] = None
    set_current: bool = True
    attempt_id: Optional[str] = None


class CompleteRequest(BaseModel):
    task_id: str
    agent_id: str
    result: str
    extra_outputs: Optional[Dict[str, Any]] = None
    result_asset: Optional[Dict[str, Any]] = None
    extra_output_assets: Optional[Dict[str, Any]] = None
    result_kind: Optional[str] = None
    result_text: Optional[str] = None
    result_meta: Optional[Dict[str, Any]] = None
    attempt_id: Optional[str] = None


class TextDeltaRequest(BaseModel):
    task_id: str
    agent_id: str
    attempt_id: str
    sequence: int = Field(ge=1)
    field: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    delta: str = Field(min_length=1, max_length=2000)


class HeartbeatRequest(BaseModel):
    agent_id: str
    types: str
    status: str = "idle"
    health_reason: str = ""
    last_error: str = ""
    last_error_at: Optional[Any] = None
    consecutive_failures: Optional[Any] = None
    quarantined_until: Optional[Any] = None
    node_id: Optional[str] = None
    provider: Optional[str] = None
    gpu_index: Optional[Any] = None
    runtime_profile: Optional[str] = None
    image_ref: Optional[str] = None
    model_bundle_versions: Optional[Any] = None
    pool_managed: Optional[Any] = None


class AgentControlRequest(BaseModel):
    state: str
    reason: str = ""
    ttl_seconds: Optional[int] = None


def verify_token(authorization: Optional[str] = Header(None)):
    return verify_agent_token(
        authorization=authorization,
        agent_token=getattr(settings, "agent_secret_token", None),
        logger=logger,
    )


@router.get("/pop")
async def pop_task(
    types: Optional[str] = None,
    preferred_types: Optional[str] = None,
    agent_id: Optional[str] = None,
    cancel_lock: bool = False,
    _authorized: bool = Depends(verify_token),
    queue_manager: QueueManagerDep = None,
):
    return await pop_task_payload(
        types=types,
        preferred_types=preferred_types,
        agent_id=agent_id,
        queue_manager=queue_manager,
        cancel_lock=cancel_lock,
    )


@router.get("/peek")
async def peek_task(
    types: Optional[str] = None,
    preferred_types: Optional[str] = None,
    limit: int = 1,
    _authorized: bool = Depends(verify_token),
    queue_manager: QueueManagerDep = None,
):
    return await peek_task_payload(
        types=types,
        preferred_types=preferred_types,
        limit=limit,
        queue_manager=queue_manager,
    )


@router.get("/check/{task_id}")
async def check_task(
    task_id: str,
    _authorized: bool = Depends(verify_token),
    queue_manager: QueueManagerDep = None,
):
    return await check_task_payload(task_id=task_id, queue_manager=queue_manager)


@router.post("/status")
async def update_status(
    req: StatusUpdateRequest,
    _authorized: bool = Depends(verify_token),
    queue_manager: QueueManagerDep = None,
):
    return await update_status_payload(
        task_id=req.task_id,
        agent_id=req.agent_id,
        status=req.status,
        progress=req.progress,
        error=req.error,
        execution_phase=req.execution_phase,
        cancel_locked=req.cancel_locked,
        set_current=req.set_current,
        queue_manager=queue_manager,
    )


@router.post("/complete")
async def complete_task(
    req: CompleteRequest,
    _authorized: bool = Depends(verify_token),
    queue_manager: QueueManagerDep = None,
    minio_client: MinioClientDep = None,
):
    return await complete_task_payload(
        task_id=req.task_id,
        agent_id=req.agent_id,
        result=req.result,
        extra_outputs=req.extra_outputs,
        result_asset=req.result_asset,
        extra_output_assets=req.extra_output_assets,
        result_kind=req.result_kind,
        result_text=req.result_text,
        result_meta=req.result_meta,
        minio_client=minio_client,
        result_bucket=settings.minio_result_bucket,
        queue_manager=queue_manager,
    )


@router.post("/text-delta")
async def append_text_delta(
    req: TextDeltaRequest,
    _authorized: bool = Depends(verify_token),
    queue_manager: QueueManagerDep = None,
):
    try:
        return await append_text_delta_payload(
            task_id=req.task_id,
            agent_id=req.agent_id,
            attempt_id=req.attempt_id,
            sequence=req.sequence,
            field=req.field,
            delta=req.delta,
            queue_manager=queue_manager,
        )
    except (ValueError, TextStreamConflictError) as exc:
        code = getattr(exc, "code", "invalid_attempt_id")
        detail: dict[str, Any] = {"code": code}
        expected_sequence = getattr(exc, "expected_sequence", None)
        if expected_sequence is not None:
            detail["expected_sequence"] = expected_sequence
        raise HTTPException(status_code=409, detail=detail) from exc


class TaskHeartbeatRequest(BaseModel):
    task_id: str
    agent_id: Optional[str] = None


@router.post("/task_heartbeat")
async def task_heartbeat(
    req: TaskHeartbeatRequest,
    _authorized: bool = Depends(verify_token),
    queue_manager: QueueManagerDep = None,
):
    return await task_heartbeat_payload(
        task_id=req.task_id,
        agent_id=req.agent_id,
        queue_manager=queue_manager,
    )


@router.post("/heartbeat")
async def heartbeat(
    req: HeartbeatRequest,
    _authorized: bool = Depends(verify_token),
    queue_manager: QueueManagerDep = None,
):
    metadata = {
        "node_id": req.node_id,
        "provider": req.provider,
        "gpu_index": req.gpu_index,
        "runtime_profile": req.runtime_profile,
        "image_ref": req.image_ref,
        "model_bundle_versions": req.model_bundle_versions,
        "pool_managed": req.pool_managed,
    }
    return await heartbeat_payload(
        agent_id=req.agent_id,
        types=req.types,
        status=req.status,
        health_reason=req.health_reason,
        last_error=req.last_error,
        last_error_at=req.last_error_at,
        consecutive_failures=req.consecutive_failures,
        quarantined_until=req.quarantined_until,
        metadata=metadata,
        queue_manager=queue_manager,
    )


@router.post("/control/{agent_id}")
async def set_agent_control(
    agent_id: str,
    req: AgentControlRequest,
    _authorized: bool = Depends(verify_token),
    queue_manager: QueueManagerDep = None,
):
    return await set_agent_control_payload(
        agent_id=agent_id,
        state=req.state,
        reason=req.reason,
        ttl_seconds=req.ttl_seconds,
        queue_manager=queue_manager,
    )


@router.get("/control/{agent_id}")
async def get_agent_control(
    agent_id: str,
    _authorized: bool = Depends(verify_token),
    queue_manager: QueueManagerDep = None,
):
    return await get_agent_control_payload(agent_id=agent_id, queue_manager=queue_manager)
