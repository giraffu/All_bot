import httpx
import asyncio
from config import API_BASE

async def main():
    # we need to login or we can just fetch from DB and serialize like FastAPI does
    from fastapi.encoders import jsonable_encoder
    from src.database.core import AsyncSessionLocal
    from src.database.models import History
    from sqlalchemy import select
    
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(History).order_by(History.id.desc()).limit(1))
        item = res.scalar()
        print(jsonable_encoder(item.created_at))

asyncio.run(main())
