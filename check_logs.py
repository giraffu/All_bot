import asyncio
import os
import sys
from sqlalchemy import select

# Add parent directory to path so we can import src
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.database.core import AsyncSessionLocal
from src.database.models import WorkerLog

async def check_logs():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(WorkerLog))
        logs = result.scalars().all()
        print(f"Found {len(logs)} logs:")
        for log in logs:
            print(f"  {log.id}: {log.worker_id} - {log.task_type} - {log.status}")

if __name__ == "__main__":
    asyncio.run(check_logs())