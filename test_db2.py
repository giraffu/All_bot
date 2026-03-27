import asyncio
from sqlalchemy import text
from src.database.core import AsyncSessionLocal

async def main():
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("SELECT price_stars FROM membership_plans"))
        rows = result.fetchall()
        print("ROWS:", rows)

asyncio.run(main())
