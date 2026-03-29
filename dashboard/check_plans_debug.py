import asyncio
from src.database.core import AsyncSessionLocal, init_db
from src.database.models import MembershipPlan
from sqlalchemy import select

async def main():
    await init_db()
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(MembershipPlan))
        plans = res.scalars().all()
        print("Plans in DB:")
        for p in plans:
            print(f"ID: {p.id}, Name: '{p.name}', Identity: '{p.identity_name}', Credits: {p.reward_credits}")

if __name__ == "__main__":
    asyncio.run(main())
