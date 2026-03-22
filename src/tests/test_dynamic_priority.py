import pytest
from unittest.mock import AsyncMock
from src.services.permission_service import PermissionService

@pytest.mark.asyncio
async def test_calculate_user_priority_newbie_bonus():
    # Setup
    permission_service = PermissionService()
    permission_service.quota_manager.get_user_stats = AsyncMock()
    
    # Test generation_count < 2
    permission_service.quota_manager.get_user_stats.return_value = {"generation_count": 1}
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 30

    # Test generation_count == 2
    permission_service.quota_manager.get_user_stats.return_value = {"generation_count": 2}
    permission_service.get_user_group = AsyncMock(return_value="凡人")
    permission_service.get_user_identity = AsyncMock(return_value="外门弟子")
    permission_service.quota_manager.get_daily_usage = AsyncMock(return_value=0)
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 0 # Fallback to normal calculation

@pytest.mark.asyncio
async def test_calculate_user_priority_golden_core():
    # Setup
    permission_service = PermissionService()
    permission_service.get_user_group = AsyncMock(return_value="金丹期")
    permission_service.get_user_identity = AsyncMock(return_value="外门弟子")
    permission_service.quota_manager.get_daily_usage = AsyncMock()
    permission_service.quota_manager.get_user_stats = AsyncMock(return_value={"generation_count": 10})
    
    # Test Case 1: 0 usage -> Priority 10 (updated rules)
    permission_service.quota_manager.get_daily_usage.return_value = 0
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 10

    # Test Case 2: 4 usage -> Priority 10
    permission_service.quota_manager.get_daily_usage.return_value = 4
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 10

    # Test Case 3: 5 usage -> Priority 5
    permission_service.quota_manager.get_daily_usage.return_value = 5
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 5

    # Test Case 4: 10 usage -> Priority 2
    permission_service.quota_manager.get_daily_usage.return_value = 10
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 2

    # Test Case 5: 20 usage -> Priority 0
    permission_service.quota_manager.get_daily_usage.return_value = 20
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 0

@pytest.mark.asyncio
async def test_calculate_user_priority_foundation():
    # Setup
    permission_service = PermissionService()
    permission_service.get_user_group = AsyncMock(return_value="筑基期")
    permission_service.get_user_identity = AsyncMock(return_value="外门弟子")
    permission_service.quota_manager.get_daily_usage = AsyncMock()
    permission_service.quota_manager.get_user_stats = AsyncMock(return_value={"generation_count": 10})
    
    # Rule: [(5, 5), (10, 2)]
    
    # < 5 -> 5
    permission_service.quota_manager.get_daily_usage.return_value = 4
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 5
    
    # 5 to 9 -> 2
    permission_service.quota_manager.get_daily_usage.return_value = 5
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 2
    
    # >= 10 -> 0
    permission_service.quota_manager.get_daily_usage.return_value = 10
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 0

@pytest.mark.asyncio
async def test_calculate_user_priority_qi_refining():
    # Setup
    permission_service = PermissionService()
    permission_service.get_user_group = AsyncMock(return_value="练气期")
    permission_service.get_user_identity = AsyncMock(return_value="外门弟子")
    permission_service.quota_manager.get_daily_usage = AsyncMock()
    permission_service.quota_manager.get_user_stats = AsyncMock(return_value={"generation_count": 10})

    # Rule: [(5, 2), (10, 1)]

    # < 5 -> 2
    permission_service.quota_manager.get_daily_usage.return_value = 4
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 2

    # 5 to 9 -> 1
    permission_service.quota_manager.get_daily_usage.return_value = 5
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 1

    # >= 10 -> 0
    permission_service.quota_manager.get_daily_usage.return_value = 10
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 0

@pytest.mark.asyncio
async def test_calculate_user_priority_mortal():
    # Setup
    permission_service = PermissionService()
    permission_service.get_user_group = AsyncMock(return_value="凡人")
    permission_service.get_user_identity = AsyncMock(return_value="外门弟子")
    permission_service.quota_manager.get_daily_usage = AsyncMock()
    permission_service.quota_manager.get_user_stats = AsyncMock(return_value={"generation_count": 10})

    # Rule: [] -> Always 0

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
    permission_service.get_user_group = AsyncMock(return_value="金丹期") # gives 5
    permission_service.get_user_identity = AsyncMock(return_value="真传弟子") # gives 40
    permission_service.quota_manager.get_daily_usage = AsyncMock()
    permission_service.quota_manager.get_user_stats = AsyncMock(return_value={"generation_count": 10})

    # Rule: Golden Core (10) + True Disciple (50)
    permission_service.quota_manager.get_daily_usage.return_value = 4
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 55

    # Rule: Golden Core (10, 5) + True Disciple (50, 20)
    permission_service.quota_manager.get_daily_usage.return_value = 45
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 20 # 0 + 20
