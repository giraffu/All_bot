import asyncio
import sys
import os
from pathlib import Path
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Add src to path
sys.path.append(os.getcwd())

from src.database.models import UserLog

DB_PATH = "sqlite+aiosqlite:///bot_data.db"

async def view_logs(limit=20):
    engine = create_async_engine(DB_PATH, echo=False)
    AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with AsyncSessionLocal() as session:
        print(f"{'ID':<6} | {'User ID':<10} | {'Type':<20} | {'Credit':<6} | {'Balance':<8} | {'Time':<20}")
        print("-" * 80)
        
        stmt = select(UserLog).order_by(desc(UserLog.created_at)).limit(limit)
        result = await session.execute(stmt)
        logs = result.scalars().all()
        
        for log in logs:
            print(f"{log.id:<6} | {log.user_id:<10} | {log.operation_type[:20]:<20} | {log.credit_change:<6} | {log.current_balance:<8} | {log.created_at}")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(view_logs())
