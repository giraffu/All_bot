import asyncio
import sys
import os
from pathlib import Path
from sqlalchemy import text

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))

from src.database.core import engine

async def migrate():
    print("Starting migration: Add is_channel_member column to users table...")
    async with engine.begin() as conn:
        try:
            # Check if column exists
            # SQLite doesn't support IF NOT EXISTS for ADD COLUMN directly in standard SQL universally, 
            # but we can try to add it and catch the error if it exists.
            await conn.execute(text("ALTER TABLE users ADD COLUMN is_channel_member BOOLEAN DEFAULT 0"))
            print("Successfully added 'is_channel_member' column.")
        except Exception as e:
            if "duplicate column name" in str(e).lower():
                print("Column 'is_channel_member' already exists.")
            else:
                print(f"Error adding column: {e}")

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(migrate())
