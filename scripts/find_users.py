import asyncio
import logging
from sqlalchemy import text
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.database.core import AsyncSessionLocal

async def find_users():
    async with AsyncSessionLocal() as session:
        result1 = await session.execute(text("SELECT id, user_group, current_identity, identity_expire_at, is_channel_member, invited_by FROM users WHERE id = 10000000003824;"))
        print("Robin Green info:", result1.fetchall())
        
if __name__ == "__main__":
    asyncio.run(find_users())
