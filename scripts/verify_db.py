import sys
import os
import asyncio
from sqlalchemy import select, func

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database.core import AsyncSessionLocal
from src.database.models import User, Referral

async def verify():
    async with AsyncSessionLocal() as session:
        # Count Users
        result = await session.execute(select(func.count(User.id)))
        user_count = result.scalar()
        print(f"Users: {user_count}")
        
        # Count Referrals
        result = await session.execute(select(func.count(Referral.id)))
        ref_count = result.scalar()
        print(f"Referrals: {ref_count}")
        
        # Show users with details
        print("\nUser Details:")
        stmt = select(User).order_by(User.created_at.desc())
        result = await session.execute(stmt)
        users = result.scalars().all()
        for user in users:
            name_display = f"{user.full_name or 'Unknown'}"
            if user.username:
                name_display += f" (@{user.username})"
            print(f"ID: {user.id} | Name: {name_display} | Credits: {user.credits} | Created: {user.created_at}")

if __name__ == "__main__":
    asyncio.run(verify())
