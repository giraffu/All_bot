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
                        
                    self.last_lt = tx_lt
                    
                    in_msg = tx.get("in_msg", {})
                    if not in_msg:
                        continue
                        
                    amount_nanotons = int(in_msg.get("value", 0))
                    if amount_nanotons <= 0:
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
                        await self._process_order(order_id, amount_nanotons, tx_hash)

    async def _process_order(self, order_id: str, amount_nanotons: int, tx_hash: str):
        """
        Process a found order: verify amount, fulfill, and notify user.
        Format: ORDER:{tgUserId}:{planId}:{timestamp}
        """
        logger.info(f"Processing order from blockchain: {order_id} with amount {amount_nanotons}")
        
        try:
            parts = order_id.split(":")
            if len(parts) != 4:
                logger.warning(f"Invalid order format: {order_id}")
                return
                
            tg_user_id = int(parts[1])
            plan_id = int(parts[2])
            
            async with AsyncSessionLocal() as db:
                # 1. Check if already processed
                existing_order = await db.execute(select(Order).where(Order.order_id == order_id))
                if existing_order.scalar_one_or_none():
                    logger.info(f"Order {order_id} already processed.")
                    return
                    
                # 2. Get Plan and User
                plan_res = await db.execute(select(MembershipPlan).where(MembershipPlan.id == plan_id))
                plan = plan_res.scalar_one_or_none()
                if not plan:
                    logger.error(f"Plan {plan_id} not found for order {order_id}")
                    return
                    
                user_res = await db.execute(select(User).where(User.id == tg_user_id))
                user = user_res.scalar_one_or_none()
                if not user:
                    logger.error(f"User {tg_user_id} not found for order {order_id}")
                    return
                
                # Note: In frontend-only approach, we must trust the frontend's price or recalculate.
                # Here we just check if they paid at least the plan's base price * 0.5 (max discount).
                # For strict security, you'd recalculate the exact expected price here.
                expected_min_nanotons = int(plan.price_ton * Decimal('0.5') * 10**9)
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
                    # 4. Fulfill
                    user.credits += plan.reward_credits
                    user.current_identity = plan.identity_name
                    user.is_first_charge = False
                    
                    log = UserLog(
                        user_id=user.id,
                        username=user.username,
                        operation_type="recharge",
                        credit_change=plan.reward_credits,
                        current_balance=user.credits,
                        extra_info=f'{{"order_id": "{order_id}", "plan": "{plan.name}"}}'
                    )
                    db.add(log)
                    
                    await db.commit()
                    logger.info(f"Successfully fulfilled order {order_id} for user {tg_user_id}")
                    
                    # 5. Notify User
                    try:
                        await self.bot_app.bot.send_message(
                            chat_id=tg_user_id,
                            text=f"🎉 **充值成功！**\n\n"
                                 f"恭喜道友，您已成功购买【{plan.name}】。\n"
                                 f"💎 获得灵石：+{plan.reward_credits}\n"
                                 f"🪪 当前身份晋升为：**{plan.identity_name}**\n\n"
                                 f"祝您仙途坦荡！",
                            parse_mode="Markdown"
                        )
                    except Exception as e:
                        logger.error(f"Failed to send success message to {tg_user_id}: {e}")
                else:
                    await db.commit()

        except Exception as e:
            logger.error(f"Error processing order {order_id}: {e}")
