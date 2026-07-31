from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from src.database.models import AffiliateRedeem, AffiliateTransaction, User
from src.services.affiliate_redeem_rules import (
    AFFILIATE_REDEEM_OPTION_USDT_TON,
    AFFILIATE_REDEEM_NETWORK_TON,
    AFFILIATE_REDEEM_PENDING,
    AFFILIATE_REDEEM_REJECTED,
    AFFILIATE_REDEEM_SUCCESS,
    AFFILIATE_REDEEM_TYPE_USDT,
    REDEEM_USDT_QUANT,
    normalize_usdt_payout_address,
    normalize_usdt_redeem_amount,
)


class AffiliateUsdtRedeemError(RuntimeError):
    pass


class AffiliateUsdtRedeemConflictError(AffiliateUsdtRedeemError):
    pass


class AffiliateUsdtRedeemNotFoundError(AffiliateUsdtRedeemError):
    pass


class AffiliateUsdtRedeemInsufficientBalanceError(AffiliateUsdtRedeemError):
    def __init__(self, available: Decimal, requested: Decimal):
        self.available = available
        self.requested = requested
        super().__init__("insufficient affiliate balance")


@dataclass(frozen=True)
class AffiliateBalanceSummary:
    total_usdt: Decimal
    spent_usdt: Decimal
    frozen_usdt: Decimal
    available_usdt: Decimal


@dataclass(frozen=True)
class AffiliateUsdtRedeemResult:
    redeem_id: int
    user_id: int
    amount_usdt: Decimal
    payout_network: str
    payout_address: str
    payout_tx_hash: str | None
    status: str
    idempotency_key: str
    created_at: datetime | None
    processed_at: datetime | None
    rejection_reason: str | None
    balance: AffiliateBalanceSummary


async def query_affiliate_balance_summary(
    session: AsyncSession, user_id: int
) -> AffiliateBalanceSummary:
    stmt = select(
        func.coalesce(
            func.sum(
                case(
                    (
                        and_(
                            AffiliateTransaction.direction == "IN",
                            AffiliateTransaction.status == "SUCCESS",
                        ),
                        AffiliateTransaction.amount_usdt,
                    ),
                    else_=0,
                )
            ),
            0,
        ),
        func.coalesce(
            func.sum(
                case(
                    (
                        and_(
                            AffiliateTransaction.direction == "OUT",
                            AffiliateTransaction.status == "SUCCESS",
                        ),
                        AffiliateTransaction.amount_usdt,
                    ),
                    else_=0,
                )
            ),
            0,
        ),
        func.coalesce(
            func.sum(
                case(
                    (
                        and_(
                            AffiliateTransaction.direction == "OUT",
                            AffiliateTransaction.status == "PENDING",
                            AffiliateTransaction.transaction_type == "USDT_REDEEM",
                        ),
                        AffiliateTransaction.amount_usdt,
                    ),
                    else_=0,
                )
            ),
            0,
        ),
    ).where(AffiliateTransaction.user_id == user_id)
    total, spent, frozen = (await session.execute(stmt)).one()
    total_d = Decimal(str(total or 0)).quantize(REDEEM_USDT_QUANT)
    spent_d = Decimal(str(spent or 0)).quantize(REDEEM_USDT_QUANT)
    frozen_d = Decimal(str(frozen or 0)).quantize(REDEEM_USDT_QUANT)
    return AffiliateBalanceSummary(
        total_usdt=total_d,
        spent_usdt=spent_d,
        frozen_usdt=frozen_d,
        available_usdt=(total_d - spent_d - frozen_d).quantize(REDEEM_USDT_QUANT),
    )


def _to_result(
    redeem: AffiliateRedeem, balance: AffiliateBalanceSummary
) -> AffiliateUsdtRedeemResult:
    return AffiliateUsdtRedeemResult(
        redeem_id=int(redeem.id),
        user_id=int(redeem.user_id),
        amount_usdt=Decimal(str(redeem.amount_usdt)).quantize(REDEEM_USDT_QUANT),
        payout_network=str(redeem.payout_network or AFFILIATE_REDEEM_NETWORK_TON),
        payout_address=str(redeem.payout_address or ""),
        payout_tx_hash=redeem.payout_tx_hash,
        status=redeem.status,
        idempotency_key=redeem.idempotency_key,
        created_at=redeem.created_at,
        processed_at=redeem.processed_at,
        rejection_reason=redeem.rejection_reason,
        balance=balance,
    )


async def _run_transaction(session: AsyncSession, runner):
    if session.in_transaction():
        return await runner()
    async with session.begin():
        return await runner()


async def create_affiliate_usdt_redeem(
    session: AsyncSession,
    *,
    user_id: int,
    amount_usdt: Decimal,
    payout_address: str,
    idempotency_key: str,
) -> AffiliateUsdtRedeemResult:
    amount = normalize_usdt_redeem_amount(amount_usdt)
    address = normalize_usdt_payout_address(payout_address)

    async def _create():
        user = (
            await session.execute(
                select(User).where(User.id == user_id).with_for_update()
            )
        ).scalar_one_or_none()
        if user is None:
            raise ValueError("user not found")
        existing = (
            await session.execute(
                select(AffiliateRedeem)
                .where(
                    AffiliateRedeem.user_id == user_id,
                    AffiliateRedeem.idempotency_key == idempotency_key,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if existing is not None:
            matches = (
                existing.redeem_type == AFFILIATE_REDEEM_TYPE_USDT
                and Decimal(str(existing.amount_usdt)).quantize(REDEEM_USDT_QUANT)
                == amount
                and existing.payout_address == address
            )
            if not matches:
                raise AffiliateUsdtRedeemConflictError(
                    "idempotency key already used with different parameters"
                )
            return _to_result(
                existing, await query_affiliate_balance_summary(session, user_id)
            )
        pending = (
            await session.execute(
                select(AffiliateRedeem.id).where(
                    AffiliateRedeem.user_id == user_id,
                    AffiliateRedeem.redeem_type == AFFILIATE_REDEEM_TYPE_USDT,
                    AffiliateRedeem.status == AFFILIATE_REDEEM_PENDING,
                )
            )
        ).scalar_one_or_none()
        if pending is not None:
            raise AffiliateUsdtRedeemConflictError(
                "user already has a pending USDT redeem"
            )
        balance = await query_affiliate_balance_summary(session, user_id)
        if balance.available_usdt < amount:
            raise AffiliateUsdtRedeemInsufficientBalanceError(
                balance.available_usdt, amount
            )
        redeem = AffiliateRedeem(
            user_id=user_id,
            redeem_type=AFFILIATE_REDEEM_TYPE_USDT,
            redeem_option_key=AFFILIATE_REDEEM_OPTION_USDT_TON,
            requested_amount_usdt=amount,
            amount_usdt=amount,
            credits_granted=0,
            status=AFFILIATE_REDEEM_PENDING,
            idempotency_key=idempotency_key,
            payout_network=AFFILIATE_REDEEM_NETWORK_TON,
            payout_address=address,
            details={"schema_version": "affiliate_usdt_redeem_v1"},
        )
        session.add(redeem)
        await session.flush()
        session.add(
            AffiliateTransaction(
                user_id=user_id,
                amount_usdt=amount,
                transaction_type="USDT_REDEEM",
                direction="OUT",
                reference_type="AFFILIATE_REDEEM",
                reference_id=str(redeem.id),
                idempotency_key=f"affiliate:redeem:usdt:{redeem.id}",
                status=AFFILIATE_REDEEM_PENDING,
                details={
                    "redeem_id": redeem.id,
                    "network": AFFILIATE_REDEEM_OPTION_USDT_TON,
                },
            )
        )
        try:
            await session.flush()
        except IntegrityError as exc:
            raise AffiliateUsdtRedeemConflictError(
                "duplicate pending USDT redeem"
            ) from exc
        return _to_result(
            redeem, await query_affiliate_balance_summary(session, user_id)
        )

    return await _run_transaction(session, _create)


async def _load_redeem_for_update(
    session: AsyncSession, redeem_id: int
) -> AffiliateRedeem:
    redeem = (
        await session.execute(
            select(AffiliateRedeem)
            .where(
                AffiliateRedeem.id == redeem_id,
                AffiliateRedeem.redeem_type == AFFILIATE_REDEEM_TYPE_USDT,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if redeem is None:
        raise AffiliateUsdtRedeemNotFoundError("USDT redeem not found")
    return redeem


async def complete_affiliate_usdt_redeem(
    session: AsyncSession,
    *,
    redeem_id: int,
    payout_tx_hash: str,
    processed_by: str,
    admin_note: str | None = None,
) -> AffiliateUsdtRedeemResult:
    tx_hash = str(payout_tx_hash or "").strip()
    if not tx_hash:
        raise ValueError("payout transaction hash is required")

    async def _complete():
        redeem = await _load_redeem_for_update(session, redeem_id)
        if redeem.status == AFFILIATE_REDEEM_SUCCESS:
            if redeem.payout_tx_hash != tx_hash:
                raise AffiliateUsdtRedeemConflictError(
                    "redeem already completed with a different transaction hash"
                )
            return _to_result(
                redeem,
                await query_affiliate_balance_summary(session, int(redeem.user_id)),
            )
        if redeem.status != AFFILIATE_REDEEM_PENDING:
            raise AffiliateUsdtRedeemConflictError(
                "rejected redeem cannot be completed"
            )
        ledger = (
            await session.execute(
                select(AffiliateTransaction)
                .where(
                    AffiliateTransaction.reference_type == "AFFILIATE_REDEEM",
                    AffiliateTransaction.reference_id == str(redeem.id),
                    AffiliateTransaction.transaction_type == "USDT_REDEEM",
                )
                .with_for_update()
            )
        ).scalar_one()
        redeem.status = AFFILIATE_REDEEM_SUCCESS
        redeem.payout_tx_hash = tx_hash
        redeem.admin_note = str(admin_note or "").strip() or None
        redeem.processed_by = processed_by
        redeem.processed_at = datetime.now()
        ledger.status = AFFILIATE_REDEEM_SUCCESS
        try:
            await session.flush()
        except IntegrityError as exc:
            raise AffiliateUsdtRedeemConflictError(
                "payout transaction hash already used"
            ) from exc
        return _to_result(
            redeem,
            await query_affiliate_balance_summary(session, int(redeem.user_id)),
        )

    return await _run_transaction(session, _complete)


async def reject_affiliate_usdt_redeem(
    session: AsyncSession,
    *,
    redeem_id: int,
    reason: str,
    processed_by: str,
) -> AffiliateUsdtRedeemResult:
    rejection_reason = str(reason or "").strip()
    if not rejection_reason:
        raise ValueError("rejection reason is required")

    async def _reject():
        redeem = await _load_redeem_for_update(session, redeem_id)
        if redeem.status == AFFILIATE_REDEEM_REJECTED:
            if redeem.rejection_reason != rejection_reason:
                raise AffiliateUsdtRedeemConflictError(
                    "redeem already rejected with a different reason"
                )
            return _to_result(
                redeem,
                await query_affiliate_balance_summary(session, int(redeem.user_id)),
            )
        if redeem.status != AFFILIATE_REDEEM_PENDING:
            raise AffiliateUsdtRedeemConflictError(
                "completed redeem cannot be rejected"
            )
        ledger = (
            await session.execute(
                select(AffiliateTransaction)
                .where(
                    AffiliateTransaction.reference_type == "AFFILIATE_REDEEM",
                    AffiliateTransaction.reference_id == str(redeem.id),
                    AffiliateTransaction.transaction_type == "USDT_REDEEM",
                )
                .with_for_update()
            )
        ).scalar_one()
        redeem.status = AFFILIATE_REDEEM_REJECTED
        redeem.rejection_reason = rejection_reason
        redeem.processed_by = processed_by
        redeem.processed_at = datetime.now()
        ledger.status = AFFILIATE_REDEEM_REJECTED
        await session.flush()
        return _to_result(
            redeem,
            await query_affiliate_balance_summary(session, int(redeem.user_id)),
        )

    return await _run_transaction(session, _reject)


async def list_user_affiliate_usdt_redeems(
    session: AsyncSession,
    *,
    user_id: int,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    filters = (
        AffiliateRedeem.user_id == user_id,
        AffiliateRedeem.redeem_type == AFFILIATE_REDEEM_TYPE_USDT,
    )
    total = (
        await session.execute(
            select(func.count(AffiliateRedeem.id)).where(*filters)
        )
    ).scalar_one()
    records = (
        await session.execute(
            select(AffiliateRedeem)
            .where(*filters)
            .order_by(AffiliateRedeem.created_at.desc(), AffiliateRedeem.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    balance = await query_affiliate_balance_summary(session, user_id)
    return {
        "items": [_to_result(record, balance) for record in records],
        "total": int(total),
        "page": page,
        "page_size": page_size,
        "balance": balance,
    }
