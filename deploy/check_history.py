import asyncio
from sqlalchemy import select
from src.database.core import AsyncSessionLocal
from src.database.models import History

async def main():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(History).order_by(History.id.desc()).limit(10))
        for row in result.scalars():
            print(row.id, row.user_id, row.type, row.output_file)

asyncio.run(main())