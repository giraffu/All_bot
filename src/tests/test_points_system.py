import pytest
import pytest_asyncio

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
async def test_points_system(setup_db):
    user_id = setup_db
    qm = QuotaManager()
    
    # 1. Test user initialization
    credits = await qm.get_credits(user_id)
    assert credits == 20  # Default credits for new user
    
    # 2. Test Check-in (should give 20 permanent)
    success = await qm.checkin(user_id=user_id, username="test_user", full_name="Test User", reward=20)
    assert success is True

    total = await qm.get_credits(user_id)
    assert total == 40  # 20 + 20
    
    # Check-in again should fail (already checked in today)
    success_again = await qm.checkin(user_id=user_id)
    assert success_again is False
    
    # 3. Test points consumption (deducts permanent points)
    # Deduct 10 points
    await qm.deduct_credits(user_id, 10, task_type="test_deduct")
    total = await qm.get_credits(user_id)
    assert total == 30  # 40 - 10
    
    # Deduct 25 points
    await qm.deduct_credits(user_id, 25, task_type="test_deduct")
    total = await qm.get_credits(user_id)
    assert total == 5   # 30 - 25
    
    # 4. Test points clearance (deprecated)
    pass
