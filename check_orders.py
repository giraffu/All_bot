import asyncio
from sqlalchemy import select
from src.database.core import AsyncSessionLocal
from src.database.models import Order

async def main():
    async with AsyncSessionLocal() as session:
        orders = await session.execute(select(Order).where(Order.plan_id == 3).order_by(Order.id.desc()).limit(10))
        for o in orders.scalars().all():
            print(f"ID: {o.id}, Order ID: {o.order_id}, Status: {o.status}, Plan: {o.plan_id}, User: {o.telegram_id}, Original: {o.original_price}, Final: {o.final_price}, TX: {o.tx_hash}")

asyncio.run(main())
