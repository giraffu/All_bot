import asyncio
import logging
from sqlalchemy import text
import sys
import os

# Add the project root to sys.path to allow imports from src
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.database.core import AsyncSessionLocal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def merge_users():
    source_id = 6708830818
    target_id = 10000000055300
    
    async with AsyncSessionLocal() as session:
        try:
            logger.info(f"Starting to merge user {source_id} into {target_id}")
            
            # 1. Update core assets and attributes
            logger.info("Merging core attributes...")
            await session.execute(text(f"""
                UPDATE users 
                SET 
                    credits = credits + COALESCE((SELECT credits FROM users WHERE id = {source_id}), 0),
                    checkin_count = checkin_count + COALESCE((SELECT checkin_count FROM users WHERE id = {source_id}), 0),
                    referral_count = referral_count + COALESCE((SELECT referral_count FROM users WHERE id = {source_id}), 0),
                    generation_count = generation_count + COALESCE((SELECT generation_count FROM users WHERE id = {source_id}), 0),
                    total_contributions = total_contributions + COALESCE((SELECT total_contributions FROM users WHERE id = {source_id}), 0),
                    approved_contributions = approved_contributions + COALESCE((SELECT approved_contributions FROM users WHERE id = {source_id}), 0),
                    
                    user_group = '金丹期',
                    current_identity = '真传弟子',
                    identity_expire_at = '2026-06-15 15:29:38',
                    is_channel_member = TRUE,
                    
                    invited_by = (SELECT invited_by FROM users WHERE id = {source_id})
                WHERE id = {target_id};
            """))

            # 2. Update non-conflicting foreign keys
            logger.info("Updating non-conflicting foreign keys...")
            tables = [
                ('history', 'user_id'),
                ('checkin_history', 'user_id'),
                ('user_logs', 'user_id'),
                ('gallery_posts', 'user_id'),
                ('template_contributions', 'user_id'),
                ('orders', 'telegram_id')
            ]
            for table, fk_col in tables:
                await session.execute(text(f"UPDATE {table} SET {fk_col} = {target_id} WHERE {fk_col} = {source_id};"))

            # 3. Update referrals
            logger.info("Updating referrals...")
            await session.execute(text(f"UPDATE referrals SET inviter_id = {target_id} WHERE inviter_id = {source_id};"))
            await session.execute(text(f"UPDATE referrals SET invitee_id = {target_id} WHERE invitee_id = {source_id};"))

            # 4. Update user_interactions with duplicate deletion
            logger.info("Updating user interactions (handling duplicates)...")
            await session.execute(text(f"""
                DELETE FROM user_interactions 
                WHERE user_id = {source_id} 
                  AND (post_id, action_type) IN (
                      SELECT post_id, action_type FROM user_interactions WHERE user_id = {target_id}
                  );
            """))
            await session.execute(text(f"UPDATE user_interactions SET user_id = {target_id} WHERE user_id = {source_id};"))

            # 5. Soft delete / merge source user
            logger.info("Archiving source user...")
            await session.execute(text(f"""
                UPDATE users 
                SET 
                    telegram_id = NULL,
                    google_id = NULL,
                    email = NULL,
                    username = username || '_merged_to_{target_id}',
                    credits = 0,
                    checkin_count = 0,
                    referral_count = 0,
                    generation_count = 0
                WHERE id = {source_id};
            """))

            await session.commit()
            logger.info(f"Successfully merged user {source_id} into {target_id}.")

        except Exception as e:
            await session.rollback()
            logger.error(f"Error during merge, transaction rolled back: {e}")
            raise

if __name__ == "__main__":
    asyncio.run(merge_users())
