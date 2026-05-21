from typing import Any

from src.core.user_facade import UserDashboardDTO
from src.database.models import User
from src.web_api.schemas.auth_schema import InvitationRechargeStats, UserResponse


def _build_invitation_recharge_stats(
    payload: dict[str, Any] | None,
) -> InvitationRechargeStats | None:
    if not payload:
        return None
    return InvitationRechargeStats(**payload)


def build_user_response_from_auth_stats(
    user: User,
    stats: dict[str, Any] | None,
) -> UserResponse:
    resolved_stats = stats or {}
    return UserResponse(
        id=user.id,
        telegram_id=user.telegram_id,
        username=user.username,
        full_name=user.full_name,
        language_code=user.language_code,
        credits=resolved_stats.get("credits", user.credits),
        user_group=resolved_stats.get("group", user.user_group),
        current_identity=resolved_stats.get("identity", user.current_identity),
        priority=resolved_stats.get("priority", 0),
        identity_expire_at=resolved_stats.get("identity_expire_at"),
        total_contributions=resolved_stats.get("total_contributions", 0),
        generation_count=resolved_stats.get("generations", 0),
        checkin_count=resolved_stats.get("checkins", 0),
        invitation_count=resolved_stats.get("invitations", 0),
        invitation_recharge=_build_invitation_recharge_stats(
            resolved_stats.get("invitation_recharge")
        ),
    )


def build_user_response_from_dashboard_dto(
    user: User,
    dto: UserDashboardDTO,
) -> UserResponse:
    return UserResponse(
        id=user.id,
        telegram_id=user.telegram_id,
        username=user.username,
        full_name=user.full_name,
        language_code=user.language_code,
        credits=dto.credits,
        user_group=dto.current_group,
        current_identity=dto.current_identity,
        identity_expire_at=dto.identity_expire_at,
        priority=dto.current_priority,
        generation_count=dto.generations,
        checkin_count=dto.checkins,
        invitation_count=dto.invitations,
        invitation_recharge=InvitationRechargeStats(**dto.invitation_recharge),
        breakthrough_conditions=[
            condition.model_dump() for condition in dto.breakthrough_conditions
        ],
        is_unlocked=dto.is_unlocked,
    )


def build_token_user_payload(
    *,
    access_token: str,
    user_response: UserResponse,
) -> dict[str, Any]:
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user_response.model_dump(),
    }
