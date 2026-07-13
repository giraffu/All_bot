import json

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.database.models import User, UserLog
from src.quota import QuotaManager


async def _create_session_factory(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(User.__table__.create)
        await conn.run_sync(UserLog.__table__.create)
        await conn.exec_driver_sql(
            """
            CREATE TABLE private_bot_task_submissions (
                submission_key VARCHAR(128) PRIMARY KEY,
                internal_user_id BIGINT NOT NULL,
                debit_confirmed_at DATETIME NULL,
                updated_at DATETIME NULL,
                actual_cost INTEGER NULL,
                status VARCHAR(32) NOT NULL,
                compensation_status VARCHAR(32) NOT NULL
            )
            """
        )

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr("src.quota.AsyncSessionLocal", session_factory)
    return engine, session_factory


@pytest.mark.asyncio
async def test_add_credits_idempotency_key_applies_credit_once(monkeypatch):
    engine, session_factory = await _create_session_factory(monkeypatch)
    try:
        async with session_factory() as session:
            session.add(User(id=1, username="tester", credits=10))
            await session.commit()

        quota = QuotaManager()
        first = await quota.add_credits(
            1,
            90,
            username="tester",
            task_type="refund_user_cancel",
            idempotency_key="task_refund:refund_user_cancel:registry-1",
        )
        second = await quota.add_credits(
            1,
            90,
            username="tester",
            task_type="refund_user_cancel",
            idempotency_key="task_refund:refund_user_cancel:registry-1",
        )

        async with session_factory() as session:
            user = await session.get(User, 1)
            logs = (
                await session.execute(select(UserLog).order_by(UserLog.id))
            ).scalars().all()

        assert first.old_balance == 10
        assert first.new_balance == 100
        assert second.old_balance == 100
        assert second.new_balance == 100
        assert user.credits == 100
        assert [(log.operation_type, log.credit_change) for log in logs] == [
            ("refund_user_cancel", 90)
        ]
        assert json.loads(logs[0].extra_info) == {
            "old_balance": 10,
            "credit_idempotency_key": "task_refund:refund_user_cancel:registry-1",
        }
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_deduct_credits_idempotency_key_applies_debit_once(monkeypatch):
    engine, session_factory = await _create_session_factory(monkeypatch)
    try:
        async with session_factory() as session:
            session.add(User(id=2, username="visitor", credits=100))
            await session.execute(
                text(
                    """
                    INSERT INTO private_bot_task_submissions (
                        submission_key,
                        internal_user_id,
                        actual_cost,
                        status,
                        compensation_status
                    ) VALUES (
                        'private_bot_update:9:101:0',
                        2,
                        25,
                        'reserved',
                        'not_required'
                    )
                    """
                )
            )
            await session.commit()

        quota = QuotaManager()
        first = await quota.deduct_credits(
            2,
            25,
            username="visitor",
            task_type="quick_image",
            idempotency_key="task_debit:private_bot_update:9:101:0",
        )
        second = await quota.deduct_credits(
            2,
            25,
            username="visitor",
            task_type="quick_image",
            idempotency_key="task_debit:private_bot_update:9:101:0",
        )

        async with session_factory() as session:
            user = await session.get(User, 2)
            logs = (
                await session.execute(select(UserLog).order_by(UserLog.id))
            ).scalars().all()
            debit_confirmed_at = (
                await session.execute(
                    text(
                        "SELECT debit_confirmed_at FROM private_bot_task_submissions"
                    )
                )
            ).scalar_one()

        assert (first.old_balance, first.new_balance) == (100, 75)
        assert (second.old_balance, second.new_balance) == (75, 75)
        assert user.credits == 75
        assert [(log.operation_type, log.credit_change) for log in logs] == [
            ("quick_image", -25)
        ]
        assert json.loads(logs[0].extra_info)["credit_idempotency_key"] == (
            "task_debit:private_bot_update:9:101:0"
        )
        assert debit_confirmed_at is not None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_private_debit_rolls_back_after_orphan_compensation_fence(monkeypatch):
    engine, session_factory = await _create_session_factory(monkeypatch)
    try:
        async with session_factory() as session:
            session.add(User(id=4, username="visitor", credits=100))
            await session.execute(
                text(
                    """
                    INSERT INTO private_bot_task_submissions (
                        submission_key,
                        internal_user_id,
                        actual_cost,
                        status,
                        compensation_status
                    ) VALUES (
                        'private_bot_update:9:102:0',
                        4,
                        25,
                        'failed',
                        'completed'
                    )
                    """
                )
            )
            await session.commit()

        with pytest.raises(
            RuntimeError,
            match="no longer accepts this debit",
        ):
            await QuotaManager().deduct_credits(
                4,
                25,
                username="visitor",
                task_type="quick_image",
                idempotency_key="task_debit:private_bot_update:9:102:0",
            )

        async with session_factory() as session:
            user = await session.get(User, 4)
            logs = (await session.execute(select(UserLog))).scalars().all()
        assert user.credits == 100
        assert logs == []
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_private_debit_rolls_back_when_ledger_cost_differs(monkeypatch):
    engine, session_factory = await _create_session_factory(monkeypatch)
    try:
        async with session_factory() as session:
            session.add(User(id=5, username="visitor", credits=100))
            await session.execute(
                text(
                    """
                    INSERT INTO private_bot_task_submissions (
                        submission_key,
                        internal_user_id,
                        actual_cost,
                        status,
                        compensation_status
                    ) VALUES (
                        'private_bot_update:9:103:0',
                        5,
                        25,
                        'reserved',
                        'not_required'
                    )
                    """
                )
            )
            await session.commit()

        with pytest.raises(
            RuntimeError,
            match="no longer accepts this debit",
        ):
            await QuotaManager().deduct_credits(
                5,
                20,
                username="visitor",
                task_type="quick_image",
                idempotency_key="task_debit:private_bot_update:9:103:0",
            )

        async with session_factory() as session:
            user = await session.get(User, 5)
            logs = (await session.execute(select(UserLog))).scalars().all()
        assert user.credits == 100
        assert logs == []
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_credit_idempotency_key_dedupes_across_refund_reasons(monkeypatch):
    engine, session_factory = await _create_session_factory(monkeypatch)
    try:
        async with session_factory() as session:
            session.add(User(id=3, username="visitor", credits=10))
            await session.commit()

        quota = QuotaManager()
        await quota.add_credits(
            3,
            6,
            task_type="refund_restart",
            idempotency_key="task_refund:task:deterministic-task",
        )
        replay = await quota.add_credits(
            3,
            6,
            task_type="refund_zombie_cleanup",
            idempotency_key="task_refund:task:deterministic-task",
        )

        async with session_factory() as session:
            user = await session.get(User, 3)
            logs = (
                await session.execute(select(UserLog).order_by(UserLog.id))
            ).scalars().all()

        assert user.credits == 16
        assert replay.old_balance == replay.new_balance == 16
        assert len(logs) == 1
        assert await quota.has_credit_idempotency_entry(
            user_id=3,
            idempotency_key="task_refund:task:deterministic-task",
            expected_credit_change=6,
        )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_canonical_refund_key_recognizes_pre_upgrade_reason_key(monkeypatch):
    engine, session_factory = await _create_session_factory(monkeypatch)
    try:
        async with session_factory() as session:
            session.add(User(id=6, username="visitor", credits=100))
            session.add(
                UserLog(
                    user_id=6,
                    username="visitor",
                    operation_type="refund_user_cancel",
                    credit_change=6,
                    current_balance=100,
                    extra_info=json.dumps(
                        {
                            "old_balance": 94,
                            "credit_idempotency_key": (
                                "task_refund:refund_user_cancel:legacy-task"
                            ),
                        }
                    ),
                )
            )
            await session.commit()

        replay = await QuotaManager().add_credits(
            6,
            6,
            username="visitor",
            task_type="refund_private_submission",
            idempotency_key="task_refund:task:legacy-task",
        )
        with pytest.raises(
            ValueError,
            match="different amount",
        ):
            await QuotaManager().add_credits(
                6,
                7,
                username="visitor",
                task_type="refund_private_submission",
                idempotency_key="task_refund:task:legacy-task",
            )

        async with session_factory() as session:
            user = await session.get(User, 6)
            logs = (await session.execute(select(UserLog))).scalars().all()
        assert replay.old_balance == replay.new_balance == 100
        assert user.credits == 100
        assert len(logs) == 1
    finally:
        await engine.dispose()
