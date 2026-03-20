import asyncio
from sqlalchemy import select, func
from src.database.core import AsyncSessionLocal
from src.database.models import TemplateContribution

async def main():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(func.count(TemplateContribution.id)))
        count = result.scalar()
        print(f"Total rows: {count}")
        result = await session.execute(select(TemplateContribution.file_path).limit(5))
        paths = result.scalars().all()
        for p in paths:
            print(p)

if __name__ == "__main__":
    asyncio.run(main())
