import json

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.database.models import User, UserLog
from src.quota import QuotaManager


async def _create_session_factory(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(User.__table__.create)
        await conn.run_sync(UserLog.__table__.create)

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
