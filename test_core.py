import asyncio
from src.database.core import AsyncSessionLocal
from sqlalchemy import select
from src.database.models import User
from src.core.user_core import get_or_create_user_by_telegram

async def test():
    # Test existing user
    print("Testing existing user...")
    user, is_new = await get_or_create_user_by_telegram(1150944233, "existing_user")
    print(f"Existing user: ID={user.id}, TG_ID={user.telegram_id}, is_new={is_new}")

    # Test new user
    print("\nTesting new user...")
    new_user, is_new = await get_or_create_user_by_telegram(9999999999, "new_user")
    print(f"New user: ID={new_user.id}, TG_ID={new_user.telegram_id}, is_new={is_new}")

    # Test billing core
    print("\nTesting billing core...")
    from src.core.billing_core import check_and_deduct_credits, refund_credits
    success, msg = await check_and_deduct_credits(new_user.id, 1, "test")
    print(f"Deduct 1 credit: success={success}, msg={msg}")
    
    await refund_credits(new_user.id, 1, "refund")
    print("Refunded 1 credit.")

if __name__ == "__main__":
    asyncio.run(test())
