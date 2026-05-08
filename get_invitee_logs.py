import asyncio
from src.database.core import AsyncSessionLocal
from src.database.models import UserLog
from sqlalchemy import select

async def main():
    async with AsyncSessionLocal() as session:
        stmt = select(UserLog).where(UserLog.user_id == 10000000046617).order_by(UserLog.created_at)
        result = await session.execute(stmt)
        logs = result.scalars().all()
        for log in logs:
            print(f"{log.operation_type}, {log.credit_change}, {log.created_at}")

if __name__ == "__main__":
    asyncio.run(main())
