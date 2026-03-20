import asyncio
from sqlalchemy import select, func
from src.database.core import AsyncSessionLocal
from src.database.models import TemplateContribution
from dotenv import load_dotenv
import os

load_dotenv()

async def main():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(TemplateContribution))
        contributions = result.scalars().all()
        
        print("Recent 5 in DB:")
        for c in sorted(contributions, key=lambda x: x.id, reverse=True)[:5]:
            print(f"ID: {c.id}, file_path: {c.file_path}, reviewed: {c.is_reviewed}")
        
if __name__ == "__main__":
    asyncio.run(main())
