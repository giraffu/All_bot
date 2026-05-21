from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.core.user_facade import BreakthroughConditionDTO, UserDashboardDTO
from src.database.models import User
from src.web_api.services import user_profile_service


@pytest.mark.asyncio
async def test_get_current_user_profile_payload_maps_dashboard_dto(monkeypatch):
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
    dto = UserDashboardDTO(
        first_name="道友",
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
        identity_expire_at=None,
        is_unlocked=True,
        breakthrough_conditions=[
            BreakthroughConditionDTO(
                type="invite",
                target=10,
                current=9,
                done=False,
            )
        ],
    )

    async def fake_get_user_dashboard_info(telegram_id: int, display_name: str):
        assert telegram_id == 12345
        assert display_name == "道友"
        return dto

    monkeypatch.setattr(
        "src.core.user_facade.get_user_dashboard_info",
        fake_get_user_dashboard_info,
    )

    response = await user_profile_service.get_current_user_profile_payload(user)

    assert response.credits == 120
    assert response.user_group == "筑基期"
    assert response.current_identity == "核心弟子"
    assert response.breakthrough_conditions[0].type == "invite"


@pytest.mark.asyncio
async def test_perform_user_checkin_returns_schema_payload(monkeypatch):
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
    perform_checkin = AsyncMock(return_value=(True, 88, "", 7, 5))
    monkeypatch.setattr(
        "src.services.permission_service.permission_service",
        SimpleNamespace(perform_checkin=perform_checkin),
    )

    response = await user_profile_service.perform_user_checkin(user)

    perform_checkin.assert_awaited_once_with(54321, "tester", "测试修士")
    assert response.success is True
    assert response.current_credits == 88
    assert response.total_days == 7
    assert response.reward == 5
