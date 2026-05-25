import logging

from fastapi import HTTPException

from src.core.task_core import (
    CoreDomainError,
    cancel_user_task,
)


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
