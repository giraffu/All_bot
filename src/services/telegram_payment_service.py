from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert

from src.core.user_core import get_or_create_user_by_telegram
from src.database.core import AsyncSessionLocal
from src.database.models import MembershipPlan, Order, User, UserLog
from src.services.affiliate_redeem_service import is_membership_settlement_v2_enabled
from src.services.membership_settlement_service import (
    MembershipSettlementAuditSource,
    settle_membership_plan_in_session,
)
from src.services.order_v2_service import build_order_public_lookup_stmt, parse_order_payload

logger = logging.getLogger("bot.payment")


@dataclass(frozen=True)
class TelegramStarsPaymentResult:
    status: Literal["success", "amount_mismatch", "noop"]
    user_id: int | None = None
    plan_name: str | None = None
    credits_granted: int = 0
    converted_days: int = 0
    final_identity: str | None = None
    final_expire_at: str | None = None
    is_pure_credit_plan: bool = False
    is_downgrade: bool = False


async def validate_stars_precheckout(
    *,
    payload: str,
    telegram_user_id: int,
    total_amount: int,
) -> bool:
    parsed_payload = parse_order_payload(payload)
    if parsed_payload.kind == "legacy":
        return True
    if parsed_payload.kind != "v2" or not parsed_payload.business_order_id:
        return False

    internal_user, _ = await get_or_create_user_by_telegram(telegram_user_id)
    async with AsyncSessionLocal() as session:
        order = (
            await session.execute(
                build_order_public_lookup_stmt(parsed_payload.business_order_id)
            )
        ).scalar_one_or_none()
        if (
            not order
            or order.internal_user_id != internal_user.id
            or order.status != "PENDING"
        ):
            return False

        plan = (
            await session.execute(
                select(MembershipPlan).where(MembershipPlan.id == order.plan_id)
            )
        ).scalar_one_or_none()
        return bool(plan and int(getattr(plan, "price_stars", 0)) == int(total_amount))


async def process_successful_stars_payment(
    *,
    payload: str,
    total_amount: int,
    telegram_payment_charge_id: str,
) -> TelegramStarsPaymentResult | None:
    parsed_payload = parse_order_payload(payload)
    if parsed_payload.kind == "unknown":
        return None

    async with AsyncSessionLocal() as session:
        user_id: int | None = None
        try:
            now = datetime.now()
            tx_hash_truncated = telegram_payment_charge_id[:100]

            if parsed_payload.kind == "v2" and parsed_payload.business_order_id:
                new_order = (
                    await session.execute(
                        build_order_public_lookup_stmt(
                            parsed_payload.business_order_id, for_update=True
                        )
                    )
                ).scalar_one_or_none()
                if not new_order:
                    logger.error(
                        "Order not found for business_order_id=%s",
                        parsed_payload.business_order_id,
                    )
                    return TelegramStarsPaymentResult(status="noop")
                if new_order.status == "SUCCESS":
                    logger.info(
                        "Stars order already SUCCESS for business_order_id=%s",
                        parsed_payload.business_order_id,
                    )
                    return TelegramStarsPaymentResult(status="noop")

                user = (
                    await session.execute(
                        select(User)
                        .where(User.id == new_order.internal_user_id)
                        .with_for_update()
                    )
                ).scalar_one_or_none()
                user_id = new_order.internal_user_id
                if not user:
                    logger.error(
                        "User %s not found during stars v2 payment",
                        new_order.internal_user_id,
                    )
                    return TelegramStarsPaymentResult(status="noop")

                plan = (
                    await session.execute(
                        select(MembershipPlan).where(MembershipPlan.id == new_order.plan_id)
                    )
                ).scalar_one_or_none()
                if not plan:
                    logger.error("Unknown plan_id: %s", new_order.plan_id)
                    return TelegramStarsPaymentResult(status="noop")
                if total_amount != getattr(plan, "price_stars", 0):
                    logger.error(
                        "Amount mismatch for business_order_id=%s: paid %s, expected %s",
                        parsed_payload.business_order_id,
                        total_amount,
                        getattr(plan, "price_stars", 0),
                    )
                    return TelegramStarsPaymentResult(status="amount_mismatch")

                new_order.status = "SUCCESS"
                new_order.tx_hash = tx_hash_truncated
                new_order.paid_at = now
                await session.flush()
            else:
                try:
                    user_id = int(parsed_payload.telegram_user_id)
                    plan_id = int(parsed_payload.plan_id)
                except (TypeError, ValueError):
                    logger.error("Invalid payload format: %s", payload)
                    return TelegramStarsPaymentResult(status="noop")

                plan = (
                    await session.execute(
                        select(MembershipPlan).where(MembershipPlan.id == plan_id)
                    )
                ).scalar_one_or_none()
                if not plan:
                    logger.error("Unknown plan_id: %s", plan_id)
                    return TelegramStarsPaymentResult(status="noop")
                if total_amount != getattr(plan, "price_stars", 0):
                    logger.error(
                        "Amount mismatch for plan %s: paid %s, expected %s",
                        plan_id,
                        total_amount,
                        getattr(plan, "price_stars", 0),
                    )
                    return TelegramStarsPaymentResult(status="amount_mismatch")

                user = (
                    await session.execute(
                        select(User)
                        .where(or_(User.telegram_id == user_id, User.id == user_id))
                        .with_for_update()
                    )
                ).scalar_one_or_none()
                if not user:
                    logger.error("User %s not found during payment", user_id)
                    return TelegramStarsPaymentResult(status="noop")

                inserted_order_id = (
                    await session.execute(
                        insert(Order)
                        .values(
                            order_id=payload[:64],
                            internal_user_id=user.id,
                            plan_id=plan_id,
                            original_price=total_amount,
                            final_price=total_amount,
                            status="SUCCESS",
                            tx_hash=tx_hash_truncated,
                            payment_channel="XTR",
                            paid_at=now,
                        )
                        .on_conflict_do_nothing(index_elements=["tx_hash"])
                        .returning(Order.id)
                    )
                ).scalar_one_or_none()
                if inserted_order_id is None:
                    logger.warning(
                        "Order already processed for charge_id: %s",
                        telegram_payment_charge_id,
                    )
                    return TelegramStarsPaymentResult(status="noop")

                new_order = await session.get(Order, inserted_order_id)
                if new_order is None:
                    raise RuntimeError(
                        "failed to reload inserted Stars order for charge_id: "
                        f"{telegram_payment_charge_id}"
                    )
                await session.flush()
                if new_order.tx_hash != tx_hash_truncated:
                    raise RuntimeError(
                        "inserted Stars order tx_hash mismatch for charge_id: "
                        f"{telegram_payment_charge_id}"
                    )

            from src.core.affiliate_core import (
                calculate_and_set_commission_for_paid_order,
                invalidate_invitation_recharge_cache,
                record_affiliate_commission_transaction,
            )

            referral = await calculate_and_set_commission_for_paid_order(
                session, new_order
            )
            if referral and Decimal(str(new_order.commission_usdt or 0)) > 0:
                inserted = await record_affiliate_commission_transaction(
                    session,
                    new_order,
                    referral,
                    source="telegram_stars_payment",
                )
                if not inserted:
                    logger.warning(
                        "affiliate ledger insert skipped for Stars order_id=%s order_pk=%s tx_hash=%s",
                        new_order.order_id,
                        new_order.id,
                        new_order.tx_hash,
                    )

            if is_membership_settlement_v2_enabled():
                applied_snapshot = await settle_membership_plan_in_session(
                    locked_user=user,
                    plan=plan,
                    audit_source=MembershipSettlementAuditSource(
                        source="telegram_stars_payment",
                        source_channel="XTR",
                        source_order_id=str(new_order.order_id),
                        source_tx_hash=tx_hash_truncated,
                    ),
                    session=session,
                    now=now,
                    grant_reward_credits=True,
                )
            else:
                from src.core.billing_core import calculate_identity_conversion

                final_identity, new_expire_at = calculate_identity_conversion(
                    current_identity=user.current_identity,
                    current_expire_at=user.identity_expire_at,
                    new_identity=plan.identity_name,
                    duration_days=plan.duration_days,
                )
                user.credits += plan.reward_credits
                user.current_identity = final_identity
                user.identity_expire_at = new_expire_at
                applied_snapshot = {
                    "credits_granted": int(plan.reward_credits or 0),
                    "converted_days": 0,
                    "final_identity": final_identity,
                    "final_expire_at": new_expire_at.isoformat()
                    if new_expire_at
                    else None,
                    "is_pure_credit_plan": int(plan.duration_days or 0) == 0,
                    "is_downgrade": False,
                }
                log = UserLog(
                    user_id=user.id,
                    username=user.username,
                    operation_type="recharge",
                    credit_change=int(plan.reward_credits or 0),
                    current_balance=user.credits,
                    extra_info=json.dumps(
                        {
                            "reason": f"Telegram Stars 购买: {plan.name}",
                            "via": "telegram_stars",
                            "plan_id": plan.id,
                        },
                        ensure_ascii=False,
                    ),
                )
                session.add(log)

            await session.commit()
            if referral:
                await invalidate_invitation_recharge_cache(referral.inviter_id)

            logger.info(
                "Payment success processed for user %s, plan: %s",
                user_id,
                plan.name,
            )
            return TelegramStarsPaymentResult(
                status="success",
                user_id=user_id,
                plan_name=str(plan.name),
                credits_granted=int(applied_snapshot.get("credits_granted", 0)),
                converted_days=int(applied_snapshot.get("converted_days", 0)),
                final_identity=str(
                    applied_snapshot.get("final_identity", user.current_identity)
                ),
                final_expire_at=applied_snapshot.get("final_expire_at"),
                is_pure_credit_plan=bool(
                    applied_snapshot.get("is_pure_credit_plan", False)
                ),
                is_downgrade=bool(applied_snapshot.get("is_downgrade", False)),
            )
        except Exception:
            await session.rollback()
            logger.exception("Error processing payment for user %s", user_id)
            raise
