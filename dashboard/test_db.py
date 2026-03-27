import asyncio
from sqlalchemy import select
from src.database.core import AsyncSessionLocal
from src.database.models import MembershipPlan

async def main():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(MembershipPlan))
        plans = result.scalars().all()
        for p in plans:
            print(f"ID: {p.id}, Name: {p.name}, TON: {p.price_ton}, Credits: {p.reward_credits}, Duration: {p.duration_days}")

asyncio.run(main())
