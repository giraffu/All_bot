import asyncio
from sqlalchemy import text
from src.database.core import AsyncSessionLocal
from src.core.billing_core import refund_credits

async def main():
    user_id = 10000000041071
    amount = 20
    reason = "refund"
    operator = "system_fix_bug"
    
    try:
        await refund_credits(user_id, amount, reason, operator)
        print(f"Successfully refunded {amount} credits to {user_id}")
    except Exception as e:
        print(f"Failed to refund: {e}")

asyncio.run(main())
