from src.web_api.presenters.user_presenter import build_user_response_from_dashboard_dto
from src.web_api.schemas.auth_schema import UserResponse
from src.web_api.schemas.user_schema import CheckinResponse


async def get_current_user_profile_payload(current_user) -> UserResponse:
    from src.core.user_facade import get_user_dashboard_info

    dto = await get_user_dashboard_info(
        current_user.telegram_id,
        current_user.full_name or current_user.username or "道友",
    )
    return build_user_response_from_dashboard_dto(current_user, dto)


async def perform_user_checkin(current_user) -> CheckinResponse:
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
