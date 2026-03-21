import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.services.permission_service import PermissionService
from src.constants import DYNAMIC_PRIORITY_RULES

@pytest.mark.asyncio
async def test_calculate_user_priority_newbie_bonus():
    # Setup
    permission_service = PermissionService()
    permission_service.get_user_group = AsyncMock(return_value="凡人")
    permission_service.get_user_identity = AsyncMock(return_value="外门弟子")
    permission_service.quota_manager.get_daily_usage = AsyncMock(return_value=0)
    
    # generation_count < 5 -> Priority 30
    permission_service.quota_manager.get_user_stats = AsyncMock(return_value={"generation_count": 2})
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 30

@pytest.mark.asyncio
async def test_calculate_user_priority_golden_core():
    # Setup
    permission_service = PermissionService()
    permission_service.get_user_group = AsyncMock(return_value="金丹期")
    permission_service.get_user_identity = AsyncMock(return_value="外门弟子")
    permission_service.quota_manager.get_daily_usage = AsyncMock()
    permission_service.quota_manager.get_user_stats = AsyncMock(return_value={"generation_count": 10})

    # Test Case 1: 0 usage -> Priority 3
    permission_service.quota_manager.get_daily_usage.return_value = 0
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 3

    # Test Case 2: 49 usage -> Priority 3
    permission_service.quota_manager.get_daily_usage.return_value = 49
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 3

    # Test Case 3: 50 usage -> Priority 2 (Next tier starts at 50)
    # Rule: [(50, 3), (100, 2)...] -> if usage < 50 return 3. So 50 is not < 50. Next rule.
    permission_service.quota_manager.get_daily_usage.return_value = 50
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 2

    # Test Case 4: 99 usage -> Priority 2
    permission_service.quota_manager.get_daily_usage.return_value = 99
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 2

    # Test Case 5: 100 usage -> Priority 1
    permission_service.quota_manager.get_daily_usage.return_value = 100
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 1

    # Test Case 6: 200 usage -> Priority 0
    permission_service.quota_manager.get_daily_usage.return_value = 200
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

    # Rule: [(25, 2), (50, 1)]

    # < 25 -> 2
    permission_service.quota_manager.get_daily_usage.return_value = 10
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 2

    # 25 -> 1
    permission_service.quota_manager.get_daily_usage.return_value = 25
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 1

    # 50 -> 0
    permission_service.quota_manager.get_daily_usage.return_value = 50
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

    # Rule: [(15, 1)]

    # < 15 -> 1
    permission_service.quota_manager.get_daily_usage.return_value = 10
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 1

    # 15 -> 0
    permission_service.quota_manager.get_daily_usage.return_value = 15
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
    permission_service.get_user_group = AsyncMock(return_value="金丹期") # gives 3
    permission_service.get_user_identity = AsyncMock(return_value="真传弟子") # gives 40
    permission_service.quota_manager.get_daily_usage = AsyncMock()
    permission_service.quota_manager.get_user_stats = AsyncMock(return_value={"generation_count": 10})

    # Rule: Golden Core (50, 3) + True Disciple (50, 40)
    permission_service.quota_manager.get_daily_usage.return_value = 10
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 43 # 3 + 40
    
    # Rule: Golden Core (100, 2) + True Disciple (100, 20)
    permission_service.quota_manager.get_daily_usage.return_value = 75
    priority = await permission_service.calculate_user_priority(123)
    assert priority == 22 # 2 + 20
