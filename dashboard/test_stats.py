import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv
import sys

sys.path.append("/home/hfy/APP/All_bot")

load_dotenv("/home/hfy/APP/All_bot/.env")
DB_URL = os.getenv("DATABASE_URL")
if not DB_URL:
    DB_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/bot_db"

engine = create_async_engine(DB_URL)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

from dashboard.backend.routers.stats import get_stats_history

async def run():
    async with async_session() as db:
        res = await get_stats_history(days=2, db=db)
        for r in res:
            print(r["date"], "TON:", r["ton_recharge"], "Stars:", r["stars_recharge"], "RMB:", r["rmb_recharge"], "USDT:", r["usdt_recharge"], "Cumulative USDT:", r["cumulative_usdt"])

asyncio.run(run())
