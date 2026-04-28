import asyncio
from sqlalchemy import select
from src.database.database import get_db_session
from src.database.models import WorkerLog
import json

async def check():
    async with get_db_session() as session:
        stmt = select(WorkerLog).where(WorkerLog.task_id == 'ffe7c5e9-1f73-4181-89e3-8187afaba319')
        result = await session.execute(stmt)
        logs = result.scalars().all()
        for log in logs:
            print(f"ID: {log.id}, Worker: {log.worker_id}, Status: {log.status}, Message: {log.message}, Timestamp: {log.timestamp}")
            print(f"Details: {log.details}")

asyncio.run(check())
