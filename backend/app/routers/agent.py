import logging
from typing import Annotated, Any, Dict, Optional

# Worker/agent protocol routes only.
# User-facing Web APIs must stay in `src/web_api` to keep the entrypoint split clear.

from app.agent_router_helpers import (
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
from app.dependencies import get_queue_manager
from app.queue_manager import QueueManager
from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent/task", tags=["agent"])
QueueManagerDep = Annotated[QueueManager, Depends(get_queue_manager)]


class StatusUpdateRequest(BaseModel):
    task_id: str
    agent_id: str
    status: str
    progress: float = 0.0
    error: str = ""
    execution_phase: Optional[str] = None
    cancel_locked: Optional[bool] = None
    set_current: bool = True


class CompleteRequest(BaseModel):
    task_id: str
    agent_id: str
    result: str
    extra_outputs: Optional[Dict[str, Any]] = None


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
):
    return await complete_task_payload(
        task_id=req.task_id,
        agent_id=req.agent_id,
        result=req.result,
        extra_outputs=req.extra_outputs,
        queue_manager=queue_manager,
    )


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
