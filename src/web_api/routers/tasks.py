import logging

from fastapi import APIRouter, Depends, HTTPException

from src.core.task_core import (
    ConcurrencyLimitError,
    CoreDomainError,
    InsufficientCreditsError,
)
from src.database.models import User
from src.quota import QuotaManager
from sqlalchemy.ext.asyncio import AsyncSession
from src.web_api.dependencies import get_current_user, get_current_user_once, get_db
from src.web_api.schemas.task_schema import (
    TaskGenerateRequest,
    TaskGenerateResponse,
    TaskResultResponse,
    TaskStatusResponse,
)
from src.web_api.services.task_result_service import get_task_result_payload
from src.web_api.services.task_submission_service import submit_generation_task
from src.web_api.services.user_task_api_service import cancel_pending_task_payload
from src.web_api.services.task_runtime_api_service import (
    build_task_status_stream_response_for_user,
    get_queue_status_payload,
    get_task_status_payload_for_user,
)

router = APIRouter()
logger = logging.getLogger(__name__)
quota_manager = QuotaManager()


@router.delete("/cancel/{task_id}")
async def cancel_pending_task(task_id: str, current_user: User = Depends(get_current_user)):
    return await cancel_pending_task_payload(task_id=task_id, user_id=current_user.id)

@router.post("/generate", response_model=TaskGenerateResponse)
async def create_generation_task(
    req: TaskGenerateRequest, current_user: User = Depends(get_current_user)
):
    """
    Submit a generation task (image/video).
    """
    try:
        return await submit_generation_task(
            req=req,
            current_user=current_user,
            get_balance=quota_manager.get_credits,
            logger=logger,
        )
    except ConcurrencyLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except InsufficientCreditsError as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc
    except CoreDomainError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.get("/{task_id}/result", response_model=TaskResultResponse)
async def get_task_result(
    task_id: str, 
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get task generation result directly.
    """
    return await get_task_result_payload(
        task_id=task_id,
        current_user=current_user,
        db=db,
    )


@router.get(
    "/{task_id}/status",
    response_model=TaskStatusResponse,
    response_model_exclude_none=True,
)
async def get_task_status(
    task_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Get coarse task status for low-frequency user-facing polling.
    """
    return await get_task_status_payload_for_user(
        task_id=task_id,
        user_id=current_user.id,
    )


@router.get("/{task_id}/stream")
async def task_status_stream(
    task_id: str,
    current_user: User = Depends(get_current_user_once),
):
    """
    SSE Endpoint for real-time task progress tracking.
    Listens to Redis Pub/Sub channel: comfy:task_events:{task_id}
    Also periodically sends queue position while pending.
    """
    return await build_task_status_stream_response_for_user(
        task_id=task_id,
        user_id=current_user.id,
        logger_override=logger,
    )


@router.get("/queue-status")
async def get_queue_status(_current_user: User = Depends(get_current_user)) -> dict:
    """获取当前系统的排队宏观大盘数据"""
    return await get_queue_status_payload()
