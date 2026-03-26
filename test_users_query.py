import asyncio
from sqlalchemy import select, func
from src.database.core import get_db, async_session_maker
from src.database.models import User

async def main():
    async with async_session_maker() as db:
        stmt = select(func.count(User.id))
        result = await db.execute(stmt)
        print("Total users:", result.scalar())

if __name__ == "__main__":
    asyncio.run(main())
