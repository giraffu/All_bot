from fastapi import APIRouter, Depends, HTTPException, Header, status
from pydantic import BaseModel
from typing import Optional
import logging

from app.queue_manager import QueueManager
from app.models import TaskStatus

# Instead of importing from main.py, we redefine the dependency here 
# or just import the Redis/Settings to avoid circular imports.
from app.config import settings
from redis.asyncio import Redis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent/task", tags=["agent"])

# Dependency for Redis (duplicated from main.py to avoid circular import)
async def get_redis():
    redis = Redis.from_url(settings.redis_url)
    try:
        yield redis
    finally:
        await redis.close()

# Dependency for QueueManager
async def get_queue_manager(redis: Redis = Depends(get_redis)):
    return QueueManager(redis)

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
    status: str = "idle" # idle or running

def verify_token(authorization: Optional[str] = Header(None)):
    from app.config import settings
    # Assuming AGENT_SECRET_TOKEN is added to settings, or use placeholder
    agent_token = getattr(settings, "agent_secret_token", "super_secret_agent_token_2026")
    if not authorization or authorization != f"Bearer {agent_token}":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing agent token",
        )
    return True

@router.get("/pop")
async def pop_task(
    types: Optional[str] = None,
    authorized: bool = Depends(verify_token),
    queue_manager: QueueManager = Depends(get_queue_manager)
):
    allowed_types = None
    if types:
        allowed_types = [t.strip() for t in types.split(",")]
        
    task_data = await queue_manager.dequeue_task(allowed_types=allowed_types)
    if not task_data:
        raise HTTPException(status_code=404, detail="No pending tasks")
        
    task_id, score = task_data
    task_details = await queue_manager.get_task_status(task_id)
    
    if not task_details:
        raise HTTPException(status_code=404, detail="Task details not found")
        
    return {"task": task_details}

@router.post("/status")
async def update_status(
    req: StatusUpdateRequest, 
    authorized: bool = Depends(verify_token),
    queue_manager: QueueManager = Depends(get_queue_manager)
):
    if req.status == "running":
        if req.progress > 0:
            await queue_manager.update_progress(req.task_id, req.progress)
    elif req.status == "failed":
        await queue_manager.fail_task(req.task_id, req.error)
        
    return {"status": "ok"}

@router.post("/complete")
async def complete_task(
    req: CompleteRequest, 
    authorized: bool = Depends(verify_token),
    queue_manager: QueueManager = Depends(get_queue_manager)
):
    await queue_manager.complete_task(req.task_id, req.result)
    return {"status": "ok"}

@router.post("/heartbeat")
async def heartbeat(
    req: HeartbeatRequest,
    authorized: bool = Depends(verify_token),
    queue_manager: QueueManager = Depends(get_queue_manager)
):
    await queue_manager.update_agent_heartbeat(req.agent_id, req.types, req.status)
    return {"status": "ok"}
