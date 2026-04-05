import asyncio
from src.database.core import engine, AsyncSessionLocal
from sqlalchemy import text
from src.database.models import MembershipPlan

async def main():
    async with engine.begin() as conn:
        try:
            await conn.execute(text("ALTER TABLE membership_plans ADD COLUMN price_rmb DECIMAL(10, 2) NOT NULL DEFAULT 0.00;"))
            print("Column price_rmb added.")
        except Exception as e:
            print(f"Failed to add column (might already exist): {e}")
            
    async with AsyncSessionLocal() as session:
        # Update 200 stars to 30.00
        await session.execute(text("UPDATE membership_plans SET price_rmb = 30.00 WHERE price_stars = 200"))
        # Update 500 stars to 70.00
        await session.execute(text("UPDATE membership_plans SET price_rmb = 70.00 WHERE price_stars = 500"))
        # Update 1000 stars to 120.00
        await session.execute(text("UPDATE membership_plans SET price_rmb = 120.00 WHERE price_stars = 1000"))
        await session.commit()
        print("Updated initial RMB prices.")

if __name__ == "__main__":
    asyncio.run(main())
