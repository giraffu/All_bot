import asyncio
import logging
from datetime import datetime
from decimal import Decimal

import aiohttp
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.future import select

from config import VITE_MERCHANT_ADDRESS
from src.database.core import AsyncSessionLocal
from src.database.models import MembershipPlan, Order, User, UserLog
from src.services.affiliate_redeem_service import is_membership_settlement_v2_enabled
from src.services.membership_settlement_service import (
    MembershipSettlementAuditSource,
    settle_membership_plan_in_session,
)
from src.services.order_v2_service import (
    build_order_public_lookup_stmt,
    parse_order_payload,
)

logger = logging.getLogger(__name__)


def parse_payload_boc(boc_str: str) -> str:
    """
    Parses a BOC payload (base64 or hex) and returns the text comment.
    """
    import base64

    try:
        from pytoniq_core import Cell

        boc_bytes = None

        # Try base64 first
        try:
            boc_bytes = base64.b64decode(boc_str)
            cell = Cell.one_from_boc(boc_bytes)
        except Exception:
            # If base64 fails or Cell parsing fails, try hex
            boc_bytes = bytes.fromhex(boc_str)
            cell = Cell.one_from_boc(boc_bytes)

        slice = cell.begin_parse()
        opcode = slice.load_uint(32)
        if opcode == 0:
            return slice.load_snake_string()
        return None
    except Exception:
        return None


class TonPaymentValidator:
    def __init__(self, bot_app, api_base: str = "https://toncenter.com/api/v2/jsonRPC"):
        self.api_base = api_base
        self.bot_app = bot_app
        self.merchant_address = VITE_MERCHANT_ADDRESS
        self.last_lt = 0  # Logical time of the last processed transaction

    async def poll_transactions(self):
        """
        Background task to poll transactions continuously.
        """
        logger.info(
            f"Starting TON payment polling for address: {self.merchant_address}"
        )

        while True:
            try:
                await self._check_new_transactions()
            except Exception as e:
                logger.error(f"Error in TON polling task: {e}")

            # Sleep for 15 seconds before next poll
            await asyncio.sleep(15)

    async def _check_new_transactions(self):
        async with aiohttp.ClientSession() as session:
            payload = {
                "method": "getTransactions",
                "params": {
                    "address": self.merchant_address,
                    "limit": 20,
                    "archival": True,
                },
                "id": 1,
                "jsonrpc": "2.0",
            }

            async with session.post(self.api_base, json=payload) as resp:
                try:
                    data = await resp.json()
                except Exception as e:
                    logger.warning(f"Failed to decode JSON from TON API: {e}. Status: {resp.status}")
                    return

                if not isinstance(data, dict) or "result" not in data:
                    logger.error(f"Failed to fetch transactions or invalid format: {data}")
                    return

                transactions = data["result"]
                if not isinstance(transactions, list):
                    logger.error(f"Transactions is not a list: {transactions}")
                    return

                # Process from oldest to newest in the current batch
                for tx in reversed(transactions):
                    if not isinstance(tx, dict):
                        continue

                    tx_id_info = tx.get("transaction_id", {})
                    if not isinstance(tx_id_info, dict):
                        tx_id_info = {}

                    try:
                        tx_lt = int(tx_id_info.get("lt", 0))
                    except (ValueError, TypeError):
                        tx_lt = 0

                    tx_hash = tx_id_info.get("hash", "")

                    if tx_lt <= self.last_lt:
                        continue  # Already processed

                    in_msg = tx.get("in_msg", {})
                    if not isinstance(in_msg, dict) or not in_msg:
                        self.last_lt = tx_lt
                        continue

                    try:
                        amount_nanotons = int(in_msg.get("value", 0))
                    except (ValueError, TypeError):
                        amount_nanotons = 0

                    if amount_nanotons <= 0:
                        self.last_lt = tx_lt
                        continue

                    # Extract message/payload
                    msg_data = in_msg.get("message", "")
                    if not isinstance(msg_data, str):
                        msg_data = ""

                    msg_data_info = in_msg.get("msg_data", {})
                    if not isinstance(msg_data_info, dict):
                        msg_data_info = {}
                    msg_data_boc = msg_data_info.get("body", "")  # Might be in body

                    # Try to parse payload
                    order_id = None
                    if msg_data_boc:
                        order_id = parse_payload_boc(msg_data_boc)
                    elif msg_data and msg_data.startswith("ORDER:"):
                        # If it's plain text somehow
                        order_id = msg_data

                    parsed_payload = parse_order_payload(order_id) if order_id else None
                    if parsed_payload and parsed_payload.kind in {"legacy", "v2"}:
                        success = await self._process_order(
                            order_id, amount_nanotons, tx_hash
                        )
                        if success:
                            self.last_lt = tx_lt
                        else:
                            # If a transaction fails to process (e.g. DB error), we should stop
                            # advancing last_lt and break, so it can be retried in the next poll.
                            break
                    else:
                        self.last_lt = tx_lt

    async def _process_order(
        self, order_id: str, amount_nanotons: int, tx_hash: str
    ) -> bool:
        """
        Process a found order: verify amount, fulfill, and notify user.
        Returns True if processing is complete (success or definitive failure), False if it should be retried.
        """
        logger.info(
            f"Processing order from blockchain: {order_id} with amount {amount_nanotons}"
        )

        try:
            parsed_payload = parse_order_payload(order_id)
            if parsed_payload.kind == "unknown":
                logger.warning(f"Invalid order format: {order_id}")
                return True

            from src.core.user_core import get_or_create_user_by_telegram

            async with AsyncSessionLocal() as db:
                try:
                    tg_user_id = None
                    existing_pending_order = None
                    if parsed_payload.kind == "v2" and parsed_payload.business_order_id:
                        existing_pending_order = (
                            await db.execute(
                                build_order_public_lookup_stmt(
                                    parsed_payload.business_order_id, for_update=True
                                )
                            )
                        ).scalar_one_or_none()
                        if not existing_pending_order:
                            logger.warning(
                                "business_order_id not found for TON payment: %s",
                                parsed_payload.business_order_id,
                            )
                            return True
                        plan_id = existing_pending_order.plan_id
                        internal_user_id = existing_pending_order.telegram_id
                        tg_user_id = internal_user_id
                        plan = (
                            await db.execute(
                                select(MembershipPlan).where(
                                    MembershipPlan.id == existing_pending_order.plan_id
                                )
                            )
                        ).scalar_one_or_none()
                        user = (
                            await db.execute(
                                select(User)
                                .where(User.id == existing_pending_order.telegram_id)
                                .with_for_update()
                            )
                        ).scalar_one_or_none()
                    else:
                        internal_user, _ = await get_or_create_user_by_telegram(
                            int(parsed_payload.telegram_user_id)
                        )
                        internal_user_id = internal_user.id
                        tg_user_id = int(parsed_payload.telegram_user_id)
                        plan_id = int(parsed_payload.plan_id)

                        existing_order = await db.execute(
                            select(Order).where(Order.order_id == order_id)
                        )
                        if existing_order.scalar_one_or_none():
                            order_id = f"{order_id}_{tx_hash[:8]}"

                        plan = (
                            await db.execute(
                                select(MembershipPlan).where(MembershipPlan.id == plan_id)
                            )
                        ).scalar_one_or_none()
                        user = (
                            await db.execute(
                                select(User)
                                .where(User.id == internal_user_id)
                                .with_for_update()
                            )
                        ).scalar_one_or_none()

                    if not plan:
                        logger.error(f"Plan {plan_id} not found for order {order_id}")
                        return True
                    if not user:
                        logger.error(
                            f"User {internal_user_id} not found for order {order_id}"
                        )
                        return True

                    # Exact price match with tiny slippage allowed
                    from src.constants import TON_SLIPPAGE_NANOTON, TON_TO_NANOTON

                    expected_min_nanotons = (
                        int(plan.price_ton * Decimal(str(TON_TO_NANOTON)))
                        - TON_SLIPPAGE_NANOTON
                    )
                    if expected_min_nanotons < 0:
                        expected_min_nanotons = 0

                    if amount_nanotons < expected_min_nanotons:
                        logger.warning(
                            f"Insufficient funds for order {order_id}: {amount_nanotons} < {expected_min_nanotons}"
                        )
                        status = "FAILED"
                    else:
                        status = "SUCCESS"

                    if existing_pending_order is not None:
                        if existing_pending_order.status == "SUCCESS":
                            logger.info("Transaction %s already processed.", tx_hash)
                            return True
                        existing_pending_order.status = status
                        existing_pending_order.tx_hash = tx_hash
                        existing_pending_order.payment_channel = "TON"
                        existing_pending_order.final_price = Decimal(amount_nanotons) / Decimal(
                            str(TON_TO_NANOTON)
                        )
                        existing_pending_order.paid_at = (
                            datetime.now() if status == "SUCCESS" else None
                        )
                        new_order = existing_pending_order
                        await db.flush()
                    else:
                        inserted_order_id = (
                            await db.execute(
                                insert(Order)
                                .values(
                                    order_id=order_id,
                                    telegram_id=internal_user_id,
                                    plan_id=plan_id,
                                    original_price=plan.price_ton,
                                    final_price=Decimal(amount_nanotons)
                                    / Decimal(str(TON_TO_NANOTON)),
                                    status=status,
                                    tx_hash=tx_hash,
                                    payment_channel="TON",
                                    paid_at=datetime.now()
                                    if status == "SUCCESS"
                                    else None,
                                )
                                .on_conflict_do_nothing(index_elements=["tx_hash"])
                                .returning(Order.id)
                            )
                        ).scalar_one_or_none()
                        if inserted_order_id is None:
                            logger.info(f"Transaction {tx_hash} already processed.")
                            return True

                        new_order = await db.get(Order, inserted_order_id)
                        if new_order is None:
                            raise RuntimeError(
                                f"failed to reload inserted TON order for tx_hash: {tx_hash}"
                            )
                        if new_order.tx_hash != tx_hash:
                            raise RuntimeError(
                                f"inserted TON order tx_hash mismatch for tx_hash: {tx_hash}"
                            )

                    if status == "SUCCESS":
                        from src.core.affiliate_core import (
                            calculate_and_set_commission_for_paid_order,
                            invalidate_invitation_recharge_cache,
                            record_affiliate_commission_transaction,
                        )

                        await db.flush()
                        referral = await calculate_and_set_commission_for_paid_order(
                            db, new_order
                        )
                        if referral and Decimal(str(new_order.commission_usdt or 0)) > 0:
                            inserted = await record_affiliate_commission_transaction(
                                db,
                                new_order,
                                referral,
                                source="ton_payment_validator",
                            )
                            if not inserted:
                                logger.warning(
                                    "affiliate ledger insert skipped for TON order_id=%s order_pk=%s tx_hash=%s",
                                    new_order.order_id,
                                    new_order.id,
                                    new_order.tx_hash,
                                )

                        now = datetime.now()
                        if is_membership_settlement_v2_enabled():
                            applied_snapshot = await settle_membership_plan_in_session(
                                locked_user=user,
                                plan=plan,
                                audit_source=MembershipSettlementAuditSource(
                                    source="ton_payment_validator",
                                    source_channel="TON",
                                    source_order_id=str(new_order.order_id),
                                    source_tx_hash=tx_hash,
                                ),
                                session=db,
                                now=now,
                                grant_reward_credits=True,
                            )
                        else:
                            from src.core.billing_core import calculate_identity_conversion
                            import json

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
                                "is_downgrade": False,
                            }
                            log = UserLog(
                                user_id=user.id,
                                username=user.username,
                                operation_type="recharge",
                                credit_change=plan.reward_credits,
                                current_balance=user.credits,
                                extra_info=json.dumps(
                                    {
                                        "order_id": order_id,
                                        "plan": plan.name,
                                        "tx_hash": tx_hash,
                                    },
                                    ensure_ascii=False,
                                ),
                            )
                            db.add(log)

                        await db.commit()
                        if referral:
                            await invalidate_invitation_recharge_cache(
                                referral.inviter_id
                            )
                        logger.info(
                            f"Successfully fulfilled order {order_id} for user {tg_user_id}"
                        )

                        # 5. Notify User
                        try:
                            credits_granted = int(applied_snapshot.get("credits_granted", 0))
                            converted_days = int(applied_snapshot.get("converted_days", 0))
                            final_identity = str(
                                applied_snapshot.get("final_identity", user.current_identity)
                            )
                            final_expire_at = applied_snapshot.get("final_expire_at")
                            is_downgrade = bool(applied_snapshot.get("is_downgrade", False))
                            msg_text = (
                                f"🎉 <b>充值成功！</b>\n\n"
                                f"恭喜道友，您已成功购买【{plan.name}】。\n"
                                f"💎 获得灵石：+{credits_granted}\n"
                            )
                            if is_downgrade:
                                msg_text += (
                                    f"🪪 当前身份保持为：<b>{final_identity}</b>\n"
                                )
                                if converted_days > 0:
                                    msg_text += f"⚖️ 新套餐价值已折算为 <b>{converted_days}</b> 天当前高级身份时长\n"
                            else:
                                msg_text += (
                                    f"🪪 当前身份晋升为：<b>{final_identity}</b>\n"
                                )
                                if converted_days > 0:
                                    msg_text += f"⚖️ 老套餐残值已折算为 <b>{converted_days}</b> 天新套餐时长\n"

                            if final_expire_at:
                                msg_text += (
                                    f"⏳ 到期时间：{final_expire_at}\n\n祝您仙途坦荡！"
                                )
                            else:
                                msg_text += "\n祝您仙途坦荡！"

                            await self.bot_app.bot.send_message(
                                chat_id=tg_user_id, text=msg_text, parse_mode="HTML"
                            )
                        except Exception as e:
                            logger.error(
                                f"Failed to send success message to {tg_user_id}: {e}"
                            )
                    else:
                        await db.commit()

                    return True

                except Exception as db_e:
                    await db.rollback()
                    logger.error(f"Database error processing order {order_id}: {db_e}")
                    return False

        except Exception as e:
            logger.error(f"Error processing order {order_id}: {e}")
            return False
