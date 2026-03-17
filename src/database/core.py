import os
import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from .models import Base
from config import DATABASE_URL
# from .logger import setup_db_logging

logger = logging.getLogger(__name__)

# Engine configuration
engine = create_async_engine(
    DATABASE_URL, 
    echo=False,
    pool_pre_ping=True,  # Useful for Postgres to detect disconnects
)

# Setup DB Logging (Disabled)
# setup_db_logging(engine)

AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
        # Migrations (idempotent checks)
        # Note: In a real production env, use Alembic. 
        # Here we do simple column checks for backward compatibility during dev.
        try:
            # Check if user_group column exists
            await conn.execute(text("SELECT user_group FROM users LIMIT 1"))
        except Exception:
            try:
                logger.info("Adding user_group column to users table")
                await conn.execute(text("ALTER TABLE users ADD COLUMN user_group VARCHAR(20) DEFAULT '游客'"))
            except Exception as e:
                logger.warning(f"Failed to add user_group column: {e}")
        
        try:
            # Check if total_contributions column exists
            await conn.execute(text("SELECT total_contributions FROM users LIMIT 1"))
        except Exception:
            try:
                logger.info("Adding contribution columns to users table")
                await conn.execute(text("ALTER TABLE users ADD COLUMN total_contributions INTEGER DEFAULT 0"))
                await conn.execute(text("ALTER TABLE users ADD COLUMN approved_contributions INTEGER DEFAULT 0"))
            except Exception as e:
                logger.warning(f"Failed to add contribution columns: {e}")

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
