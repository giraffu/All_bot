import asyncio
from sqlalchemy import select
from src.database.core import AsyncSessionLocal
from src.database.models import History
from src.web_api.schemas.user_schema import HistoryItem

async def main():
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(History).order_by(History.id.desc()).limit(1))
        item = res.scalar()
        print(HistoryItem.model_validate(item).model_dump_json())

asyncio.run(main())
