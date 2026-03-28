import asyncio
from sqlalchemy import text
from src.database.core import AsyncSessionLocal

async def migrate():
    async with AsyncSessionLocal() as session:
        try:
            await session.execute(text("ALTER TABLE history ADD COLUMN is_public BOOLEAN DEFAULT FALSE;"))
            print("Added is_public")
        except Exception as e:
            print(f"Error adding is_public: {e}")
        try:
            await session.execute(text("ALTER TABLE history ADD COLUMN rating INTEGER DEFAULT 0;"))
            print("Added rating")
        except Exception as e:
            print(f"Error adding rating: {e}")
        await session.commit()

if __name__ == "__main__":
    asyncio.run(migrate())
