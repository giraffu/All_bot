from unittest.mock import AsyncMock

import pytest

from src.services.permission_identity_priority_service import TRUSTED_USER_PRIORITY_BONUS
from src.services.permission_service import PermissionService


@pytest.mark.asyncio
async def test_calculate_user_priority_newbie_bonus():
    # Setup
    permission_service = PermissionService()
    permission_service.quota_manager.get_user_stats = AsyncMock()

    # Test generation_count < 2
    permission_service.quota_manager.get_user_stats.return_value = {
        "generation_count": 1
    }
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 30 + TRUSTED_USER_PRIORITY_BONUS

    # Test generation_count == 2
    permission_service.quota_manager.get_user_stats.return_value = {
        "generation_count": 2
    }
    permission_service.identity_priority.get_user_group = AsyncMock(return_value="凡人")
    permission_service.identity_priority.get_user_identity = AsyncMock(return_value="外门弟子")
    permission_service.quota_manager.get_daily_usage = AsyncMock(return_value=0)
    priority = await permission_service.calculate_user_priority(123)
    assert priority == TRUSTED_USER_PRIORITY_BONUS  # Fallback to normal calculation


@pytest.mark.asyncio
async def test_calculate_user_priority_low_trust_free_tier_keeps_newbie_base_priority():
    permission_service = PermissionService()
    permission_service.quota_manager.get_user_stats = AsyncMock(
        return_value={"checkin_count": 8, "generation_count": 1}
    )
    permission_service.identity_priority._has_successful_order = AsyncMock(
        return_value=False
    )
    permission_service.identity_priority.get_user_group = AsyncMock()
    permission_service.identity_priority.get_user_identity = AsyncMock()
    permission_service.quota_manager.get_daily_usage = AsyncMock()

    priority = await permission_service.calculate_user_priority(123)

    assert priority == 30
    permission_service.identity_priority.get_user_group.assert_not_awaited()
    permission_service.identity_priority.get_user_identity.assert_not_awaited()
    permission_service.quota_manager.get_daily_usage.assert_not_awaited()


@pytest.mark.asyncio
async def test_calculate_user_priority_low_trust_free_tier_skips_trusted_bonus():
    permission_service = PermissionService()
    permission_service.quota_manager.get_user_stats = AsyncMock(
        return_value={"checkin_count": 8, "generation_count": 10}
    )
    permission_service.identity_priority._has_successful_order = AsyncMock(
        return_value=False
    )
    permission_service.identity_priority.get_user_group = AsyncMock(return_value="筑基期")
    permission_service.identity_priority.get_user_identity = AsyncMock(return_value="外门弟子")
    permission_service.quota_manager.get_daily_usage = AsyncMock(return_value=9)

    priority = await permission_service.calculate_user_priority(123)

    assert priority == 5


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "successful_order_kind",
    ["paid_success_order", "manual_success_order", "gift_success_order"],
)
async def test_calculate_user_priority_success_order_exempts_low_trust(
    successful_order_kind,
):
    permission_service = PermissionService()
    permission_service.quota_manager.get_user_stats = AsyncMock(
        return_value={"checkin_count": 8, "generation_count": 1}
    )
    permission_service.identity_priority._has_successful_order = AsyncMock(
        return_value=True
    )

    priority = await permission_service.calculate_user_priority(123)

    assert priority == 30 + TRUSTED_USER_PRIORITY_BONUS, successful_order_kind


@pytest.mark.asyncio
async def test_is_low_trust_free_tier_user_skips_order_lookup_under_threshold():
    permission_service = PermissionService()
    permission_service.identity_priority._has_successful_order = AsyncMock()

    is_low_trust = (
        await permission_service.identity_priority.is_low_trust_free_tier_user(
            123,
            stats={"checkin_count": 7, "generation_count": 10},
        )
    )

    assert is_low_trust is False
    permission_service.identity_priority._has_successful_order.assert_not_awaited()


@pytest.mark.asyncio
async def test_calculate_user_priority_nascent_soul():
    # Setup
    permission_service = PermissionService()
    permission_service.identity_priority.get_user_group = AsyncMock(return_value="元婴期")
    permission_service.identity_priority.get_user_identity = AsyncMock(return_value="外门弟子")
    permission_service.quota_manager.get_daily_usage = AsyncMock()
    permission_service.quota_manager.get_user_stats = AsyncMock(
        return_value={"generation_count": 10}
    )

    # Rule: [(10, 12), (50, 5), (100, 1)]

    # Test Case 1: 0 usage -> Priority 12
    permission_service.quota_manager.get_daily_usage.return_value = 0
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 52

    # Test Case 2: 9 usage -> Priority 12
    permission_service.quota_manager.get_daily_usage.return_value = 9
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 52

    # Test Case 3: 10 usage -> Priority 5
    permission_service.quota_manager.get_daily_usage.return_value = 10
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 45

    # Test Case 4: 49 usage -> Priority 5
    permission_service.quota_manager.get_daily_usage.return_value = 49
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 45

    # Test Case 5: 100 usage -> Priority 0
    permission_service.quota_manager.get_daily_usage.return_value = 100
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 40


@pytest.mark.asyncio
async def test_calculate_user_priority_golden_core():
    # Setup
    permission_service = PermissionService()
    permission_service.identity_priority.get_user_group = AsyncMock(return_value="金丹期")
    permission_service.identity_priority.get_user_identity = AsyncMock(return_value="外门弟子")
    permission_service.quota_manager.get_daily_usage = AsyncMock()
    permission_service.quota_manager.get_user_stats = AsyncMock(
        return_value={"generation_count": 10}
    )

    # Rule: [(10, 8), (50, 3), (100, 1)]

    # Test Case 1: 0 usage -> Priority 8
    permission_service.quota_manager.get_daily_usage.return_value = 0
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 48

    # Test Case 2: 9 usage -> Priority 8
    permission_service.quota_manager.get_daily_usage.return_value = 9
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 48

    # Test Case 3: 10 usage -> Priority 3
    permission_service.quota_manager.get_daily_usage.return_value = 10
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 43

    # Test Case 4: 49 usage -> Priority 3
    permission_service.quota_manager.get_daily_usage.return_value = 49
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 43

    # Test Case 5: 100 usage -> Priority 0
    permission_service.quota_manager.get_daily_usage.return_value = 100
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 40

    # Test Case 6: 150 usage -> Priority 0
    permission_service.quota_manager.get_daily_usage.return_value = 150
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 40


@pytest.mark.asyncio
async def test_calculate_user_priority_foundation():
    # Setup
    permission_service = PermissionService()
    permission_service.identity_priority.get_user_group = AsyncMock(return_value="筑基期")
    permission_service.identity_priority.get_user_identity = AsyncMock(return_value="外门弟子")
    permission_service.quota_manager.get_daily_usage = AsyncMock()
    permission_service.quota_manager.get_user_stats = AsyncMock(
        return_value={"generation_count": 10}
    )

    # Rule: [(10, 5), (50, 1)]

    # < 10 -> 5
    permission_service.quota_manager.get_daily_usage.return_value = 9
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 45

    # >= 50 -> 0
    permission_service.quota_manager.get_daily_usage.return_value = 50
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 40


@pytest.mark.asyncio
async def test_calculate_user_priority_qi_refining():
    # Setup
    permission_service = PermissionService()
    permission_service.identity_priority.get_user_group = AsyncMock(return_value="练气期")
    permission_service.identity_priority.get_user_identity = AsyncMock(return_value="外门弟子")
    permission_service.quota_manager.get_daily_usage = AsyncMock()
    permission_service.quota_manager.get_user_stats = AsyncMock(
        return_value={"generation_count": 10}
    )

    # Rule: [(10, 3), (50, 1)]

    # < 10 -> 3
    permission_service.quota_manager.get_daily_usage.return_value = 9
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 43

    # >= 50 -> 0
    permission_service.quota_manager.get_daily_usage.return_value = 50
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 40


@pytest.mark.asyncio
async def test_calculate_user_priority_mortal():
    # Setup
    permission_service = PermissionService()
    permission_service.identity_priority.get_user_group = AsyncMock(return_value="凡人")
    permission_service.identity_priority.get_user_identity = AsyncMock(return_value="外门弟子")
    permission_service.quota_manager.get_daily_usage = AsyncMock()
    permission_service.quota_manager.get_user_stats = AsyncMock(
        return_value={"generation_count": 10}
    )

    # Rule: [] (Always 0)

    permission_service.quota_manager.get_daily_usage.return_value = 0
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 40

    permission_service.quota_manager.get_daily_usage.return_value = 100
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 40


@pytest.mark.asyncio
async def test_calculate_user_priority_addition():
    # Setup
    permission_service = PermissionService()
    permission_service.identity_priority.get_user_group = AsyncMock(return_value="金丹期")  # gives 10
    permission_service.identity_priority.get_user_identity = AsyncMock(
        return_value="真传弟子"
    )  # gives 45
    permission_service.quota_manager.get_daily_usage = AsyncMock()
    permission_service.quota_manager.get_user_stats = AsyncMock(
        return_value={"generation_count": 10}
    )

    # Rule: Golden Core (3) + True Disciple (45) -> usage 19: Golden Core=3 (since 10 <= 19 < 50), True Disciple=45 (since 19 < 40)
    permission_service.quota_manager.get_daily_usage.return_value = 19
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 88  # 3 + 45 + trusted bonus

    # Rule: Golden Core (3) + True Disciple (1) -> usage 150: Golden Core=0 (since 150 >= 100), True Disciple=1 (since 150 >= 70)
    permission_service.quota_manager.get_daily_usage.return_value = 150
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 41  # 0 + 1 + trusted bonus


@pytest.mark.asyncio
async def test_build_user_detailed_stats_includes_today_generations():
    permission_service = PermissionService()
    permission_service.quota_manager.get_user_stats = AsyncMock(
        return_value={
            "identity_expire_at": None,
            "invitation_count": 2,
            "checkin_count": 4,
            "generation_count": 11,
            "today_generation_count": 3,
            "total_contributions": 0,
            "approved_contributions": 0,
        }
    )
    permission_service.identity_priority.get_user_group = AsyncMock(
        return_value="练气期"
    )
    permission_service.identity_priority.get_user_identity = AsyncMock(
        return_value="真传弟子"
    )
    permission_service.identity_priority.calculate_user_priority = AsyncMock(
        return_value=48
    )
    permission_service.quota_manager.get_credits = AsyncMock(return_value=2078)
    permission_service.growth_channel.get_invitation_recharge_stats = AsyncMock(
        return_value={}
    )

    stats = await permission_service._build_user_detailed_stats(123)

    assert stats["today_generations"] == 3
