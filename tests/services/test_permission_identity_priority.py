from unittest.mock import AsyncMock

import pytest

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
    assert priority == 30

    # Test generation_count == 2
    permission_service.quota_manager.get_user_stats.return_value = {
        "generation_count": 2
    }
    permission_service.identity_priority.get_user_group = AsyncMock(return_value="凡人")
    permission_service.identity_priority.get_user_identity = AsyncMock(return_value="外门弟子")
    permission_service.quota_manager.get_daily_usage = AsyncMock(return_value=0)
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 0  # Fallback to normal calculation


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
    assert priority == 12

    # Test Case 2: 9 usage -> Priority 12
    permission_service.quota_manager.get_daily_usage.return_value = 9
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 12

    # Test Case 3: 10 usage -> Priority 5
    permission_service.quota_manager.get_daily_usage.return_value = 10
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 5

    # Test Case 4: 49 usage -> Priority 5
    permission_service.quota_manager.get_daily_usage.return_value = 49
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 5

    # Test Case 5: 100 usage -> Priority 0
    permission_service.quota_manager.get_daily_usage.return_value = 100
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 0


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
    assert priority == 8

    # Test Case 2: 9 usage -> Priority 8
    permission_service.quota_manager.get_daily_usage.return_value = 9
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 8

    # Test Case 3: 10 usage -> Priority 3
    permission_service.quota_manager.get_daily_usage.return_value = 10
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 3

    # Test Case 4: 49 usage -> Priority 3
    permission_service.quota_manager.get_daily_usage.return_value = 49
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 3

    # Test Case 5: 100 usage -> Priority 0
    permission_service.quota_manager.get_daily_usage.return_value = 100
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 0

    # Test Case 6: 150 usage -> Priority 0
    permission_service.quota_manager.get_daily_usage.return_value = 150
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 0


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
    assert priority == 5

    # >= 50 -> 0
    permission_service.quota_manager.get_daily_usage.return_value = 50
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 0


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
    assert priority == 3

    # >= 50 -> 0
    permission_service.quota_manager.get_daily_usage.return_value = 50
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 0


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
    assert priority == 0

    permission_service.quota_manager.get_daily_usage.return_value = 100
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 0


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
    assert priority == 48  # 3 + 45

    # Rule: Golden Core (3) + True Disciple (1) -> usage 150: Golden Core=0 (since 150 >= 100), True Disciple=1 (since 150 >= 70)
    permission_service.quota_manager.get_daily_usage.return_value = 150
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 1  # 0 + 1
