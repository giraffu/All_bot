import pytest
import pytest_asyncio
from datetime import datetime
from sqlalchemy import select

from src.database.models import User
from src.database.core import AsyncSessionLocal
from src.quota import QuotaManager

@pytest_asyncio.fixture
async def setup_db():
    # Setup can be done if needed, but we assume DB is running and accessible.
    # In a real test we would use an in-memory DB or rollback transactions.
    # For this system test, we'll create a dummy user and clean it up.
    user_id = 999999999  # Dummy test user
    
    async with AsyncSessionLocal() as session:
        # Cleanup before
        from sqlalchemy import text
        await session.execute(text("DELETE FROM checkin_history WHERE user_id = :uid"), {"uid": user_id})
        await session.execute(text("DELETE FROM user_logs WHERE user_id = :uid"), {"uid": user_id})
        await session.execute(text("DELETE FROM history WHERE user_id = :uid"), {"uid": user_id})
        user = await session.get(User, user_id)
        if user:
            await session.delete(user)
        await session.commit()
            
    yield user_id
    
    async with AsyncSessionLocal() as session:
        # Cleanup after
        from sqlalchemy import text
        await session.execute(text("DELETE FROM checkin_history WHERE user_id = :uid"), {"uid": user_id})
        await session.execute(text("DELETE FROM user_logs WHERE user_id = :uid"), {"uid": user_id})
        await session.execute(text("DELETE FROM history WHERE user_id = :uid"), {"uid": user_id})
        user = await session.get(User, user_id)
        if user:
            await session.delete(user)
        await session.commit()

@pytest.mark.asyncio
async def test_dual_track_points_system(setup_db):
    user_id = setup_db
    qm = QuotaManager()
    
    # 1. Test user initialization
    credits = await qm.get_credits(user_id)
    assert credits == 20  # Default credits for new user
    
    # Check detailed credits
    perm, temp = await qm.get_detailed_credits(user_id)
    assert perm == 20
    assert temp == 0
    
    # 2. Test Check-in (should give 5 permanent and 15 temporary)
    success = await qm.checkin(user_id=user_id, username="test_user", full_name="Test User", reward=5, temp_reward=15)
    assert success is True
    
    perm, temp = await qm.get_detailed_credits(user_id)
    assert perm == 25  # 20 + 5
    assert temp == 15
    
    total_credits = await qm.get_credits(user_id)
    assert total_credits == 40  # 25 + 15
    
    # Check-in again should fail (already checked in today)
    success_again = await qm.checkin(user_id=user_id)
    assert success_again is False
    
    # 3. Test points consumption (should prioritize temporary points)
    # Deduct 10 points
    await qm.deduct_credits(user_id, 10, task_type="test_deduct")
    perm, temp = await qm.get_detailed_credits(user_id)
    assert temp == 5   # 15 - 10
    assert perm == 25  # Unchanged
    
    # Deduct 10 more points
    await qm.deduct_credits(user_id, 10, task_type="test_deduct_2")
    perm, temp = await qm.get_detailed_credits(user_id)
    assert temp == 0   # 5 - 5
    assert perm == 20  # 25 - 5
    
    # 4. Test points clearance
    # Give some temp points back manually to test clearance
    async with AsyncSessionLocal() as session:
        user = await session.get(User, user_id)
        user.temp_credits = 30
        await session.commit()
        
    perm, temp = await qm.get_detailed_credits(user_id)
    assert temp == 30
    
    await qm.clear_temp_credits()
    
    perm, temp = await qm.get_detailed_credits(user_id)
    assert temp == 0
    assert perm == 20  # Unchanged
