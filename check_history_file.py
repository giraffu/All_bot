import asyncio
from src.database.core import AsyncSessionLocal
from src.database.models import History
from sqlalchemy import select, func

async def main():
    target_file = "%0aecb8ed-cfce-4a99-8aac-12906420bf51%"
    async with AsyncSessionLocal() as session:
        stmt = select(History).where(History.output_file.like(target_file))
        result = await session.execute(stmt)
        record = result.scalar_one_or_none()
        
        if record:
            print(f"Found record: ID={record.id}, User={record.user_id}, TaskID={record.task_id}, Output={record.output_file}")
        else:
            print("Record not found.")

if __name__ == "__main__":
    asyncio.run(main())
