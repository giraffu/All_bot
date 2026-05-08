import asyncio
import sys
from src.database.core import AsyncSessionLocal
from src.database.models import User, Referral, UserLog
from sqlalchemy import select

async def main():
    async with AsyncSessionLocal() as session:
        # Find Nah Man (invitee)
        stmt = select(User).where(User.username == "n/a", User.id == 10000000046617)
        result = await session.execute(stmt)
        invitee = result.scalar_one_or_none()
        
        # Or maybe ID is 10000000046617
        stmt = select(User).where(User.id == 10000000046617)
        result = await session.execute(stmt)
        invitee = result.scalar_one_or_none()
        
        if invitee:
            print(f"Invitee: {invitee.id}, name: {invitee.full_name}, is_channel_member: {invitee.is_channel_member}")
            
            stmt = select(Referral).where(Referral.invitee_id == invitee.id)
            result = await session.execute(stmt)
            referral = result.scalar_one_or_none()
            if referral:
                print(f"Referral found: inviter_id={referral.inviter_id}, channel_reward_claimed={referral.channel_reward_claimed}")
            else:
                print("Referral not found!")
                
            # check logs
            stmt = select(UserLog).where(UserLog.user_id == referral.inviter_id if referral else 0)
            result = await session.execute(stmt)
            logs = result.scalars().all()
            print("Inviter logs:")
            for log in logs:
                print(f"  {log.operation_type}, {log.credit_change}, {log.created_at}")

        else:
            print("Invitee not found")

if __name__ == "__main__":
    asyncio.run(main())
