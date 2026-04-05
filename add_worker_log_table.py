import asyncio
import os
import sys

# Add parent directory to path so we can import src
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.database.core import engine
from src.database.models import WorkerLog

async def create_worker_logs_table():
    async with engine.begin() as conn:
        print("Creating worker_logs table...")
        await conn.run_sync(WorkerLog.__table__.create, checkfirst=True)
        print("Done.")

if __name__ == "__main__":
    asyncio.run(create_worker_logs_table())