import sys
import os
import asyncio
from pathlib import Path
from sqlalchemy import select, func

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.append(str(PROJECT_ROOT))

# Fix imports
from src.database.core import init_db, AsyncSessionLocal
from src.database.models import Referral, User

async def check_data():
    await init_db()
    async with AsyncSessionLocal() as session:
        # Count total referrals
        result = await session.execute(select(func.count(Referral.id)))
        total_referrals = result.scalar()
        
        # Count claimed rewards
        result = await session.execute(select(func.count(Referral.id)).where(Referral.channel_reward_claimed == True))
        claimed_rewards = result.scalar()
        
        print(f"Total Referrals: {total_referrals}")
        print(f"Claimed Channel Rewards: {claimed_rewards}")
        
        # Check specific examples
        stmt = select(Referral).where(Referral.channel_reward_claimed == True).limit(5)
        result = await session.execute(stmt)
        examples = result.scalars().all()
        
        if examples:
            print("Examples of claimed rewards (Referral ID, Invitee ID):")
            for ref in examples:
                print(f"- Ref ID: {ref.id}, Invitee ID: {ref.invitee_id}")
        else:
            print("No claimed rewards found.")

if __name__ == "__main__":
    asyncio.run(check_data())
