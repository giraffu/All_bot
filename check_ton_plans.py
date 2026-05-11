import asyncio
from sqlalchemy import select
from src.database.core import AsyncSessionLocal
from src.database.models import MembershipPlan

async def main():
    async with AsyncSessionLocal() as session:
        plans = await session.execute(select(MembershipPlan))
        for p in plans.scalars().all():
            print(f"Plan ID: {p.id}, TON: {p.price_ton}")

asyncio.run(main())
