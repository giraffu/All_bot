import asyncio
from sqlalchemy import select, desc
from src.database.core import AsyncSessionLocal
from src.database.models import TemplateContribution
from dotenv import load_dotenv
load_dotenv()

async def main():
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(TemplateContribution)
            .order_by(desc(TemplateContribution.id))
            .limit(10)
        )
        contributions = result.scalars().all()
        for c in contributions:
            print(f"ID: {c.id}")
            print(f"File Path: {c.file_path}")
            print(f"Created At: {c.created_at}")
            print("-" * 40)

if __name__ == "__main__":
    asyncio.run(main())
