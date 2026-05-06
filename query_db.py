import asyncio
from src.database.core import AsyncSessionLocal
from sqlalchemy import text

async def main():
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("SELECT id, telegram_id, username, full_name, is_channel_member FROM users WHERE id = 10000000044836 OR telegram_id = 10000000044836;"))
        for row in result:
            print(row)

asyncio.run(main())
