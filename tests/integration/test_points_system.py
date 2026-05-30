import pytest
import pytest_asyncio
from sqlalchemy import select

from src.core.exceptions import InsufficientCreditsError
from src.database.core import AsyncSessionLocal
from src.database.models import UserLog
from src.quota import QuotaManager


@pytest_asyncio.fixture
async def setup_db():
    import random
    from src.database.core import engine as db_engine

    # Setup can be done if needed, but we assume DB is running and accessible.
    # In a real test we would use an in-memory DB or rollback transactions.
    # For this system test, we'll create a dummy user and clean it up.
    user_id = random.randint(1000000000, 9999999999)  # Dummy test user

    await db_engine.dispose()

    async with AsyncSessionLocal() as session:
        # Cleanup before
        from sqlalchemy import text

        await session.execute(
            text(
                "DELETE FROM checkin_history WHERE user_id IN (SELECT id FROM users WHERE username = 'test_user')"
            )
        )
        await session.execute(
            text(
                "DELETE FROM user_logs WHERE user_id IN (SELECT id FROM users WHERE username = 'test_user')"
            )
        )
        await session.execute(
            text(
                "DELETE FROM history WHERE user_id IN (SELECT id FROM users WHERE username = 'test_user')"
            )
        )
        await session.execute(text("DELETE FROM users WHERE username = 'test_user'"))
        await session.commit()

    yield user_id

    await db_engine.dispose()

    async with AsyncSessionLocal() as session:
        # Cleanup after
        from sqlalchemy import text

        await session.execute(
            text(
                "DELETE FROM checkin_history WHERE user_id IN (SELECT id FROM users WHERE username = 'test_user')"
            )
        )
        await session.execute(
            text(
                "DELETE FROM user_logs WHERE user_id IN (SELECT id FROM users WHERE username = 'test_user')"
            )
        )
        await session.execute(
            text(
                "DELETE FROM history WHERE user_id IN (SELECT id FROM users WHERE username = 'test_user')"
            )
        )
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
    success = await qm.checkin(
        user_id=user.id, username="test_user", full_name="Test User", reward=20
    )
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

    # Deduct 25 points should fail atomically instead of silently clamping to zero
    with pytest.raises(InsufficientCreditsError):
        await qm.deduct_credits(user.id, 25, task_type="test_deduct")

    total = await qm.get_credits(user.id)
    assert total == credits + 10

    # Deprecated clearance path has been removed from the runtime contract.
    # Keep the regression focused on the active credit add/checkin/deduct chain.


@pytest.mark.asyncio
async def test_adjust_credits_with_external_transaction_persists_audit_log(setup_db):
    user_id = setup_db
    qm = QuotaManager()
    from src.core.user_core import get_or_create_user_by_telegram

    user, _ = await get_or_create_user_by_telegram(user_id, "test_user")

    async with AsyncSessionLocal() as session:
        async with session.begin():
            result = await qm.add_credits(
                user.id,
                7,
                username="test_user",
                task_type="external_tx_credit_add",
                session=session,
                extra_info={"reason": "tx_reuse_test"},
            )
            assert result.new_balance >= result.old_balance + 7

    async with AsyncSessionLocal() as session:
        log = (
            await session.execute(
                select(UserLog)
                .where(
                    UserLog.user_id == user.id,
                    UserLog.operation_type == "external_tx_credit_add",
                )
                .order_by(UserLog.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    assert log is not None
    assert log.credit_change == 7
    assert '"old_balance"' in (log.extra_info or "")
    assert '"reason": "tx_reuse_test"' in (log.extra_info or "")
