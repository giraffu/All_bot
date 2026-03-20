import asyncio
from sqlalchemy import select, func
from src.database.core import AsyncSessionLocal
from src.database.models import TemplateContribution
from dotenv import load_dotenv

load_dotenv()

async def main():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(func.count(TemplateContribution.id)))
        count = result.scalar()
        print(f"Total rows in TemplateContribution: {count}")

if __name__ == "__main__":
    asyncio.run(main())
