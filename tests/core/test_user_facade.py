from unittest.mock import AsyncMock

import pytest

from src.core.user_facade import get_user_dashboard_info


@pytest.mark.asyncio
async def test_get_user_dashboard_info_accepts_explicit_stats_dependency():
    get_stats = AsyncMock(
        return_value={
            "group": "练气期",
            "identity": "内门弟子",
            "priority": 3,
            "credits": 88,
            "invitations": 2,
            "checkins": 4,
            "generations": 11,
            "invitation_recharge": {"total_rmb": 12.5},
            "identity_expire_at": None,
        }
    )

    dto = await get_user_dashboard_info(
        12345,
        "道友",
        get_user_detailed_stats_func=get_stats,
    )

    get_stats.assert_awaited_once_with(12345)
    assert dto.first_name == "道友"
    assert dto.current_group == "练气期"
    assert dto.current_identity == "内门弟子"
    assert dto.current_priority == 3
    assert dto.credits == 88
    assert dto.is_unlocked is True
    assert [condition.type for condition in dto.breakthrough_conditions] == [
        "invite",
        "checkin",
        "generation",
    ]


@pytest.mark.asyncio
async def test_get_user_dashboard_info_builds_mortal_breakthrough_condition():
    dto = await get_user_dashboard_info(
        7,
        "新修士",
        get_user_detailed_stats_func=AsyncMock(
            return_value={
                "group": "凡人",
                "identity": "凡人",
                "priority": 0,
                "credits": 3,
                "invitations": 0,
                "checkins": 0,
                "generations": 0,
                "invitation_recharge": {},
                "identity_expire_at": None,
            }
        ),
    )

    assert dto.is_unlocked is False
    assert len(dto.breakthrough_conditions) == 1
    assert dto.breakthrough_conditions[0].type == "channel_join"
    assert dto.breakthrough_conditions[0].done is False
