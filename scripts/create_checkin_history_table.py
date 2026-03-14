import asyncio
import sys
from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))

from src.database.core import DB_PATH

async def create_table():
    print(f"Connecting to {DB_PATH}")
    engine = create_async_engine(DB_PATH, echo=True)
    
    async with engine.begin() as conn:
        print("Creating checkin_history table...")
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS checkin_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id BIGINT,
                checkin_date DATE DEFAULT CURRENT_DATE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        """))
        
        print("Creating index on checkin_history(user_id)...")
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_checkin_history_user_id ON checkin_history (user_id)
        """))
        
    print("Done!")

if __name__ == "__main__":
    asyncio.run(create_table())
