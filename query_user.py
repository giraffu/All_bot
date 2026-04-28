import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

DATABASE_URL = "postgresql+asyncpg://postgres:postgrespassword@192.168.1.115:5432/bot_db"

async def main():
    engine = create_async_engine(DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # Get latest worker_logs
        logs = await session.execute(text("SELECT * FROM worker_logs ORDER BY start_time DESC LIMIT 5"))
        for log in logs.fetchall():
            print(dict(log._mapping))
            
asyncio.run(main())
