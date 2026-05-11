import asyncio
from sqlalchemy import select
from src.database.core import AsyncSessionLocal
from src.database.models import MembershipPlan, Order, User

async def main():
    async with AsyncSessionLocal() as session:
        plans = await session.execute(select(MembershipPlan))
        for p in plans.scalars().all():
            print(f"Plan ID: {p.id}, Name: {p.name}, Stars: {p.price_stars}, RMB: {p.price_rmb}, Identity: {p.identity_name}, Credits: {p.reward_credits}, Duration: {p.duration_days}")

        # Check latest orders
        orders = await session.execute(select(Order).order_by(Order.id.desc()).limit(5))
        for o in orders.scalars().all():
            print(f"Order ID: {o.order_id}, Status: {o.status}, Plan: {o.plan_id}, User: {o.telegram_id}, Original: {o.original_price}, Final: {o.final_price}, TX: {o.tx_hash}")

asyncio.run(main())
