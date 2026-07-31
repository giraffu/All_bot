from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from src.database.models import AffiliateRedeem, AffiliateTransaction, User
from src.services.affiliate_usdt_redeem_service import (
    AffiliateUsdtRedeemConflictError,
    complete_affiliate_usdt_redeem,
    create_affiliate_usdt_redeem,
    reject_affiliate_usdt_redeem,
)


ADDRESS = "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs"


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        for table in (User.__table__, AffiliateTransaction.__table__, AffiliateRedeem.__table__):
            await conn.run_sync(table.create)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        db.add(User(id=1, telegram_id=101, username="affiliate", credits=0))
        db.add(User(id=2, telegram_id=102, username="affiliate2", credits=0))
        db.add(
            AffiliateTransaction(
                user_id=1,
                amount_usdt=Decimal("10.0000"),
                transaction_type="COMMISSION_ACCRUAL",
                direction="IN",
                reference_type="TEST",
                reference_id="seed",
                idempotency_key="seed:1",
                status="SUCCESS",
            )
        )
        db.add(
            AffiliateTransaction(
                user_id=2,
                amount_usdt=Decimal("10.0000"),
                transaction_type="COMMISSION_ACCRUAL",
                direction="IN",
                reference_type="TEST",
                reference_id="seed-2",
                idempotency_key="seed:2",
                status="SUCCESS",
            )
        )
        await db.commit()
        yield db
    await engine.dispose()


@pytest.mark.asyncio
async def test_pending_redeem_freezes_then_rejection_releases_balance(session):
    pending = await create_affiliate_usdt_redeem(
        session,
        user_id=1,
        amount_usdt=Decimal("5"),
        payout_address=ADDRESS,
        idempotency_key="request:1",
    )
    assert pending.balance.available_usdt == Decimal("5.0000")
    assert pending.balance.frozen_usdt == Decimal("5.0000")

    with pytest.raises(AffiliateUsdtRedeemConflictError):
        await create_affiliate_usdt_redeem(
            session,
            user_id=1,
            amount_usdt=Decimal("5"),
            payout_address=ADDRESS,
            idempotency_key="request:2",
        )

    rejected = await reject_affiliate_usdt_redeem(
        session,
        redeem_id=pending.redeem_id,
        reason="address confirmation failed",
        processed_by="admin",
    )
    assert rejected.balance.available_usdt == Decimal("10.0000")
    assert rejected.balance.frozen_usdt == Decimal("0.0000")


@pytest.mark.asyncio
async def test_completion_moves_frozen_to_spent_without_second_available_debit(session):
    pending = await create_affiliate_usdt_redeem(
        session,
        user_id=1,
        amount_usdt=Decimal("5"),
        payout_address=ADDRESS,
        idempotency_key="request:complete",
    )
    completed = await complete_affiliate_usdt_redeem(
        session,
        redeem_id=pending.redeem_id,
        payout_tx_hash="a" * 64,
        processed_by="admin",
    )
    assert completed.balance.available_usdt == Decimal("5.0000")
    assert completed.balance.frozen_usdt == Decimal("0.0000")
    assert completed.balance.spent_usdt == Decimal("5.0000")


@pytest.mark.asyncio
async def test_request_idempotency_replays_same_result_and_rejects_conflict(session):
    first = await create_affiliate_usdt_redeem(
        session,
        user_id=1,
        amount_usdt=Decimal("5"),
        payout_address=ADDRESS,
        idempotency_key="request:idempotent",
    )
    replay = await create_affiliate_usdt_redeem(
        session,
        user_id=1,
        amount_usdt=Decimal("5.0000"),
        payout_address=ADDRESS,
        idempotency_key="request:idempotent",
    )

    assert replay.redeem_id == first.redeem_id
    assert replay.balance.frozen_usdt == Decimal("5.0000")
    with pytest.raises(
        AffiliateUsdtRedeemConflictError,
        match="different parameters",
    ):
        await create_affiliate_usdt_redeem(
            session,
            user_id=1,
            amount_usdt=Decimal("6"),
            payout_address=ADDRESS,
            idempotency_key="request:idempotent",
        )


@pytest.mark.asyncio
async def test_admin_actions_are_idempotent_and_opposite_terminal_action_conflicts(
    session,
):
    pending = await create_affiliate_usdt_redeem(
        session,
        user_id=1,
        amount_usdt=Decimal("5"),
        payout_address=ADDRESS,
        idempotency_key="request:admin-idempotent",
    )
    first = await complete_affiliate_usdt_redeem(
        session,
        redeem_id=pending.redeem_id,
        payout_tx_hash="b" * 64,
        processed_by="admin",
    )
    replay = await complete_affiliate_usdt_redeem(
        session,
        redeem_id=pending.redeem_id,
        payout_tx_hash="b" * 64,
        processed_by="admin",
    )

    assert replay.redeem_id == first.redeem_id
    assert replay.balance.spent_usdt == Decimal("5.0000")
    with pytest.raises(AffiliateUsdtRedeemConflictError):
        await reject_affiliate_usdt_redeem(
            session,
            redeem_id=pending.redeem_id,
            reason="late rejection",
            processed_by="admin",
        )


@pytest.mark.asyncio
async def test_payout_transaction_hash_must_be_unique_and_failed_completion_rolls_back(
    session,
):
    first = await create_affiliate_usdt_redeem(
        session,
        user_id=1,
        amount_usdt=Decimal("5"),
        payout_address=ADDRESS,
        idempotency_key="request:first-tx",
    )
    await complete_affiliate_usdt_redeem(
        session,
        redeem_id=first.redeem_id,
        payout_tx_hash="c" * 64,
        processed_by="admin",
    )
    await session.commit()

    second = await create_affiliate_usdt_redeem(
        session,
        user_id=2,
        amount_usdt=Decimal("5"),
        payout_address=ADDRESS,
        idempotency_key="request:second-tx",
    )
    with pytest.raises(
        AffiliateUsdtRedeemConflictError,
        match="transaction hash already used",
    ):
        await complete_affiliate_usdt_redeem(
            session,
            redeem_id=second.redeem_id,
            payout_tx_hash="c" * 64,
            processed_by="admin",
        )
    await session.rollback()

    pending_again = await session.get(AffiliateRedeem, second.redeem_id)
    assert pending_again.status == "PENDING"
    ledger = (
        await session.execute(
            AffiliateTransaction.__table__.select().where(
                AffiliateTransaction.reference_id == str(second.redeem_id)
            )
        )
    ).first()
    assert ledger.status == "PENDING"
