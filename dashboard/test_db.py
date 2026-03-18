import asyncio
from sqlalchemy import select, func
from src.database.core import AsyncSessionLocal
from src.database.models import User

async def run():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(func.sum(User.temporary_ingot)))
        total_ingot = result.scalar()
        print("Total temporary_ingot:", total_ingot)
        
        result2 = await session.execute(select(func.sum(User.temp_credits)))
        total_temp = result2.scalar()
        print("Total temp_credits:", total_temp)
        
        result3 = await session.execute(select(User.id, User.temporary_ingot, User.temp_credits).where(User.temporary_ingot > 0).limit(5))
        users = result3.all()
        print("Users with temporary_ingot > 0:", users)
        
        result4 = await session.execute(select(User.id, User.temporary_ingot, User.temp_credits).where(User.temp_credits > 0).limit(5))
        users2 = result4.all()
        print("Users with temp_credits > 0:", users2)

asyncio.run(run())
