import sys
import os
from pathlib import Path
import asyncio
from sqlalchemy import select, func, text

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))

# Change working directory to project root
os.chdir(str(PROJECT_ROOT))

from src.database.core import get_db, init_db, AsyncSessionLocal
from src.database.models import User, History, Referral, CheckinHistory

async def migrate():
    print("Starting migration of user stats...")
    
    # 1. Add columns if they don't exist
    async with AsyncSessionLocal() as session:
        print("Checking/Adding columns...")
        # Check if columns exist
        try:
            # Try to select the new columns
            await session.execute(text("SELECT referral_count, generation_count, checkin_count, last_activity FROM users LIMIT 1"))
            print("Columns already exist.")
        except Exception:
            print("Columns missing. Adding them...")
            # SQLite doesn't support multiple ADD COLUMN in one statement easily, so do one by one
            try:
                await session.execute(text("ALTER TABLE users ADD COLUMN referral_count INTEGER DEFAULT 0"))
            except Exception as e:
                print(f"Error adding referral_count (might exist): {e}")
                
            try:
                await session.execute(text("ALTER TABLE users ADD COLUMN generation_count INTEGER DEFAULT 0"))
            except Exception as e:
                print(f"Error adding generation_count (might exist): {e}")
                
            try:
                await session.execute(text("ALTER TABLE users ADD COLUMN checkin_count INTEGER DEFAULT 0"))
            except Exception as e:
                print(f"Error adding checkin_count (might exist): {e}")
                
            try:
                await session.execute(text("ALTER TABLE users ADD COLUMN last_activity DATETIME"))
            except Exception as e:
                print(f"Error adding last_activity (might exist): {e}")
            
            await session.commit()
            print("Columns added.")

    # 2. Populate data
    async with AsyncSessionLocal() as session:
        print("Populating data...")
        
        # Get all users
        result = await session.execute(select(User))
        users = result.scalars().all()
        total_users = len(users)
        print(f"Found {total_users} users. Processing...")
        
        count = 0
        for user in users:
            # 1. Referral Count
            ref_stmt = select(func.count(Referral.id)).where(Referral.inviter_id == user.id)
            ref_res = await session.execute(ref_stmt)
            user.referral_count = ref_res.scalar() or 0
            
            # 2. Generation Count
            gen_stmt = select(func.count(History.id)).where(History.user_id == user.id)
            gen_res = await session.execute(gen_stmt)
            user.generation_count = gen_res.scalar() or 0
            
            # 3. Checkin Count
            chk_stmt = select(func.count(CheckinHistory.id)).where(CheckinHistory.user_id == user.id)
            chk_res = await session.execute(chk_stmt)
            user.checkin_count = chk_res.scalar() or 0
            
            # 4. Last Activity
            act_stmt = select(func.max(History.created_at)).where(History.user_id == user.id)
            act_res = await session.execute(act_stmt)
            user.last_activity = act_res.scalar()
            
            count += 1
            if count % 100 == 0:
                print(f"Processed {count}/{total_users} users...")
        
        await session.commit()
        print("Migration completed successfully!")

if __name__ == "__main__":
    asyncio.run(migrate())
