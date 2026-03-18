import asyncio
from src.database.core import AsyncSessionLocal
from src.database.models import User
from sqlalchemy import select

async def main():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).limit(5))
        users = result.scalars().all()
        for u in users:
            print(f"ID: {u.id}, Credits: {u.credits}, Temp: {u.temp_credits}, Referrals: {u.referral_count}, Checkins: {u.checkin_count}, Generations: {u.generation_count}")

asyncio.run(main())
