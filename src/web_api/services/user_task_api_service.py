from typing import Any

from fastapi import HTTPException

from src.core.task_core import CoreDomainError, cancel_user_task
from src.services.language_runtime_service import persist_user_language_preference
from src.web_api.schemas.auth_schema import UserResponse
from src.web_api.schemas.user_schema import CheckinResponse


async def get_current_user_profile_payload(current_user: Any) -> UserResponse:
    from src.core.user_facade import get_user_dashboard_info
    from src.web_api.presenters.user_presenter import build_user_response_from_dashboard_dto

    dto = await get_user_dashboard_info(
        current_user.telegram_id,
        current_user.full_name or current_user.username or "道友",
    )
    return build_user_response_from_dashboard_dto(current_user, dto)


async def perform_user_checkin(current_user: Any) -> CheckinResponse:
    from src.services.permission_service import permission_service

    (
        success,
        current_credits,
        error_msg,
        total_days,
        reward,
    ) = await permission_service.perform_checkin(
        current_user.telegram_id,
        current_user.username or "",
        current_user.full_name or "",
    )

    return CheckinResponse(
        success=success,
        current_credits=current_credits,
        error_msg=error_msg,
        total_days=total_days,
        reward=reward,
    )


async def update_user_language_preference_payload(
    *,
    db,
    user_id: int,
    telegram_user_id: int | None,
    language_code: str,
    persist_language_fn=None,
) -> dict[str, str]:
    if persist_language_fn is None:
        persist_language_fn = persist_user_language_preference
    normalized_lang = await persist_language_fn(
        db=db,
        internal_user_id=user_id,
        telegram_user_id=telegram_user_id,
        language_code=language_code,
    )
    return {"status": "success", "language_code": normalized_lang}


async def cancel_pending_task_payload(
    *,
    task_id: str,
    user_id: int,
    cancel_user_task_fn=None,
) -> dict[str, str | None]:
    if cancel_user_task_fn is None:
        cancel_user_task_fn = cancel_user_task
    try:
        result = await cancel_user_task_fn(task_id, user_id)
    except CoreDomainError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "status": "success",
        "message": result.get("message", "取消请求已受理"),
        "cancel_state": result.get("state"),
    }
