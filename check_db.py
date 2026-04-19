import asyncio
from sqlalchemy import select
from src.database.core import AsyncSessionLocal
from src.database.models import History

async def main():
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(History.created_at).order_by(History.id.desc()).limit(1))
        print(res.scalar())

asyncio.run(main())
