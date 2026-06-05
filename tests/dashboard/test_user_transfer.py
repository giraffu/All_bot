from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from dashboard.backend.routers import users as dashboard_users_router
from dashboard.backend.schemas import TransferUserDataRequest
from dashboard.backend.services import user_admin_service
from src.database.models import (
    AffiliateRedeem,
    AffiliateTransaction,
    CheckinHistory,
    GalleryComment,
    GalleryPost,
    GalleryPromptUnlock,
    History,
    MembershipPlan,
    Order,
    Referral,
    TemplateContribution,
    User,
    UserFollow,
    UserInteraction,
    UserLog,
)


async def _create_transfer_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    event.listen(
        engine.sync_engine,
        "connect",
        lambda dbapi_connection, _connection_record: dbapi_connection.create_function(
            "greatest",
            2,
            lambda left, right: max(left, right),
        ),
    )
    async with engine.begin() as conn:
        await conn.run_sync(User.__table__.create)
        await conn.run_sync(UserFollow.__table__.create)
        await conn.run_sync(MembershipPlan.__table__.create)
        await conn.run_sync(Referral.__table__.create)
        await conn.run_sync(History.__table__.create)
        await conn.run_sync(TemplateContribution.__table__.create)
        await conn.run_sync(CheckinHistory.__table__.create)
        await conn.run_sync(UserLog.__table__.create)
        await conn.run_sync(Order.__table__.create)
        await conn.run_sync(AffiliateTransaction.__table__.create)
        await conn.run_sync(AffiliateRedeem.__table__.create)
        await conn.run_sync(GalleryPost.__table__.create)
        await conn.run_sync(UserInteraction.__table__.create)
        await conn.run_sync(GalleryPromptUnlock.__table__.create)
        await conn.run_sync(GalleryComment.__table__.create)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    session = session_factory()
    return engine, session


@pytest.mark.asyncio
async def test_transfer_user_data_payload_moves_business_data_and_deletes_source(monkeypatch):
    engine, session = await _create_transfer_session()
    now = datetime.now()
    source_expire = now + timedelta(days=10)
    target_expire = now + timedelta(days=5)

    inviter = User(id=9, username="master", full_name="Master", credits=99)
    source = User(
        id=1,
        username="source",
        full_name="Source User",
        credits=10,
        checkin_count=2,
        generation_count=5,
        total_contributions=1,
        approved_contributions=1,
        current_identity="内门弟子",
        identity_expire_at=source_expire,
        is_channel_member=True,
        last_checkin=date(2026, 5, 20),
        last_activity=now - timedelta(days=2),
        invited_by=9,
        created_at=now - timedelta(days=10),
    )
    target = User(
        id=2,
        username="target",
        full_name="Target User",
        credits=6,
        checkin_count=3,
        generation_count=8,
        total_contributions=2,
        approved_contributions=0,
        current_identity="核心弟子",
        identity_expire_at=target_expire,
        is_channel_member=False,
        last_checkin=date(2026, 5, 18),
        last_activity=now - timedelta(days=1),
        created_at=now - timedelta(days=5),
    )
    invited_user = User(
        id=10,
        username="invitee",
        full_name="Invitee User",
        credits=3,
        invited_by=1,
    )
    session.add_all(
        [
            inviter,
            source,
            target,
            invited_user,
            MembershipPlan(
                id=1,
                name="Test Plan",
                identity_name="内门弟子",
                reward_credits=10,
                duration_days=30,
                price_ton=1,
                price_stars=100,
                price_rmb=10,
                is_active=True,
            ),
            Referral(inviter_id=9, invitee_id=1),
            Referral(inviter_id=1, invitee_id=10),
            History(user_id=1, task_id="task-1", type="image", prompt="hello"),
            TemplateContribution(user_id=1, file_path="foo.png", file_type="photo"),
            CheckinHistory(user_id=1, checkin_date=date(2026, 5, 20)),
            UserLog(
                user_id=1,
                username="source",
                operation_type="generate",
                credit_change=-1,
                current_balance=9,
            ),
            Order(
                order_id="order-1",
                internal_user_id=1,
                plan_id=1,
                original_price=10,
                final_price=10,
                status="SUCCESS",
                tx_hash="tx-source",
                payment_channel="RMB",
            ),
            AffiliateTransaction(
                user_id=1,
                amount_usdt=1.5,
                transaction_type="COMMISSION_ACCRUAL",
                direction="IN",
                reference_type="ORDER",
                reference_id="1",
                idempotency_key="aff-tx-1",
                status="SUCCESS",
            ),
            AffiliateRedeem(
                user_id=1,
                redeem_type="CREDITS",
                redeem_option_key="c100",
                requested_amount_usdt=1,
                amount_usdt=1,
                credits_granted=100,
                idempotency_key="aff-rd-1",
                status="SUCCESS",
            ),
            GalleryPost(id=100, task_id="task-1", user_id=1, media_type="image", likes_count=2),
            GalleryPost(id=101, task_id="task-2", user_id=2, media_type="image", applied_count=2),
            GalleryPost(id=102, task_id="task-3", user_id=2, media_type="image", dislikes_count=1),
            GalleryComment(post_id=100, user_id=1, content="hello comment", is_active=True),
            UserInteraction(user_id=2, post_id=100, action_type="like"),
            UserInteraction(user_id=1, post_id=100, action_type="like"),
            UserInteraction(user_id=2, post_id=101, action_type="apply"),
            UserInteraction(user_id=1, post_id=101, action_type="apply"),
            UserInteraction(user_id=1, post_id=102, action_type="dislike"),
        ]
    )
    await session.commit()

    log_action = AsyncMock()
    monkeypatch.setattr("src.services.log_service.LogService.log_action", log_action)

    result = await user_admin_service.transfer_user_data_payload(
        user_id=1,
        request=TransferUserDataRequest(target_user_id=2, note="test merge"),
        db=session,
    )

    assert result["status"] == "ok"
    assert result["source_user_id"] == 1
    assert result["target_user_id"] == 2
    assert result["moved_counts"]["history_rows"] == 1
    assert result["moved_counts"]["duplicate_reactions_deleted"] == 1
    assert result["moved_counts"]["duplicate_applies_deleted"] == 1
    assert result["moved_counts"]["source_user_deleted"] == 1
    log_action.assert_awaited_once()

    assert await session.get(User, 1) is None
    merged_target = await session.get(User, 2)
    assert merged_target.credits == 16
    assert merged_target.checkin_count == 5
    assert merged_target.generation_count == 13
    assert merged_target.total_contributions == 3
    assert merged_target.approved_contributions == 1
    assert merged_target.current_identity == "核心弟子"
    assert merged_target.identity_expire_at > now + timedelta(days=8)
    assert merged_target.user_group == "练气期"
    assert merged_target.referral_count == 1
    assert merged_target.is_channel_member is True
    assert merged_target.last_checkin == date(2026, 5, 20)
    assert merged_target.created_at == now - timedelta(days=10)

    history_row = (
        await session.execute(select(History.user_id).where(History.task_id == "task-1"))
    ).scalar_one()
    assert history_row == 2

    template_row = (
        await session.execute(select(TemplateContribution.user_id))
    ).scalar_one()
    assert template_row == 2

    checkin_count = (
        await session.execute(select(func.count(CheckinHistory.id)).where(CheckinHistory.user_id == 2))
    ).scalar_one()
    assert checkin_count == 1

    order_owner = (
        await session.execute(select(Order.internal_user_id).where(Order.order_id == "order-1"))
    ).scalar_one()
    assert order_owner == 2

    affiliate_tx_owner = (
        await session.execute(select(AffiliateTransaction.user_id))
    ).scalar_one()
    assert affiliate_tx_owner == 2

    affiliate_redeem_owner = (
        await session.execute(select(AffiliateRedeem.user_id))
    ).scalar_one()
    assert affiliate_redeem_owner == 2

    invited_by = (
        await session.execute(select(User.invited_by).where(User.id == 10))
    ).scalar_one()
    assert invited_by == 2

    transferred_referral = (
        await session.execute(select(Referral.inviter_id).where(Referral.invitee_id == 10))
    ).scalar_one()
    assert transferred_referral == 2

    target_inviter = (
        await session.execute(select(Referral.inviter_id).where(Referral.invitee_id == 2))
    ).scalar_one()
    assert target_inviter == 9

    likes_count = (
        await session.execute(select(GalleryPost.likes_count).where(GalleryPost.id == 100))
    ).scalar_one()
    assert likes_count == 1

    applied_count = (
        await session.execute(select(GalleryPost.applied_count).where(GalleryPost.id == 101))
    ).scalar_one()
    assert applied_count == 1

    target_interactions = (
        await session.execute(
            select(func.count(UserInteraction.id)).where(UserInteraction.user_id == 2)
        )
    ).scalar_one()
    assert target_interactions == 3

    await session.close()
    await engine.dispose()


@pytest.mark.asyncio
async def test_transfer_user_route_delegates_to_service(monkeypatch):
    expected = {
        "status": "ok",
        "message": "done",
        "source_user_id": 1,
        "target_user_id": 2,
        "moved_counts": {},
        "merged_profile": {},
    }
    db = object()
    request = TransferUserDataRequest(target_user_id=2, note="route")
    service_mock = AsyncMock(return_value=expected)
    monkeypatch.setattr(dashboard_users_router, "transfer_user_data_payload", service_mock)

    response = await dashboard_users_router.transfer_user_data(1, request=request, db=db)

    assert response == expected
    service_mock.assert_awaited_once_with(
        user_id=1,
        request=request,
        db=db,
        logger_override=dashboard_users_router.logger,
    )
