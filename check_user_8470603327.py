import asyncio
from sqlalchemy import select
from src.database.core import AsyncSessionLocal
from src.database.models import User

async def main():
    async with AsyncSessionLocal() as session:
        u = await session.execute(select(User).where(User.telegram_id == 8470603327))
        user = u.scalar_one_or_none()
        if user:
            print(f"User: {user.telegram_id}, Identity: {user.current_identity}, Credits: {user.credits}")

asyncio.run(main())
