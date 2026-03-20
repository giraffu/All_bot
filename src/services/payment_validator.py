import aiohttp
import asyncio
import logging
from typing import Optional, List, Dict, Any
from sqlalchemy.future import select
from decimal import Decimal

from src.database.core import AsyncSessionLocal
from src.database.models import User, Order, MembershipPlan, UserLog
from config import VITE_MERCHANT_ADDRESS

logger = logging.getLogger(__name__)

def parse_payload_boc(boc_hex: str) -> str:
    """
    Parses a BOC payload and returns the text comment.
    """
    try:
        from pytoniq_core import Cell
        cell = Cell.one_from_boc(bytes.fromhex(boc_hex))
        slice = cell.begin_parse()
        opcode = slice.load_uint(32)
        if opcode == 0:
            return slice.load_snake_string()
        return None
    except Exception as e:
        return None

class TonPaymentValidator:
    def __init__(self, bot_app, api_base: str = "https://toncenter.com/api/v2/jsonRPC"):
        self.api_base = api_base
        self.bot_app = bot_app
        self.merchant_address = VITE_MERCHANT_ADDRESS
        self.last_lt = 0 # Logical time of the last processed transaction
        
    async def poll_transactions(self):
        """
        Background task to poll transactions continuously.
        """
        logger.info(f"Starting TON payment polling for address: {self.merchant_address}")
        
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
                    "archival": True
                },
                "id": 1,
                "jsonrpc": "2.0"
            }
            
            async with session.post(self.api_base, json=payload) as resp:
                data = await resp.json()
                
                if "result" not in data:
                    logger.error(f"Failed to fetch transactions: {data}")
                    return
                    
                transactions = data["result"]
                
                # Process from oldest to newest in the current batch
                for tx in reversed(transactions):
                    tx_lt = int(tx.get("transaction_id", {}).get("lt", 0))
                    tx_hash = tx.get("transaction_id", {}).get("hash", "")
                    
                    if tx_lt <= self.last_lt:
                        continue # Already processed
                        
                    in_msg = tx.get("in_msg", {})
                    if not in_msg:
                        self.last_lt = tx_lt
                        continue
                        
                    amount_nanotons = int(in_msg.get("value", 0))
                    if amount_nanotons <= 0:
                        self.last_lt = tx_lt
                        continue
                        
                    # Extract message/payload
                    msg_data = in_msg.get("message", "")
                    msg_data_boc = in_msg.get("msg_data", {}).get("body", "") # Might be in body
                    
                    # Try to parse payload
                    order_id = None
                    if msg_data_boc:
                        order_id = parse_payload_boc(msg_data_boc)
                    elif msg_data and msg_data.startswith("ORDER:"):
                        # If it's plain text somehow
                        order_id = msg_data
                        
                    if order_id and order_id.startswith("ORDER:"):
                        success = await self._process_order(order_id, amount_nanotons, tx_hash)
                        if success:
                            self.last_lt = tx_lt
                    else:
                        self.last_lt = tx_lt

    async def _process_order(self, order_id: str, amount_nanotons: int, tx_hash: str) -> bool:
        """
        Process a found order: verify amount, fulfill, and notify user.
        Format: ORDER:{tgUserId}:{planId}:{timestamp}
        Returns True if processing is complete (success or definitive failure), False if it should be retried.
        """
        logger.info(f"Processing order from blockchain: {order_id} with amount {amount_nanotons}")
        
        try:
            parts = order_id.split(":")
            if len(parts) != 4:
                logger.warning(f"Invalid order format: {order_id}")
                return True # Don't retry invalid formats
                
            try:
                tg_user_id = int(parts[1])
                plan_id = int(parts[2])
            except ValueError:
                logger.warning(f"Invalid integer in order format: {order_id}")
                return True
            
            async with AsyncSessionLocal() as db:
                try:
                    # 1. Check if already processed (by tx_hash)
                    existing_tx = await db.execute(select(Order).where(Order.tx_hash == tx_hash))
                    if existing_tx.scalar_one_or_none():
                        logger.info(f"Transaction {tx_hash} already processed.")
                        return True
                        
                    # Also check order_id for legacy or exact duplicate payload
                    existing_order = await db.execute(select(Order).where(Order.order_id == order_id))
                    if existing_order.scalar_one_or_none():
                        # Append a suffix to avoid duplicate order_id
                        order_id = f"{order_id}_{tx_hash[:8]}"

                    # 2. Get Plan and User
                    plan_res = await db.execute(select(MembershipPlan).where(MembershipPlan.id == plan_id))
                    plan = plan_res.scalar_one_or_none()
                    if not plan:
                        logger.error(f"Plan {plan_id} not found for order {order_id}")
                        return True
                        
                    user_res = await db.execute(select(User).where(User.id == tg_user_id))
                    user = user_res.scalar_one_or_none()
                    if not user:
                        logger.error(f"User {tg_user_id} not found for order {order_id}")
                        return True
                    
                    # Exact price match with tiny slippage allowed (0.01 TON)
                    expected_min_nanotons = int(plan.price_ton * Decimal('1000000000')) - 10000000
                    if expected_min_nanotons < 0:
                        expected_min_nanotons = 0

                    if amount_nanotons < expected_min_nanotons:
                        logger.warning(f"Insufficient funds for order {order_id}: {amount_nanotons} < {expected_min_nanotons}")
                        status = "FAILED"
                    else:
                        status = "SUCCESS"
                    
                    # 3. Create Order Record
                    new_order = Order(
                        order_id=order_id,
                        telegram_id=tg_user_id,
                        plan_id=plan_id,
                        original_price=plan.price_ton,
                        final_price=Decimal(amount_nanotons) / Decimal(10**9),
                        status=status,
                        tx_hash=tx_hash
                    )
                    db.add(new_order)
                    
                    if status == "SUCCESS":
                        # 4. Fulfill using atomic update
                        from sqlalchemy import update
                        from datetime import datetime, timedelta
                        
                        now = datetime.now()
                        new_expire_at = user.identity_expire_at
                        if new_expire_at and new_expire_at > now:
                            new_expire_at += timedelta(days=plan.duration_days)
                        else:
                            new_expire_at = now + timedelta(days=plan.duration_days)
                            
                        # Perform update
                        await db.execute(
                            update(User)
                            .where(User.id == tg_user_id)
                            .values(
                                credits=User.credits + plan.reward_credits,
                                current_identity=plan.identity_name,
                                is_first_charge=False,
                                identity_expire_at=new_expire_at
                            )
                        )
                        
                        # Calculate new balance for the log
                        new_balance = user.credits + plan.reward_credits
                        
                        log = UserLog(
                            user_id=user.id,
                            username=user.username,
                            operation_type="recharge",
                            credit_change=plan.reward_credits,
                            current_balance=new_balance,
                            extra_info=f'{{"order_id": "{order_id}", "plan": "{plan.name}"}}'
                        )
                        db.add(log)
                        
                        await db.commit()
                        logger.info(f"Successfully fulfilled order {order_id} for user {tg_user_id}")
                        
                        # 5. Notify User
                        try:
                            await self.bot_app.bot.send_message(
                                chat_id=tg_user_id,
                                text=f"🎉 <b>充值成功！</b>\n\n"
                                     f"恭喜道友，您已成功购买【{plan.name}】。\n"
                                     f"💎 获得灵石：+{plan.reward_credits}\n"
                                     f"🪪 当前身份晋升为：<b>{plan.identity_name}</b>\n\n"
                                     f"祝您仙途坦荡！",
                                parse_mode="HTML"
                            )
                        except Exception as e:
                            logger.error(f"Failed to send success message to {tg_user_id}: {e}")
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
