import logging
from typing import Annotated, Optional

from app.agent_router_helpers import (
    check_task_payload,
    complete_task_payload,
    heartbeat_payload,
    pop_task_payload,
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


class CompleteRequest(BaseModel):
    task_id: str
    agent_id: str
    result: str


class HeartbeatRequest(BaseModel):
    agent_id: str
    types: str
    status: str = "idle"  # idle or running


def verify_token(authorization: Optional[str] = Header(None)):
    return verify_agent_token(
        authorization=authorization,
        agent_token=getattr(settings, "agent_secret_token", None),
        logger=logger,
    )


@router.get("/pop")
async def pop_task(
    types: Optional[str] = None,
    _authorized: bool = Depends(verify_token),
    queue_manager: QueueManagerDep = None,
):
    return await pop_task_payload(types=types, queue_manager=queue_manager)


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
    return await update_status_payload(req=req, queue_manager=queue_manager)


@router.post("/complete")
async def complete_task(
    req: CompleteRequest,
    _authorized: bool = Depends(verify_token),
    queue_manager: QueueManagerDep = None,
):
    return await complete_task_payload(req=req, queue_manager=queue_manager)


class TaskHeartbeatRequest(BaseModel):
    task_id: str
    agent_id: Optional[str] = None


@router.post("/task_heartbeat")
async def task_heartbeat(
    req: TaskHeartbeatRequest,
    _authorized: bool = Depends(verify_token),
    queue_manager: QueueManagerDep = None,
):
    return await task_heartbeat_payload(req=req, queue_manager=queue_manager)


@router.post("/heartbeat")
async def heartbeat(
    req: HeartbeatRequest,
    _authorized: bool = Depends(verify_token),
    queue_manager: QueueManagerDep = None,
):
    return await heartbeat_payload(req=req, queue_manager=queue_manager)
