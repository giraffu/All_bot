import asyncio
import sys
from sqlalchemy import select, text
from src.database.core import AsyncSessionLocal

async def main():
    try:
        async with AsyncSessionLocal() as session:
            # Check UserLog
            result = await session.execute(text("SELECT id, user_id, operation_type, credit_change, created_at, extra_info FROM user_logs WHERE user_id = 10000000041071 ORDER BY created_at DESC LIMIT 5"))
            print("UserLogs:")
            for row in result:
                print(row)
                
            # Check History
            result = await session.execute(text("SELECT id, user_id, task_id, type, created_at, is_visible FROM history WHERE user_id = 10000000041071 ORDER BY created_at DESC LIMIT 5"))
            print("\nHistory:")
            for row in result:
                print(row)

            # Check User
            result = await session.execute(text("SELECT id, telegram_id, username, credits FROM users WHERE id = 10000000041071 OR telegram_id = 10000000041071 LIMIT 1"))
            print("\nUser:")
            for row in result:
                print(row)
    except Exception as e:
        import traceback
        traceback.print_exc()

asyncio.run(main())
