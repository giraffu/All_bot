import sys
import os
import json
import asyncio
from datetime import datetime

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database.core import init_db, AsyncSessionLocal
from src.database.models import User, Permission, Referral
from sqlalchemy.future import select

async def migrate():
    print("Initializing database...")
    await init_db()

    async with AsyncSessionLocal() as session:
        # 1. Migrate Permissions
        if os.path.exists("permissions.json"):
            print("Migrating permissions.json...")
            with open("permissions.json", "r", encoding="utf-8") as f:
                perm_data = json.load(f)
                
                # Users
                for uid in perm_data.get("users", []):
                    # Check if exists
                    stmt = select(Permission).where(Permission.entity_id == uid, Permission.type == 'whitelist_user')
                    result = await session.execute(stmt)
                    if not result.scalar_one_or_none():
                        session.add(Permission(entity_id=uid, type='whitelist_user'))
                
                # Groups
                for gid in perm_data.get("groups", []):
                    stmt = select(Permission).where(Permission.entity_id == gid, Permission.type == 'whitelist_group')
                    result = await session.execute(stmt)
                    if not result.scalar_one_or_none():
                        session.add(Permission(entity_id=gid, type='whitelist_group'))
            
            await session.commit()
            print("Permissions migrated.")

        # 2. Migrate Quota (Users & Referrals)
        if os.path.exists("quota.json"):
            print("Migrating quota.json...")
            with open("quota.json", "r", encoding="utf-8") as f:
                quota_data = json.load(f)
                
                credits_data = quota_data.get("credits", {})
                checkin_data = quota_data.get("last_checkin", {})
                referrals_data = quota_data.get("referrals", {})

                # Collect all unique user IDs
                all_user_ids = set()
                all_user_ids.update(map(int, credits_data.keys()))
                all_user_ids.update(map(int, checkin_data.keys()))
                all_user_ids.update(map(int, referrals_data.keys())) # Inviters
                for invitees in referrals_data.values():
                    all_user_ids.update(map(int, invitees)) # Invitees

                # Create/Update Users
                for uid in all_user_ids:
                    stmt = select(User).where(User.id == uid)
                    result = await session.execute(stmt)
                    user = result.scalar_one_or_none()
                    
                    if not user:
                        user = User(id=uid)
                        session.add(user)
                    
                    # Update credits
                    if str(uid) in credits_data:
                        user.credits = credits_data[str(uid)]
                    
                    # Update checkin
                    if str(uid) in checkin_data:
                        try:
                            date_str = checkin_data[str(uid)]
                            user.last_checkin = datetime.strptime(date_str, "%Y-%m-%d").date()
                        except ValueError:
                            print(f"Invalid date for user {uid}: {checkin_data[str(uid)]}")

                await session.commit()
                print(f"Synced {len(all_user_ids)} users.")

                # Create Referrals
                count = 0
                for inviter_id_str, invitees in referrals_data.items():
                    inviter_id = int(inviter_id_str)
                    for invitee_id_str in invitees:
                        invitee_id = int(invitee_id_str)
                        
                        # Check if referral exists
                        stmt = select(Referral).where(Referral.invitee_id == invitee_id)
                        result = await session.execute(stmt)
                        if not result.scalar_one_or_none():
                            ref = Referral(inviter_id=inviter_id, invitee_id=invitee_id)
                            session.add(ref)
                            count += 1
                
                await session.commit()
                print(f"Migrated {count} referrals.")

    print("Migration complete!")

if __name__ == "__main__":
    asyncio.run(migrate())
