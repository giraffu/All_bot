import asyncio
from sqlalchemy import select, func
from src.database.core import AsyncSessionLocal
from src.database.models import User

async def run():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(func.sum(User.temporary_ingot)))
        print("Total temporary_ingot:", result.scalar())

asyncio.run(run())
