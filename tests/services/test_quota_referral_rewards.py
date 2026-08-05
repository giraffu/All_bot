import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.database.models import (
    History,
    MediaArchiveOutbox,
    MediaArchiveReceipt,
    Referral,
    User,
    UserLog,
)
from src.logger import UserLogger
from src.quota import QuotaManager


async def _create_session_factory(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(User.__table__.create)
        await conn.run_sync(Referral.__table__.create)
        await conn.run_sync(History.__table__.create)
        await conn.run_sync(MediaArchiveOutbox.__table__.create)
        await conn.run_sync(MediaArchiveReceipt.__table__.create)
        await conn.run_sync(UserLog.__table__.create)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr("src.quota.AsyncSessionLocal", session_factory)
    monkeypatch.setattr("src.logger.AsyncSessionLocal", session_factory)
    return engine, session_factory


async def _seed_users(session_factory, inviter_credits=100, invitee_credits=6):
    async with session_factory() as session:
        session.add_all(
            [
                User(id=1, username="inviter", credits=inviter_credits),
                User(id=2, username="invitee", credits=invitee_credits),
            ]
        )
        await session.commit()


async def _load_state(session_factory):
    async with session_factory() as session:
        inviter = await session.get(User, 1)
        invitee = await session.get(User, 2)
        referral = (
            await session.execute(select(Referral).where(Referral.invitee_id == 2))
        ).scalar_one_or_none()
        logs = (
            (await session.execute(select(UserLog).order_by(UserLog.id)))
            .scalars()
            .all()
        )
        return inviter, invitee, referral, logs


@pytest.mark.asyncio
async def test_process_referral_records_invite_without_inviter_credits(monkeypatch):
    engine, session_factory = await _create_session_factory(monkeypatch)
    try:
        await _seed_users(session_factory)

        success = await QuotaManager().process_referral(
            inviter_id=1,
            new_user_id=2,
            new_user_was_created=True,
            new_username="invitee",
        )

        inviter, invitee, referral, logs = await _load_state(session_factory)
        assert success is True
        assert inviter.credits == 100
        assert inviter.referral_count == 1
        assert invitee.invited_by == 1
        assert referral.inviter_id == 1
        assert referral.channel_reward_claimed is False
        assert [(log.operation_type, log.credit_change) for log in logs] == [
            ("welcome_bonus", 6)
        ]
        assert logs[0].current_balance == 6
        assert json.loads(logs[0].extra_info) == {"inviter_id": 1}
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_process_referral_rejects_existing_user_without_side_effects(monkeypatch):
    engine, session_factory = await _create_session_factory(monkeypatch)
    try:
        await _seed_users(session_factory)

        success = await QuotaManager().process_referral(
            inviter_id=1,
            new_user_id=2,
            new_username="invitee",
            new_user_was_created=False,
        )

        inviter, invitee, referral, logs = await _load_state(session_factory)
        assert success is False
        assert inviter.credits == 100
        assert inviter.referral_count == 0
        assert invitee.invited_by is None
        assert referral is None
        assert logs == []
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_process_channel_reward_grants_five_credits_once(monkeypatch):
    engine, session_factory = await _create_session_factory(monkeypatch)
    try:
        await _seed_users(session_factory)
        await QuotaManager().process_referral(
            1, 2, new_user_was_created=True, new_username="invitee"
        )

        first_result = await QuotaManager().process_channel_reward(2)
        second_result = await QuotaManager().process_channel_reward(2)

        inviter, invitee, referral, logs = await _load_state(session_factory)
        assert first_result == 1
        assert second_result is None
        assert inviter.credits == 105
        assert invitee.is_channel_member is True
        assert referral.channel_reward_claimed is True
        reward_logs = [
            (log.operation_type, log.credit_change)
            for log in logs
            if log.operation_type.startswith("referral_reward")
        ]
        assert reward_logs == [("referral_reward_channel", 5)]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_generation_reward_without_channel_grants_ten_once(monkeypatch):
    engine, session_factory = await _create_session_factory(monkeypatch)
    try:
        await _seed_users(session_factory)
        await QuotaManager().process_referral(
            1, 2, new_user_was_created=True, new_username="invitee"
        )

        first_result = await QuotaManager().process_generation_referral_reward(2)
        second_result = await QuotaManager().process_generation_referral_reward(2)

        inviter, _, _, logs = await _load_state(session_factory)
        assert first_result == 1
        assert second_result is None
        assert inviter.credits == 110
        reward_logs = [
            (log.operation_type, log.credit_change)
            for log in logs
            if log.operation_type.startswith("referral_reward")
        ]
        assert reward_logs == [("referral_reward_generation", 10)]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_generation_after_channel_tops_inviter_up_to_ten(monkeypatch):
    engine, session_factory = await _create_session_factory(monkeypatch)
    try:
        await _seed_users(session_factory)
        await QuotaManager().process_referral(
            1, 2, new_user_was_created=True, new_username="invitee"
        )
        await QuotaManager().process_channel_reward(2)

        result = await QuotaManager().process_generation_referral_reward(2)

        inviter, _, _, logs = await _load_state(session_factory)
        assert result == 1
        assert inviter.credits == 110
        reward_logs = [
            (log.operation_type, log.credit_change)
            for log in logs
            if log.operation_type.startswith("referral_reward")
        ]
        assert reward_logs == [
            ("referral_reward_channel", 5),
            ("referral_reward_generation", 5),
        ]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_legacy_initial_reward_counts_toward_new_targets(monkeypatch):
    engine, session_factory = await _create_session_factory(monkeypatch)
    try:
        await _seed_users(session_factory, inviter_credits=105)
        async with session_factory() as session:
            session.add(
                Referral(
                    inviter_id=1,
                    invitee_id=2,
                    channel_reward_claimed=False,
                )
            )
            session.add(
                UserLog(
                    user_id=1,
                    username="inviter",
                    operation_type="referral_reward_initial",
                    credit_change=5,
                    current_balance=105,
                    extra_info=json.dumps({"invitee_id": 2}),
                )
            )
            await session.commit()

        channel_result = await QuotaManager().process_channel_reward(2)
        generation_result = await QuotaManager().process_generation_referral_reward(2)

        inviter, _, referral, logs = await _load_state(session_factory)
        assert channel_result is None
        assert generation_result == 1
        assert inviter.credits == 110
        assert referral.channel_reward_claimed is True
        reward_logs = [
            (log.operation_type, log.credit_change)
            for log in logs
            if log.operation_type.startswith("referral_reward")
        ]
        assert reward_logs == [
            ("referral_reward_initial", 5),
            ("referral_reward_generation", 5),
        ]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_first_logged_generation_triggers_generation_referral_reward(monkeypatch):
    engine, session_factory = await _create_session_factory(monkeypatch)
    try:
        await _seed_users(session_factory)
        await QuotaManager().process_referral(
            1, 2, new_user_was_created=True, new_username="invitee"
        )

        first_created = await UserLogger(2, "invitee").log_task(
            prompt="first",
            input_images=[],
            output_image="first.png",
            task_id=None,
        )
        second_created = await UserLogger(2, "invitee").log_task(
            prompt="second",
            input_images=[],
            output_image="second.png",
            task_id=None,
        )

        inviter, invitee, _, logs = await _load_state(session_factory)
        assert first_created is True
        assert second_created is True
        assert inviter.credits == 110
        assert invitee.generation_count == 2
        reward_logs = [
            (log.operation_type, log.credit_change)
            for log in logs
            if log.operation_type.startswith("referral_reward")
        ]
        assert reward_logs == [("referral_reward_generation", 10)]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_get_user_stats_counts_today_generations(monkeypatch):
    engine, session_factory = await _create_session_factory(monkeypatch)
    try:
        today = datetime.now().replace(hour=10, minute=0, second=0, microsecond=0)
        yesterday = today - timedelta(days=1)
        async with session_factory() as session:
            session.add(User(id=1, username="cultivator", generation_count=9))
            session.add_all(
                [
                    History(
                        user_id=1, task_id="today-1", type="image", created_at=today
                    ),
                    History(
                        user_id=1,
                        task_id="today-2",
                        type="video",
                        created_at=today + timedelta(hours=1),
                    ),
                    History(
                        user_id=1,
                        task_id="yesterday",
                        type="image",
                        created_at=yesterday,
                    ),
                    History(
                        user_id=2,
                        task_id="other-user",
                        type="image",
                        created_at=today,
                    ),
                ]
            )
            await session.commit()

        stats = await QuotaManager().get_user_stats(1)

        assert stats["generation_count"] == 9
        assert stats["today_generation_count"] == 2
    finally:
        await engine.dispose()
