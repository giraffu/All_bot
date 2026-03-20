from dotenv import load_dotenv
load_dotenv()
import asyncio
from sqlalchemy import select
from src.database.core import AsyncSessionLocal
from src.database.models import TemplateContribution
import os

async def main():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(TemplateContribution).limit(10))
        contributions = result.scalars().all()
        for c in contributions:
            print(f"ID: {c.id}, is_reviewed: {c.is_reviewed}")

if __name__ == "__main__":
    asyncio.run(main())
