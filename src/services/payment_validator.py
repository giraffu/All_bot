import asyncio
import logging
from decimal import Decimal

import aiohttp
from sqlalchemy.future import select

from config import VITE_MERCHANT_ADDRESS
from src.database.core import AsyncSessionLocal
from src.database.models import MembershipPlan, Order, User, UserLog

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

                    if order_id and order_id.startswith("ORDER:"):
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
        Format: ORDER:{tgUserId}:{planId}:{timestamp}
        Returns True if processing is complete (success or definitive failure), False if it should be retried.
        """
        logger.info(
            f"Processing order from blockchain: {order_id} with amount {amount_nanotons}"
        )

        try:
            parts = order_id.split(":")
            if len(parts) != 4:
                logger.warning(f"Invalid order format: {order_id}")
                return True  # Don't retry invalid formats

            try:
                tg_user_id = int(parts[1])
                plan_id = int(parts[2])
            except ValueError:
                logger.warning(f"Invalid integer in order format: {order_id}")
                return True

            from src.core.user_core import get_or_create_user_by_telegram

            internal_user, _ = await get_or_create_user_by_telegram(tg_user_id)
            internal_user_id = internal_user.id

            async with AsyncSessionLocal() as db:
                try:
                    # 1. Check if already processed (by tx_hash)
                    existing_tx = await db.execute(
                        select(Order).where(Order.tx_hash == tx_hash)
                    )
                    if existing_tx.scalar_one_or_none():
                        logger.info(f"Transaction {tx_hash} already processed.")
                        return True

                    # Also check order_id for legacy or exact duplicate payload
                    existing_order = await db.execute(
                        select(Order).where(Order.order_id == order_id)
                    )
                    if existing_order.scalar_one_or_none():
                        # Append a suffix to avoid duplicate order_id
                        order_id = f"{order_id}_{tx_hash[:8]}"

                    # 2. Get Plan and User
                    plan_res = await db.execute(
                        select(MembershipPlan).where(MembershipPlan.id == plan_id)
                    )
                    plan = plan_res.scalar_one_or_none()
                    if not plan:
                        logger.error(f"Plan {plan_id} not found for order {order_id}")
                        return True

                    user_res = await db.execute(
                        select(User).where(User.id == internal_user_id)
                    )
                    user = user_res.scalar_one_or_none()
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

                    # 3. Create Order Record
                    new_order = Order(
                        order_id=order_id,
                        telegram_id=internal_user_id,
                        plan_id=plan_id,
                        original_price=plan.price_ton,
                        final_price=Decimal(amount_nanotons)
                        / Decimal(str(TON_TO_NANOTON)),
                        status=status,
                        tx_hash=tx_hash,
                    )
                    db.add(new_order)

                    if status == "SUCCESS":
                        # 4. Fulfill using atomic update
                        from datetime import datetime, timedelta

                        from sqlalchemy import update

                        # 身份和有效期逻辑
                        now = datetime.now()
                        new_expire_at = user.identity_expire_at
                        converted_days = 0
                        final_identity = plan.identity_name
                        is_downgrade = False

                        identity_priority = {
                            "外门弟子": 0,
                            "内门弟子": 1,
                            "核心弟子": 2,
                            "真传弟子": 3,
                        }
                        identity_ratio = {
                            "外门弟子": 1,
                            "内门弟子": 2,
                            "核心弟子": 5,
                            "真传弟子": 10,
                        }

                        current_priority = identity_priority.get(
                            user.current_identity, 0
                        )
                        new_priority = identity_priority.get(plan.identity_name, 0)

                        if new_expire_at and new_expire_at > now:
                            if user.current_identity == plan.identity_name:
                                # 同套餐续费
                                new_expire_at += timedelta(days=plan.duration_days)
                            elif new_priority > current_priority:
                                # 升级：将旧身份残值折算为新身份天数
                                import math

                                remaining_days = (
                                    new_expire_at - now
                                ).total_seconds() / 86400.0
                                old_ratio = identity_ratio.get(user.current_identity, 1)
                                new_ratio = identity_ratio.get(plan.identity_name, 1)

                                # 残值 = 剩余天数 * 旧比例，折算天数 = 残值 / 新比例
                                converted_days = math.ceil(
                                    (remaining_days * old_ratio) / new_ratio
                                )
                                new_expire_at = now + timedelta(
                                    days=plan.duration_days + converted_days
                                )
                            else:
                                # 降级或同级：保留高等级身份，将新购买的低等级套餐价值折算为高等级身份的天数
                                is_downgrade = True
                                final_identity = user.current_identity

                                import math

                                old_ratio = identity_ratio.get(user.current_identity, 1)
                                new_ratio = identity_ratio.get(plan.identity_name, 1)

                                # 新购价值 = 新套餐天数 * 新比例，折算天数 = 新购价值 / 旧比例
                                extra_days = math.ceil(
                                    (plan.duration_days * new_ratio) / old_ratio
                                )
                                converted_days = extra_days
                                new_expire_at += timedelta(days=extra_days)
                        else:
                            # 身份已过期或首次充值
                            new_expire_at = now + timedelta(days=plan.duration_days)

                        # Perform update
                        await db.execute(
                            update(User)
                            .where(User.id == internal_user_id)
                            .values(
                                credits=User.credits + plan.reward_credits,
                                current_identity=final_identity,
                                identity_expire_at=new_expire_at,
                            )
                        )

                        # Calculate new balance for the log
                        new_balance = user.credits + plan.reward_credits

                        import json

                        log = UserLog(
                            user_id=user.id,
                            username=user.username,
                            operation_type="recharge",
                            credit_change=plan.reward_credits,
                            current_balance=new_balance,
                            extra_info=json.dumps(
                                {
                                    "order_id": order_id,
                                    "plan": plan.name,
                                    "tx_hash": tx_hash,
                                    "converted_days": converted_days,
                                    "identity": final_identity,
                                },
                                ensure_ascii=False,
                            ),
                        )
                        db.add(log)

                        await db.commit()
                        logger.info(
                            f"Successfully fulfilled order {order_id} for user {tg_user_id}"
                        )

                        # 5. Notify User
                        try:
                            msg_text = (
                                f"🎉 <b>充值成功！</b>\n\n"
                                f"恭喜道友，您已成功购买【{plan.name}】。\n"
                                f"💎 获得灵石：+{plan.reward_credits}\n"
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

                            msg_text += f"⏳ 到期时间：{new_expire_at.strftime('%Y-%m-%d %H:%M:%S')}\n\n祝您仙途坦荡！"

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
