import logging

from fastapi import HTTPException

from src.core.task_core import (
    ConcurrencyLimitError,
    CoreDomainError,
    InsufficientCreditsError,
    cancel_user_task,
)
from src.web_api.services.task_submission_service import submit_generation_task


async def cancel_pending_task_payload(*, task_id: str, user_id: int) -> dict[str, str | None]:
    try:
        result = await cancel_user_task(task_id, user_id)
    except CoreDomainError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "status": "success",
        "message": result.get("message", "取消请求已受理"),
        "cancel_state": result.get("state"),
    }


async def submit_generation_task_payload(
    *,
    req,
    current_user,
    get_balance,
    logger: logging.Logger,
):
    try:
        return await submit_generation_task(
            req=req,
            current_user=current_user,
            get_balance=get_balance,
        )
    except ConcurrencyLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except InsufficientCreditsError as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc
    except CoreDomainError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Task submission error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from exc
