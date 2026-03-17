import asyncio
import os
import logging
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from dotenv import load_dotenv

load_dotenv()

# Force postgres for test
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost/bot_db")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_db")

async def test_connection():
    logger.info(f"Testing connection to: {DATABASE_URL}")
    if DATABASE_URL.startswith("sqlite"):
        logger.error("❌ Error: DATABASE_URL is still pointing to SQLite!")
        return
        
    try:
        engine = create_async_engine(DATABASE_URL, echo=False)
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            val = result.scalar()
            if val == 1:
                logger.info("✅ PostgreSQL connection successful!")
            else:
                logger.error(f"❌ Unexpected result: {val}")
    except Exception as e:
        logger.error(f"❌ Connection failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_connection())
