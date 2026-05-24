import asyncio
import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError

from config import DATABASE_URL
from src.core import affiliate_core
from src.database.core import AsyncSessionLocal as DBSessionLocal
from src.database.core import engine as db_engine
from src.database.models import AffiliateRedeem, AffiliateTransaction, User, UserLog
from src.services import affiliate_redeem_service
from src.web_api.core.security import create_access_token
from src.web_api.main import app


pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DATABASE_URL.startswith("postgresql"),
        reason="requires PostgreSQL row locks and unique constraints",
    ),
]


class _TwoPartyGate:
    def __init__(self):
        self._count = 0
        self._lock = asyncio.Lock()
        self._ready = asyncio.Event()

    async def wait(self) -> None:
        async with self._lock:
            self._count += 1
            if self._count >= 2:
                self._ready.set()
        await asyncio.wait_for(self._ready.wait(), timeout=5)


class _ProxySession:
    def __init__(self, session, gate: _TwoPartyGate | None):
        self._session = session
        self._gate = gate

    async def execute(self, stmt, *args, **kwargs):
        if self._gate and self._should_gate(stmt):
            await self._gate.wait()
        return await self._session.execute(stmt, *args, **kwargs)

    def __getattr__(self, item):
        return getattr(self._session, item)

    @staticmethod
    def _should_gate(stmt) -> bool:
        sql = str(stmt)
        return "FROM users" in sql and "FOR UPDATE" in sql


async def _ensure_affiliate_redeem_table() -> None:
    await db_engine.dispose()
    async with db_engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: AffiliateRedeem.__table__.create(
                sync_conn, checkfirst=True
            )
        )


def _unique_suffix() -> str:
    return uuid.uuid4().hex[:12]


async def _create_redeem_fixture(prefix: str, balance_usdt: Decimal) -> dict:
    await _ensure_affiliate_redeem_table()
    async with DBSessionLocal() as session:
        user = User(
            telegram_id=int(f"73{prefix[:8]}", 16) % 9_000_000_000_000_000,
            username=f"redeem_user_{prefix}",
            full_name=f"Redeem User {prefix}",
            credits=0,
        )
        session.add(user)
        await session.flush()

        session.add(
            AffiliateTransaction(
                user_id=user.id,
                amount_usdt=balance_usdt,
                transaction_type="COMMISSION_ACCRUAL",
                direction="IN",
                reference_type="TEST_SEED",
                reference_id=prefix,
                idempotency_key=f"test:affiliate:seed:{prefix}",
                status="SUCCESS",
                details={"seed": True},
            )
        )
        await session.commit()
        return {"user_id": user.id}


async def _cleanup_redeem_fixture(*, user_id: int) -> None:
    async with DBSessionLocal() as session:
        await session.execute(delete(UserLog).where(UserLog.user_id == user_id))
        await session.execute(
            delete(AffiliateRedeem).where(AffiliateRedeem.user_id == user_id)
        )
        await session.execute(
            delete(AffiliateTransaction).where(AffiliateTransaction.user_id == user_id)
        )
        # Commit dependent-row cleanup first to avoid FK ordering surprises in tests
        # that insert additional affiliate ledger rows concurrently.
        await session.commit()
        try:
            await session.execute(delete(User).where(User.id == user_id))
            await session.commit()
        except IntegrityError:
            await session.rollback()
            await session.execute(
                delete(AffiliateRedeem).where(AffiliateRedeem.user_id == user_id)
            )
            await session.execute(
                delete(AffiliateTransaction).where(
                    AffiliateTransaction.user_id == user_id
                )
            )
            await session.execute(delete(User).where(User.id == user_id))
            await session.commit()
    await db_engine.dispose()


async def _load_user_redeem_state(user_id: int) -> dict:
    async with DBSessionLocal() as session:
        user = await session.get(User, user_id)
        redeem_count = (
            await session.execute(
                select(func.count(AffiliateRedeem.id)).where(
                    AffiliateRedeem.user_id == user_id
                )
            )
        ).scalar_one()
        out_count = (
            await session.execute(
                select(func.count(AffiliateTransaction.id)).where(
                    AffiliateTransaction.user_id == user_id,
                    AffiliateTransaction.direction == "OUT",
                    AffiliateTransaction.transaction_type == "CREDITS_REDEEM",
                    AffiliateTransaction.status == "SUCCESS",
                )
            )
        ).scalar_one()
        return {
            "credits": int(user.credits or 0) if user else None,
            "redeem_count": redeem_count,
            "out_count": out_count,
        }


async def _run_redeem(
    *,
    user_id: int,
    amount_usdt: Decimal,
    idempotency_key: str,
    gate: _TwoPartyGate | None = None,
):
    async with DBSessionLocal() as session:
        proxy = _ProxySession(session, gate)
        return await affiliate_redeem_service.redeem_affiliate_balance_to_credits(
            proxy,
            user_id=user_id,
            amount_usdt=amount_usdt,
            idempotency_key=idempotency_key,
        )


async def _run_membership_redeem(
    *,
    user_id: int,
    option_key: str,
    idempotency_key: str,
    gate: _TwoPartyGate | None = None,
):
    async with DBSessionLocal() as session:
        proxy = _ProxySession(session, gate)
        return await affiliate_redeem_service.redeem_affiliate_balance_to_membership(
            proxy,
            user_id=user_id,
            option_key=option_key,
            idempotency_key=idempotency_key,
        )


async def _record_commission_with_user_lock(
    *,
    user_id: int,
    amount_usdt: Decimal,
    locked_event: asyncio.Event,
    release_event: asyncio.Event,
) -> bool:
    async with DBSessionLocal() as session:
        async with session.begin():
            await affiliate_core.lock_affiliate_balance_owner(session, user_id)
            locked_event.set()
            await asyncio.wait_for(release_event.wait(), timeout=5)
            return (
                await session.execute(
                    insert(AffiliateTransaction)
                    .values(
                        user_id=user_id,
                        amount_usdt=amount_usdt,
                        transaction_type="COMMISSION_ACCRUAL",
                        direction="IN",
                        reference_type="TEST_LOCKED_COMMISSION",
                        reference_id=_unique_suffix(),
                        idempotency_key=f"test:affiliate:locked:{_unique_suffix()}",
                        status="SUCCESS",
                        details={"source": "locked_commission"},
                    )
                    .on_conflict_do_nothing(index_elements=["idempotency_key"])
                    .returning(AffiliateTransaction.id)
                )
            ).scalar_one_or_none() is not None


async def _load_membership_redeem_state(user_id: int) -> dict:
    async with DBSessionLocal() as session:
        user = await session.get(User, user_id)
        available_balance = await affiliate_redeem_service.query_affiliate_available_balance(
            session,
            user_id,
        )
        redeem_count = (
            await session.execute(
                select(func.count(AffiliateRedeem.id)).where(
                    AffiliateRedeem.user_id == user_id,
                    AffiliateRedeem.redeem_type == "MEMBERSHIP",
                )
            )
        ).scalar_one()
        out_count = (
            await session.execute(
                select(func.count(AffiliateTransaction.id)).where(
                    AffiliateTransaction.user_id == user_id,
                    AffiliateTransaction.direction == "OUT",
                    AffiliateTransaction.transaction_type == "MEMBERSHIP_REDEEM",
                    AffiliateTransaction.status == "SUCCESS",
                )
            )
        ).scalar_one()
        return {
            "credits": int(user.credits or 0) if user else None,
            "identity": user.current_identity if user else None,
            "available_balance_usdt": available_balance,
            "redeem_count": redeem_count,
            "out_count": out_count,
        }


async def test_affiliate_redeem_concurrent_requests_do_not_double_spend(monkeypatch):
    invalidate_mock = AsyncMock()
    log_action_mock = AsyncMock()
    monkeypatch.setattr(
        affiliate_redeem_service,
        "invalidate_invitation_recharge_cache",
        invalidate_mock,
    )
    monkeypatch.setattr("src.services.log_service.LogService.log_action", log_action_mock)

    fixture = await _create_redeem_fixture(_unique_suffix(), Decimal("1.0000"))
    gate = _TwoPartyGate()

    try:
        results = await asyncio.gather(
            _run_redeem(
                user_id=fixture["user_id"],
                amount_usdt=Decimal("1.0000"),
                idempotency_key="idem-a",
                gate=gate,
            ),
            _run_redeem(
                user_id=fixture["user_id"],
                amount_usdt=Decimal("1.0000"),
                idempotency_key="idem-b",
                gate=gate,
            ),
            return_exceptions=True,
        )

        success_results = [
            result
            for result in results
            if not isinstance(result, Exception)
        ]
        error_results = [
            result for result in results if isinstance(result, Exception)
        ]

        assert len(success_results) == 1
        assert len(error_results) == 1
        assert isinstance(
            error_results[0], affiliate_redeem_service.AffiliateRedeemInsufficientBalanceError
        )
        assert success_results[0].credits_granted == 130

        state = await _load_user_redeem_state(fixture["user_id"])
        assert state == {"credits": 130, "redeem_count": 1, "out_count": 1}
        invalidate_mock.assert_awaited_once_with(fixture["user_id"])
        log_action_mock.assert_awaited_once()
    finally:
        await _cleanup_redeem_fixture(user_id=fixture["user_id"])


async def test_affiliate_redeem_same_idempotency_returns_first_success_result(monkeypatch):
    invalidate_mock = AsyncMock()
    log_action_mock = AsyncMock()
    monkeypatch.setattr(
        affiliate_redeem_service,
        "invalidate_invitation_recharge_cache",
        invalidate_mock,
    )
    monkeypatch.setattr("src.services.log_service.LogService.log_action", log_action_mock)

    fixture = await _create_redeem_fixture(_unique_suffix(), Decimal("3.0000"))
    gate = _TwoPartyGate()

    try:
        result_1, result_2 = await asyncio.gather(
            _run_redeem(
                user_id=fixture["user_id"],
                amount_usdt=Decimal("1.0000"),
                idempotency_key="same-idem",
                gate=gate,
            ),
            _run_redeem(
                user_id=fixture["user_id"],
                amount_usdt=Decimal("1.0000"),
                idempotency_key="same-idem",
                gate=gate,
            ),
        )

        assert result_1.redeem_id == result_2.redeem_id
        assert result_1.credits_granted == result_2.credits_granted == 130
        assert result_1.current_credits == result_2.current_credits == 130

        state = await _load_user_redeem_state(fixture["user_id"])
        assert state == {"credits": 130, "redeem_count": 1, "out_count": 1}
        invalidate_mock.assert_awaited_once_with(fixture["user_id"])
        log_action_mock.assert_awaited_once()
    finally:
        await _cleanup_redeem_fixture(user_id=fixture["user_id"])


async def test_affiliate_redeem_same_idempotency_keeps_first_current_credits_snapshot(
    monkeypatch,
):
    monkeypatch.setattr(
        affiliate_redeem_service,
        "invalidate_invitation_recharge_cache",
        AsyncMock(),
    )
    monkeypatch.setattr("src.services.log_service.LogService.log_action", AsyncMock())

    fixture = await _create_redeem_fixture(_unique_suffix(), Decimal("3.0000"))

    try:
        first = await _run_redeem(
            user_id=fixture["user_id"],
            amount_usdt=Decimal("1.0000"),
            idempotency_key="sticky-current-credits",
        )
        assert first.current_credits == 130

        async with DBSessionLocal() as session:
            user = await session.get(User, fixture["user_id"])
            user.credits = 7
            await session.commit()

        replay = await _run_redeem(
            user_id=fixture["user_id"],
            amount_usdt=Decimal("1.0000"),
            idempotency_key="sticky-current-credits",
        )

        assert replay.redeem_id == first.redeem_id
        assert replay.current_credits == 130
        assert replay.available_balance_usdt == Decimal("2.0000")

        state = await _load_user_redeem_state(fixture["user_id"])
        assert state == {"credits": 7, "redeem_count": 1, "out_count": 1}
    finally:
        await _cleanup_redeem_fixture(user_id=fixture["user_id"])


async def test_affiliate_redeem_same_idempotency_keeps_first_available_balance_snapshot(
    monkeypatch,
):
    monkeypatch.setattr(
        affiliate_redeem_service,
        "invalidate_invitation_recharge_cache",
        AsyncMock(),
    )
    monkeypatch.setattr("src.services.log_service.LogService.log_action", AsyncMock())

    fixture = await _create_redeem_fixture(_unique_suffix(), Decimal("3.0000"))

    try:
        first = await _run_redeem(
            user_id=fixture["user_id"],
            amount_usdt=Decimal("1.0000"),
            idempotency_key="sticky-available-balance",
        )
        assert first.available_balance_usdt == Decimal("2.0000")

        async with DBSessionLocal() as session:
            session.add(
                AffiliateTransaction(
                    user_id=fixture["user_id"],
                    amount_usdt=Decimal("5.0000"),
                    transaction_type="COMMISSION_ACCRUAL",
                    direction="IN",
                    reference_type="TEST_TOPUP",
                    reference_id=_unique_suffix(),
                    idempotency_key=f"test:affiliate:topup:{_unique_suffix()}",
                    status="SUCCESS",
                    details={"seed": "topup"},
                )
            )
            await session.commit()

        replay = await _run_redeem(
            user_id=fixture["user_id"],
            amount_usdt=Decimal("1.0000"),
            idempotency_key="sticky-available-balance",
        )

        assert replay.redeem_id == first.redeem_id
        assert replay.available_balance_usdt == Decimal("2.0000")
    finally:
        await _cleanup_redeem_fixture(user_id=fixture["user_id"])


async def test_affiliate_redeem_same_idempotency_with_different_amount_conflicts(monkeypatch):
    monkeypatch.setattr(
        affiliate_redeem_service,
        "invalidate_invitation_recharge_cache",
        AsyncMock(),
    )
    monkeypatch.setattr("src.services.log_service.LogService.log_action", AsyncMock())

    fixture = await _create_redeem_fixture(_unique_suffix(), Decimal("5.0000"))

    try:
        first = await _run_redeem(
            user_id=fixture["user_id"],
            amount_usdt=Decimal("1.0000"),
            idempotency_key="conflict-idem",
        )
        assert first.credits_granted == 130

        with pytest.raises(affiliate_redeem_service.AffiliateRedeemConflictError):
            await _run_redeem(
                user_id=fixture["user_id"],
                amount_usdt=Decimal("3.0000"),
                idempotency_key="conflict-idem",
            )

        state = await _load_user_redeem_state(fixture["user_id"])
        assert state == {"credits": 130, "redeem_count": 1, "out_count": 1}
    finally:
        await _cleanup_redeem_fixture(user_id=fixture["user_id"])


async def test_affiliate_redeem_side_effect_failures_do_not_break_success_response(
    monkeypatch,
):
    monkeypatch.setattr(
        affiliate_redeem_service,
        "invalidate_invitation_recharge_cache",
        AsyncMock(side_effect=RuntimeError("cache unavailable")),
    )

    fixture = await _create_redeem_fixture(_unique_suffix(), Decimal("2.0000"))

    try:
        result = await _run_redeem(
            user_id=fixture["user_id"],
            amount_usdt=Decimal("1.0000"),
            idempotency_key="side-effects-fail",
        )

        assert result.status == "SUCCESS"
        assert result.credits_granted == 130
        assert result.current_credits == 130

        state = await _load_user_redeem_state(fixture["user_id"])
        assert state == {"credits": 130, "redeem_count": 1, "out_count": 1}
    finally:
        await _cleanup_redeem_fixture(user_id=fixture["user_id"])


async def test_affiliate_redeem_api_succeeds_with_real_auth_session_chain(monkeypatch):
    invalidate_mock = AsyncMock()
    log_action_mock = AsyncMock()
    monkeypatch.setattr(
        affiliate_redeem_service,
        "invalidate_invitation_recharge_cache",
        invalidate_mock,
    )
    monkeypatch.setattr("src.services.log_service.LogService.log_action", log_action_mock)
    monkeypatch.setattr(
        "src.services.permission_service.permission_service.get_user_detailed_stats",
        AsyncMock(return_value={"identity": "内门弟子", "group": "练气期"}),
    )
    monkeypatch.setattr(
        "src.web_api.services.user_affiliate_redeem_api_service.invalidate_affiliate_redeem_cache_after_commit",
        invalidate_mock,
    )
    monkeypatch.setattr(
        "src.services.redis_client.redis_client",
        SimpleNamespace(
            redis=SimpleNamespace(
                get=AsyncMock(return_value=None),
                delete=AsyncMock(return_value=1),
            )
        ),
    )

    fixture = await _create_redeem_fixture(_unique_suffix(), Decimal("2.0000"))
    token = create_access_token(str(fixture["user_id"]))

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.post(
                "/api/users/me/affiliate/redeem-credits",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "amount_usdt": "1.0000",
                    "idempotency_key": f"api-idem-{_unique_suffix()}",
                },
            )

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["status"] == "SUCCESS"
        assert data["credits_granted"] == 130
        assert data["current_credits"] == 130
        assert data["available_balance_usdt"] == 1.0

        state = await _load_user_redeem_state(fixture["user_id"])
        assert state == {"credits": 130, "redeem_count": 1, "out_count": 1}
        invalidate_mock.assert_awaited_once_with(fixture["user_id"])
        log_action_mock.assert_awaited_once()
    finally:
        await _cleanup_redeem_fixture(user_id=fixture["user_id"])


async def test_affiliate_membership_redeem_succeeds_and_updates_identity(monkeypatch):
    invalidate_mock = AsyncMock()
    log_action_mock = AsyncMock()
    monkeypatch.setattr(
        affiliate_redeem_service,
        "invalidate_invitation_recharge_cache",
        invalidate_mock,
    )
    monkeypatch.setattr("src.services.log_service.LogService.log_action", log_action_mock)

    fixture = await _create_redeem_fixture(_unique_suffix(), Decimal("100.0000"))

    try:
        result = await _run_membership_redeem(
            user_id=fixture["user_id"],
            option_key="inner_30d",
            idempotency_key="membership-success",
        )

        assert result.status == "SUCCESS"
        assert result.redeem_type == "MEMBERSHIP"
        assert result.target_identity == "内门弟子"
        assert result.current_identity == "内门弟子"
        assert result.amount_usdt == Decimal("4.4118")
        assert result.available_balance_usdt == Decimal("95.5882")

        state = await _load_membership_redeem_state(fixture["user_id"])
        assert state == {
            "credits": 400,
            "identity": "内门弟子",
            "available_balance_usdt": Decimal("95.5882"),
            "redeem_count": 1,
            "out_count": 1,
        }
        invalidate_mock.assert_awaited_once_with(fixture["user_id"])
        log_action_mock.assert_awaited_once()
    finally:
        await _cleanup_redeem_fixture(user_id=fixture["user_id"])


async def test_affiliate_membership_redeem_same_idempotency_returns_first_snapshot(
    monkeypatch,
):
    monkeypatch.setattr(
        affiliate_redeem_service,
        "invalidate_invitation_recharge_cache",
        AsyncMock(),
    )
    monkeypatch.setattr("src.services.log_service.LogService.log_action", AsyncMock())

    fixture = await _create_redeem_fixture(_unique_suffix(), Decimal("100.0000"))

    try:
        first = await _run_membership_redeem(
            user_id=fixture["user_id"],
            option_key="core_30d",
            idempotency_key="membership-idem",
        )

        async with DBSessionLocal() as session:
            user = await session.get(User, fixture["user_id"])
            user.current_identity = "真传弟子"
            await session.commit()

        replay = await _run_membership_redeem(
            user_id=fixture["user_id"],
            option_key="core_30d",
            idempotency_key="membership-idem",
        )

        assert replay.redeem_id == first.redeem_id
        assert replay.current_identity == first.current_identity == "核心弟子"
        assert replay.available_balance_usdt == first.available_balance_usdt == Decimal(
            "89.7059"
        )
    finally:
        await _cleanup_redeem_fixture(user_id=fixture["user_id"])


async def test_affiliate_membership_redeem_same_idempotency_different_option_conflicts(
    monkeypatch,
):
    monkeypatch.setattr(
        affiliate_redeem_service,
        "invalidate_invitation_recharge_cache",
        AsyncMock(),
    )
    monkeypatch.setattr("src.services.log_service.LogService.log_action", AsyncMock())

    fixture = await _create_redeem_fixture(_unique_suffix(), Decimal("100.0000"))

    try:
        first = await _run_membership_redeem(
            user_id=fixture["user_id"],
            option_key="inner_30d",
            idempotency_key="membership-conflict",
        )
        assert first.target_identity == "内门弟子"

        with pytest.raises(affiliate_redeem_service.AffiliateRedeemConflictError):
            await _run_membership_redeem(
                user_id=fixture["user_id"],
                option_key="true_30d",
                idempotency_key="membership-conflict",
            )
    finally:
        await _cleanup_redeem_fixture(user_id=fixture["user_id"])


async def test_affiliate_membership_redeem_rolls_back_when_settlement_fails(
    monkeypatch,
):
    monkeypatch.setattr(
        affiliate_redeem_service,
        "invalidate_invitation_recharge_cache",
        AsyncMock(),
    )
    monkeypatch.setattr("src.services.log_service.LogService.log_action", AsyncMock())
    monkeypatch.setattr(
        affiliate_redeem_service,
        "apply_membership_settlement_in_session",
        AsyncMock(side_effect=RuntimeError("settlement failed")),
    )

    fixture = await _create_redeem_fixture(_unique_suffix(), Decimal("100.0000"))

    try:
        with pytest.raises(RuntimeError, match="settlement failed"):
            await _run_membership_redeem(
                user_id=fixture["user_id"],
                option_key="inner_30d",
                idempotency_key="membership-rollback",
            )

        state = await _load_membership_redeem_state(fixture["user_id"])
        assert state == {
            "credits": 0,
            "identity": "外门弟子",
            "available_balance_usdt": Decimal("100.0000"),
            "redeem_count": 0,
            "out_count": 0,
        }
    finally:
        await _cleanup_redeem_fixture(user_id=fixture["user_id"])


async def test_affiliate_membership_redeem_api_succeeds_with_feature_flags(
    monkeypatch,
):
    invalidate_mock = AsyncMock()
    log_action_mock = AsyncMock()
    monkeypatch.setenv("MEMBERSHIP_SETTLEMENT_V2_ENABLED", "true")
    monkeypatch.setenv("AFFILIATE_MEMBERSHIP_REDEEM_ENABLED", "true")
    monkeypatch.setattr(
        affiliate_redeem_service,
        "invalidate_invitation_recharge_cache",
        invalidate_mock,
    )
    monkeypatch.setattr("src.services.log_service.LogService.log_action", log_action_mock)
    monkeypatch.setattr(
        "src.services.permission_service.permission_service.get_user_detailed_stats",
        AsyncMock(return_value={"identity": "内门弟子", "group": "练气期"}),
    )
    monkeypatch.setattr(
        "src.web_api.services.user_affiliate_redeem_api_service.invalidate_affiliate_redeem_cache_after_commit",
        invalidate_mock,
    )
    monkeypatch.setattr(
        "src.services.redis_client.redis_client",
        SimpleNamespace(
            redis=SimpleNamespace(
                get=AsyncMock(return_value=None),
                delete=AsyncMock(return_value=1),
            )
        ),
    )

    fixture = await _create_redeem_fixture(_unique_suffix(), Decimal("100.0000"))
    token = create_access_token(str(fixture["user_id"]))

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.post(
                "/api/users/me/affiliate/redeem-membership",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "option_key": "inner_30d",
                    "idempotency_key": f"api-membership-{_unique_suffix()}",
                },
            )

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["status"] == "SUCCESS"
        assert data["redeem_type"] == "MEMBERSHIP"
        assert data["target_identity"] == "内门弟子"
        assert data["amount_usdt"] == "4.4118"
        assert data["available_balance_usdt"] == "95.5882"

        state = await _load_membership_redeem_state(fixture["user_id"])
        assert state == {
            "credits": 400,
            "identity": "内门弟子",
            "available_balance_usdt": Decimal("95.5882"),
            "redeem_count": 1,
            "out_count": 1,
        }
        invalidate_mock.assert_awaited_once_with(fixture["user_id"])
        log_action_mock.assert_awaited_once()
    finally:
        await _cleanup_redeem_fixture(user_id=fixture["user_id"])


async def test_affiliate_redeem_concurrent_with_commission_accrual_keeps_balances_consistent(
    monkeypatch,
):
    monkeypatch.setattr(
        affiliate_redeem_service,
        "invalidate_invitation_recharge_cache",
        AsyncMock(),
    )
    monkeypatch.setattr("src.services.log_service.LogService.log_action", AsyncMock())

    fixture = await _create_redeem_fixture(_unique_suffix(), Decimal("1.0000"))
    gate = _TwoPartyGate()

    async def _record_commission(amount_usdt: Decimal) -> bool:
        await gate.wait()
        async with DBSessionLocal() as session:
            proxy = _ProxySession(session, gate)
            async with proxy.begin():
                return (
                    await proxy.execute(
                        insert(AffiliateTransaction)
                        .values(
                            user_id=fixture["user_id"],
                            amount_usdt=amount_usdt,
                            transaction_type="COMMISSION_ACCRUAL",
                            direction="IN",
                            reference_type="TEST_CONCURRENT_ORDER",
                            reference_id=_unique_suffix(),
                            idempotency_key=f"test:affiliate:concurrent:{_unique_suffix()}",
                            status="SUCCESS",
                            details={"source": "concurrent_commission"},
                        )
                        .on_conflict_do_nothing(index_elements=["idempotency_key"])
                        .returning(AffiliateTransaction.id)
                    )
                ).scalar_one_or_none() is not None

    try:
        redeem_result, commission_inserted = await asyncio.gather(
            _run_redeem(
                user_id=fixture["user_id"],
                amount_usdt=Decimal("1.0000"),
                idempotency_key="redeem-vs-commission",
                gate=gate,
            ),
            _record_commission(Decimal("0.5000")),
        )

        assert commission_inserted is True
        assert redeem_result.status == "SUCCESS"
        assert redeem_result.credits_granted == 130

        async with DBSessionLocal() as session:
            balance = await affiliate_redeem_service.query_affiliate_available_balance(
                session, fixture["user_id"]
            )

        state = await _load_user_redeem_state(fixture["user_id"])
        assert state == {"credits": 130, "redeem_count": 1, "out_count": 1}
        assert balance == Decimal("0.5000")
    finally:
        await _cleanup_redeem_fixture(user_id=fixture["user_id"])


async def test_affiliate_redeem_defers_cache_invalidation_when_reusing_external_transaction(
    monkeypatch,
):
    invalidate_mock = AsyncMock()
    monkeypatch.setattr(
        affiliate_redeem_service,
        "invalidate_invitation_recharge_cache",
        invalidate_mock,
    )
    monkeypatch.setattr("src.services.log_service.LogService.log_action", AsyncMock())

    fixture = await _create_redeem_fixture(_unique_suffix(), Decimal("2.0000"))

    try:
        async with DBSessionLocal() as session:
            async with session.begin():
                result = await affiliate_redeem_service.redeem_affiliate_balance_to_credits(
                    session,
                    user_id=fixture["user_id"],
                    amount_usdt=Decimal("1.0000"),
                    idempotency_key="defer-cache-invalidation",
                )
                assert result.status == "SUCCESS"
                invalidate_mock.assert_not_awaited()

            invalidate_mock.assert_not_awaited()

        state = await _load_user_redeem_state(fixture["user_id"])
        assert state == {"credits": 130, "redeem_count": 1, "out_count": 1}
    finally:
        await _cleanup_redeem_fixture(user_id=fixture["user_id"])


async def test_affiliate_redeem_waits_for_commission_commit_on_same_user(monkeypatch):
    monkeypatch.setattr(
        affiliate_redeem_service,
        "invalidate_invitation_recharge_cache",
        AsyncMock(),
    )
    monkeypatch.setattr("src.services.log_service.LogService.log_action", AsyncMock())

    fixture = await _create_redeem_fixture(_unique_suffix(), Decimal("1.0000"))
    locked_event = asyncio.Event()
    release_event = asyncio.Event()

    try:
        commission_task = asyncio.create_task(
            _record_commission_with_user_lock(
                user_id=fixture["user_id"],
                amount_usdt=Decimal("2.0000"),
                locked_event=locked_event,
                release_event=release_event,
            )
        )
        await asyncio.wait_for(locked_event.wait(), timeout=5)

        redeem_task = asyncio.create_task(
            _run_redeem(
                user_id=fixture["user_id"],
                amount_usdt=Decimal("3.0000"),
                idempotency_key="redeem-after-commission-lock",
            )
        )

        await asyncio.sleep(0.2)
        assert redeem_task.done() is False

        release_event.set()
        commission_inserted, redeem_result = await asyncio.gather(
            commission_task, redeem_task
        )

        assert commission_inserted is True
        assert redeem_result.status == "SUCCESS"
        assert redeem_result.credits_granted == 390
        assert redeem_result.available_balance_usdt == Decimal("0.0000")

        state = await _load_user_redeem_state(fixture["user_id"])
        assert state == {"credits": 390, "redeem_count": 1, "out_count": 1}
    finally:
        release_event.set()
        await _cleanup_redeem_fixture(user_id=fixture["user_id"])
