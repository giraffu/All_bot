import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from .models import Base

# Database path
DB_PATH = "sqlite+aiosqlite:///bot_data.db"

engine = create_async_engine(
    DB_PATH, 
    echo=False,
    connect_args={"timeout": 30}  # Increase timeout to reduce "database is locked" errors
)

AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

async def init_db():
    async with engine.begin() as conn:
        # Enable WAL mode for better concurrency
        await conn.execute(text("PRAGMA journal_mode=WAL;"))
        # Set synchronous to NORMAL for better performance with WAL
        await conn.execute(text("PRAGMA synchronous=NORMAL;"))
        
        await conn.run_sync(Base.metadata.create_all)
        # Manually add user_group column if it doesn't exist
        try:
            await conn.execute(text("ALTER TABLE users ADD COLUMN user_group VARCHAR(20) DEFAULT '游客'"))
        except Exception:
            pass
        
        # Add contribution tracking columns
        try:
            await conn.execute(text("ALTER TABLE users ADD COLUMN total_contributions INTEGER DEFAULT 0"))
        except Exception:
            pass
            
        try:
            await conn.execute(text("ALTER TABLE users ADD COLUMN approved_contributions INTEGER DEFAULT 0"))
        except Exception:
            pass

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
