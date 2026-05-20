import logging
import os
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

import aiohttp
from sqlalchemy import select

from src.database.core import AsyncSessionLocal
from src.database.models import MembershipPlan, Order, User
from src.core.affiliate_core import (
    calculate_and_set_commission_for_paid_order,
    invalidate_invitation_recharge_cache,
    record_affiliate_commission_transaction,
)
from src.services.log_service import LogService  # Backward-compatible test patch target.
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


async def fulfill_order(
    out_trade_no: str, external_trade_no: str, paid_amount: Decimal | str | int
) -> bool:
    """
    统一发货逻辑，目前供 RMB 支付网关回调使用。
    """
    async with AsyncSessionLocal() as session:
        try:
            # 1. 查找订单
            order_res = await session.execute(
                build_order_public_lookup_stmt(out_trade_no, for_update=True)
            )
            order = order_res.scalar_one_or_none()
            if not order:
                logger.error(f"Order not found: {out_trade_no}")
                return False

            if order.status == "SUCCESS":
                logger.info(
                    f"Order {out_trade_no} is already SUCCESS. Idempotent return."
                )
                return True  # 幂等返回

            # 金额校验
            if _normalize_rmb_amount(order.final_price) != _normalize_rmb_amount(
                paid_amount
            ):
                logger.error(
                    f"Amount mismatch for {out_trade_no}: paid {paid_amount}, expected {order.final_price}"
                )
                return False

            # 2. 查找套餐
            plan_res = await session.execute(
                select(MembershipPlan).where(MembershipPlan.id == order.plan_id)
            )
            plan = plan_res.scalar_one_or_none()
            if not plan:
                logger.error(f"Plan not found: {order.plan_id}")
                return False

            # 3. 查找用户
            user_res = await session.execute(
                select(User).where(User.id == order.telegram_id).with_for_update()
            )
            user = user_res.scalar_one_or_none()
            if not user:
                logger.error(f"User not found: {order.telegram_id}")
                return False

            now = datetime.now()
            order.payment_channel = "RMB"
            order.status = "SUCCESS"
            order.tx_hash = external_trade_no
            order.paid_at = now
            await session.flush()
            referral = await calculate_and_set_commission_for_paid_order(session, order)
            if referral and Decimal(str(order.commission_usdt or 0)) > 0:
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
            if is_membership_settlement_v2_enabled():
                applied_snapshot = await settle_membership_plan_in_session(
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
                    "current_credits": int(user.credits or 0),
                    "settlement_reason": "LEGACY_FALLBACK",
                    "is_pure_credit_plan": int(plan.duration_days or 0) == 0,
                    "kept_current_identity": final_identity == user.current_identity,
                    "is_downgrade": False,
                }

            await session.commit()
            if referral:
                await invalidate_invitation_recharge_cache(referral.inviter_id)

            logger.info(f"Order {out_trade_no} fulfilled for user {user.id}")

            # 6. 通知用户
            bot_token = os.getenv("BOT_TOKEN")
            if bot_token:
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
                    success_msg += (
                        f"👑 <b>当前身份保持为</b>：<code>{final_identity}</code>\n"
                    )
                    if converted_days > 0:
                        success_msg += f"⚖️ <b>新套餐价值已折算</b>：<code>{converted_days}</code> 天当前高级身份时长\n"
                else:
                    success_msg += (
                        f"👑 <b>当前身份晋升为</b>：<code>{final_identity}</code>\n"
                    )
                    if converted_days > 0:
                        success_msg += f"⚖️ <b>老套餐残值已折算</b>：<code>{converted_days}</code> 天新套餐时长\n"

                if final_expire_at:
                    success_msg += f"⏳ <b>身份到期时间</b>：<code>{final_expire_at}</code>\n\n"
                success_msg += "祝您仙途坦荡，早日登峰造极！"

                telegram_api_url = f"{TELEGRAM_API_BASE_URL}/bot{bot_token}/sendMessage"
                payload = {
                    "chat_id": user.telegram_id
                    or user.id,  # Fallback to id if telegram_id is empty (for old users)
                    "text": success_msg,
                    "parse_mode": "HTML",
                }
                try:
                    async with aiohttp.ClientSession() as http_session:
                        async with http_session.post(
                            telegram_api_url, json=payload, timeout=10
                        ) as resp:
                            if resp.status != 200:
                                logger.error(
                                    f"Failed to send TG message, status: {resp.status}, response: {await resp.text()}"
                                )
                except Exception as e:
                    logger.error(f"Exception while sending TG message: {e}")

            return True

        except Exception as e:
            await session.rollback()
            logger.error(f"Failed to fulfill order {out_trade_no}: {e}")
            return False
