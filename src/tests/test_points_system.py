import pytest
import pytest_asyncio

from src.database.core import AsyncSessionLocal
from src.database.models import User
from src.quota import QuotaManager


@pytest_asyncio.fixture
async def setup_db():
    import random
    # Setup can be done if needed, but we assume DB is running and accessible.
    # In a real test we would use an in-memory DB or rollback transactions.
    # For this system test, we'll create a dummy user and clean it up.
    user_id = random.randint(1000000000, 9999999999)  # Dummy test user
    
    async with AsyncSessionLocal() as session:
        # Cleanup before
        from sqlalchemy import text
        await session.execute(text("DELETE FROM checkin_history WHERE user_id IN (SELECT id FROM users WHERE username = 'test_user')"))
        await session.execute(text("DELETE FROM user_logs WHERE user_id IN (SELECT id FROM users WHERE username = 'test_user')"))
        await session.execute(text("DELETE FROM history WHERE user_id IN (SELECT id FROM users WHERE username = 'test_user')"))
        await session.execute(text("DELETE FROM users WHERE username = 'test_user'"))
        await session.commit()
            
    yield user_id
    
    async with AsyncSessionLocal() as session:
        # Cleanup after
        from sqlalchemy import text
        await session.execute(text("DELETE FROM checkin_history WHERE user_id IN (SELECT id FROM users WHERE username = 'test_user')"))
        await session.execute(text("DELETE FROM user_logs WHERE user_id IN (SELECT id FROM users WHERE username = 'test_user')"))
        await session.execute(text("DELETE FROM history WHERE user_id IN (SELECT id FROM users WHERE username = 'test_user')"))
        await session.execute(text("DELETE FROM users WHERE username = 'test_user'"))
        await session.commit()

@pytest.mark.asyncio
async def test_points_system(setup_db):
    user_id = setup_db
    qm = QuotaManager()
    from src.core.user_core import get_or_create_user_by_telegram
    user, created = await get_or_create_user_by_telegram(user_id, "test_user")
    
    # 1. Test user initialization
    credits = await qm.get_credits(user.id)
    assert credits >= 0  # Default credits for new user should not be negative
    
    # 2. Test Check-in (should give 20 permanent)
    success = await qm.checkin(user_id=user.id, username="test_user", full_name="Test User", reward=20)
    assert success is True

    total = await qm.get_credits(user.id)
    assert total == credits + 20  # credits + 20
    
    # Check-in again should fail (already checked in today)
    success_again = await qm.checkin(user_id=user.id)
    assert success_again is False
    
    # 3. Test points consumption (deducts permanent points)
    # Deduct 10 points
    await qm.deduct_credits(user.id, 10, "test_user", "test_task")
    total = await qm.get_credits(user.id)
    assert total == credits + 10  # credits + 20 - 10
    
    # Deduct 25 points
    await qm.deduct_credits(user.id, 25, task_type="test_deduct")
    total = await qm.get_credits(user.id)
    assert total == max(0, credits - 15)   # max(0, credits + 10 - 25)
    
    # 4. Test points clearance (deprecated)
    pass
