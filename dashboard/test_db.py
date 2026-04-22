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

from sqlalchemy import text

async def run():
    async with async_session() as db:
        res = await db.execute(text('SELECT name, price_rmb, price_stars, price_ton FROM membership_plans LIMIT 5'))
        for row in res:
            print(f"Plan: {row.name}, RMB: {row.price_rmb}, Stars: {row.price_stars}, TON: {row.price_ton}")

asyncio.run(run())
