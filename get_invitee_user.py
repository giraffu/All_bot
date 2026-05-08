import asyncio
from src.database.core import AsyncSessionLocal
from src.database.models import User
from sqlalchemy import select

async def main():
    async with AsyncSessionLocal() as session:
        stmt = select(User).where(User.id == 10000000046617)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        if user:
            print(f"ID: {user.id}, credits: {user.credits}, invited_by: {user.invited_by}")
        else:
            print("Not found")

if __name__ == "__main__":
    asyncio.run(main())
