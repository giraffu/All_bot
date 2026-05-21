from datetime import datetime

from src.core.user_facade import BreakthroughConditionDTO, UserDashboardDTO
from src.database.models import User
from src.web_api.presenters.user_presenter import (
    build_token_user_payload,
    build_user_response_from_auth_stats,
    build_user_response_from_dashboard_dto,
)


def test_build_user_response_from_auth_stats_maps_auth_fields():
    user = User(
        id=1,
        telegram_id=12345,
        username="dao",
        full_name="道友",
        language_code="zh-hans",
        credits=10,
        user_group="凡人",
        current_identity="外门弟子",
    )

    response = build_user_response_from_auth_stats(
        user,
        {
            "credits": 88,
            "group": "练气期",
            "identity": "内门弟子",
            "priority": 3,
            "identity_expire_at": datetime(2026, 5, 21, 10, 0, 0),
            "generations": 7,
            "checkins": 4,
            "invitations": 2,
            "invitation_recharge": {
                "recharged_invitees_count": 1,
                "total_recharge_count": 3,
                "total_ton": 2.5,
            },
        },
    )

    assert response.credits == 88
    assert response.user_group == "练气期"
    assert response.current_identity == "内门弟子"
    assert response.priority == 3
    assert response.generation_count == 7
    assert response.checkin_count == 4
    assert response.invitation_count == 2
    assert response.invitation_recharge is not None
    assert response.invitation_recharge.total_ton == 2.5


def test_build_user_response_from_dashboard_dto_maps_profile_fields():
    user = User(
        id=2,
        telegram_id=54321,
        username="tester",
        full_name="测试修士",
        language_code="zh-hans",
        credits=5,
        user_group="凡人",
        current_identity="外门弟子",
    )
    dto = UserDashboardDTO(
        first_name="测试修士",
        current_group="筑基期",
        current_identity="核心弟子",
        current_priority=6,
        credits=120,
        invitations=9,
        checkins=12,
        generations=34,
        invitation_recharge={
            "recharged_invitees_count": 2,
            "total_recharge_count": 5,
            "total_rmb": 88.0,
        },
        is_unlocked=True,
        breakthrough_conditions=[
            BreakthroughConditionDTO(
                type="invite",
                target=10,
                current=9,
                done=False,
            )
        ],
        identity_expire_at=datetime(2026, 6, 1, 0, 0, 0),
    )

    response = build_user_response_from_dashboard_dto(user, dto)

    assert response.user_group == "筑基期"
    assert response.current_identity == "核心弟子"
    assert response.credits == 120
    assert response.priority == 6
    assert response.invitation_count == 9
    assert response.breakthrough_conditions[0].type == "invite"
    assert response.is_unlocked is True


def test_build_token_user_payload_wraps_user_response():
    user = User(
        id=3,
        telegram_id=10001,
        username="payload",
        full_name="封装测试",
        language_code="zh-hans",
        credits=66,
        user_group="练气期",
        current_identity="内门弟子",
    )
    user_response = build_user_response_from_auth_stats(user, None)

    payload = build_token_user_payload(
        access_token="jwt-token",
        user_response=user_response,
    )

    assert payload["access_token"] == "jwt-token"
    assert payload["token_type"] == "bearer"
    assert payload["user"]["id"] == 3
    assert payload["user"]["credits"] == 66
