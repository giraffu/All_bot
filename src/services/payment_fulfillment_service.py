import logging
import os
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

import aiohttp
from sqlalchemy import select

from src.database.core import AsyncSessionLocal
from src.database.models import MembershipPlan, User
from src.core.affiliate_core import (
    calculate_and_set_commission_for_paid_order,
    invalidate_invitation_recharge_cache,
    record_affiliate_commission_transaction,
)
from src.services.affiliate_redeem_service import is_membership_settlement_v2_enabled
from src.services.membership_settlement_service import (
    MembershipSettlementAuditSource,
    settle_membership_plan_in_session,
)
from src.services.order_v2_service import build_order_public_lookup_stmt
from config import TELEGRAM_API_BASE_URL

logger = logging.getLogger("payment_fulfillment")
RMB_AMOUNT_QUANT = Decimal("0.01")


def _normalize_rmb_amount(amount: Decimal | str | int) -> Decimal:
    return Decimal(str(amount)).quantize(RMB_AMOUNT_QUANT, rounding=ROUND_HALF_UP)


async def _load_rmb_order(session, out_trade_no: str):
    order_res = await session.execute(
        build_order_public_lookup_stmt(out_trade_no, for_update=True)
    )
    return order_res.scalar_one_or_none()


async def _load_membership_plan(session, plan_id: int):
    plan_res = await session.execute(
        select(MembershipPlan).where(MembershipPlan.id == plan_id)
    )
    return plan_res.scalar_one_or_none()


async def _load_locked_user(session, internal_user_id: int):
    user_res = await session.execute(
        select(User).where(User.id == internal_user_id).with_for_update()
    )
    return user_res.scalar_one_or_none()


def _mark_order_paid(order, *, external_trade_no: str, paid_at: datetime) -> None:
    order.payment_channel = "RMB"
    order.status = "SUCCESS"
    order.tx_hash = external_trade_no
    order.paid_at = paid_at


async def _record_order_affiliate_ledger(session, order):
    referral = await calculate_and_set_commission_for_paid_order(session, order)
    if not referral or Decimal(str(order.commission_usdt or 0)) <= 0:
        return referral

    inserted = await record_affiliate_commission_transaction(
        session,
        order,
        referral,
        source="rmb_payment_callback",
    )
    if not inserted:
        logger.warning(
            "affiliate ledger insert skipped for RMB order_id=%s order_pk=%s tx_hash=%s",
            order.order_id,
            order.id,
            order.tx_hash,
        )
    return referral


async def _settle_rmb_order_membership(
    *,
    session,
    user,
    plan,
    order,
    external_trade_no: str,
    now: datetime,
) -> dict:
    if is_membership_settlement_v2_enabled():
        return await settle_membership_plan_in_session(
            locked_user=user,
            plan=plan,
            audit_source=MembershipSettlementAuditSource(
                source="rmb_payment_callback",
                source_channel="RMB",
                source_order_id=order.order_id,
                source_tx_hash=external_trade_no,
            ),
            session=session,
            now=now,
            grant_reward_credits=True,
        )

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
    return {
        "credits_granted": int(plan.reward_credits or 0),
        "converted_days": 0,
        "final_identity": final_identity,
        "final_expire_at": new_expire_at.isoformat() if new_expire_at else None,
        "current_credits": int(user.credits or 0),
        "settlement_reason": "LEGACY_FALLBACK",
        "is_pure_credit_plan": int(plan.duration_days or 0) == 0,
        "kept_current_identity": final_identity == user.current_identity,
        "is_downgrade": False,
    }


def _build_rmb_payment_success_message(*, plan, user, applied_snapshot: dict) -> str:
    credits_granted = int(applied_snapshot.get("credits_granted", 0))
    converted_days = int(applied_snapshot.get("converted_days", 0))
    final_identity = str(applied_snapshot.get("final_identity", user.current_identity))
    final_expire_at = applied_snapshot.get("final_expire_at")
    is_pure_credit = bool(applied_snapshot.get("is_pure_credit_plan", False))
    is_downgrade = bool(applied_snapshot.get("is_downgrade", False))
    success_msg = (
        f"🎉 <b>支付成功！</b>\n\n"
        f"感谢您的赞助，您已成功购买 <b>{plan.name}</b>。\n"
        f"💎 <b>获得永久灵石</b>：<code>{credits_granted}</code>\n"
    )
    if is_pure_credit or is_downgrade:
        success_msg += f"👑 <b>当前身份保持为</b>：<code>{final_identity}</code>\n"
        if converted_days > 0:
            success_msg += (
                f"⚖️ <b>新套餐价值已折算</b>：<code>{converted_days}</code> "
                "天当前高级身份时长\n"
            )
    else:
        success_msg += f"👑 <b>当前身份晋升为</b>：<code>{final_identity}</code>\n"
        if converted_days > 0:
            success_msg += (
                f"⚖️ <b>老套餐残值已折算</b>：<code>{converted_days}</code> 天新套餐时长\n"
            )

    if final_expire_at:
        success_msg += f"⏳ <b>身份到期时间</b>：<code>{final_expire_at}</code>\n\n"
    return success_msg + "祝您仙途坦荡，早日登峰造极！"


async def _notify_rmb_payment_success(*, user, plan, applied_snapshot: dict) -> None:
    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        return

    telegram_api_url = f"{TELEGRAM_API_BASE_URL}/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": user.telegram_id or user.id,
        "text": _build_rmb_payment_success_message(
            plan=plan,
            user=user,
            applied_snapshot=applied_snapshot,
        ),
        "parse_mode": "HTML",
    }
    try:
        async with aiohttp.ClientSession() as http_session:
            async with http_session.post(
                telegram_api_url,
                json=payload,
                timeout=10,
            ) as resp:
                if resp.status != 200:
                    response_text = await resp.text()
                    logger.error(
                        "Failed to send TG message, status: %s, response: %s",
                        resp.status,
                        response_text,
                    )
    except Exception as e:
        logger.error(f"Exception while sending TG message: {e}")


async def fulfill_order(
    out_trade_no: str, external_trade_no: str, paid_amount: Decimal | str | int
) -> bool:
    """
    统一发货逻辑，目前供 RMB 支付网关回调使用。
    """
    async with AsyncSessionLocal() as session:
        try:
            order = await _load_rmb_order(session, out_trade_no)
            if not order:
                logger.error(f"Order not found: {out_trade_no}")
                return False

            if order.status == "SUCCESS":
                logger.info(
                    f"Order {out_trade_no} is already SUCCESS. Idempotent return."
                )
                return True  # 幂等返回

            if _normalize_rmb_amount(order.final_price) != _normalize_rmb_amount(
                paid_amount
            ):
                logger.error(
                    f"Amount mismatch for {out_trade_no}: paid {paid_amount}, expected {order.final_price}"
                )
                return False

            plan = await _load_membership_plan(session, order.plan_id)
            if not plan:
                logger.error(f"Plan not found: {order.plan_id}")
                return False

            user = await _load_locked_user(session, order.internal_user_id)
            if not user:
                logger.error(f"User not found: {order.internal_user_id}")
                return False

            now = datetime.now()
            _mark_order_paid(order, external_trade_no=external_trade_no, paid_at=now)
            await session.flush()
            referral = await _record_order_affiliate_ledger(session, order)
            applied_snapshot = await _settle_rmb_order_membership(
                session=session,
                user=user,
                plan=plan,
                order=order,
                external_trade_no=external_trade_no,
                now=now,
            )

            await session.commit()
            if referral:
                await invalidate_invitation_recharge_cache(referral.inviter_id)

            logger.info(f"Order {out_trade_no} fulfilled for user {user.id}")
            await _notify_rmb_payment_success(
                user=user,
                plan=plan,
                applied_snapshot=applied_snapshot,
            )

            return True

        except Exception as e:
            await session.rollback()
            logger.error(f"Failed to fulfill order {out_trade_no}: {e}")
            return False
