import asyncio
from sqlalchemy import select
from src.database.core import AsyncSessionLocal
from src.database.models import Order, User

async def main():
    async with AsyncSessionLocal() as session:
        orders = await session.execute(select(Order).where(Order.plan_id == 7).order_by(Order.id.desc()).limit(5))
        for o in orders.scalars().all():
            u = await session.execute(select(User).where(User.id == o.telegram_id))
            user = u.scalar_one_or_none()
            print(f"ID: {o.id}, Order: {o.order_id}, Status: {o.status}, Plan: {o.plan_id}, UserTG: {user.telegram_id if user else 'None'}, UserID: {o.telegram_id}")

asyncio.run(main())
