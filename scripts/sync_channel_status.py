import sys
import os
import asyncio
import logging
from pathlib import Path
from sqlalchemy import select, update
from telegram import Bot
from telegram.request import HTTPXRequest
from telegram.error import TelegramError

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))

# Import config first to ensure env vars are loaded
from config import BOT_TOKEN, BOT_TOKEN_TEST, REQUIRED_CHANNEL_ID, PROXY_URL
from src.database.core import init_db, AsyncSessionLocal
from src.database.models import Referral, User

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def sync_channel_status():
    # Use Test Bot Token as requested by user
    TOKEN_TO_USE = BOT_TOKEN_TEST
    
    if not TOKEN_TO_USE or not REQUIRED_CHANNEL_ID:
        logger.error(f"Config Error: BOT_TOKEN_TEST={bool(TOKEN_TO_USE)}, REQUIRED_CHANNEL_ID={REQUIRED_CHANNEL_ID}")
        return

    logger.info(f"Starting synchronization for Channel ID: {REQUIRED_CHANNEL_ID}")
    logger.info(f"Using Bot Token: {TOKEN_TO_USE[:5]}...{TOKEN_TO_USE[-5:]}")
    logger.info(f"Using Proxy Config: {PROXY_URL}")
    
    # Initialize Bot with Proxy
    try:
        # Try to use http protocol for proxy if it starts with socks5 but might support http (common in clash)
        # Or just use what is provided.
        
        proxy_url = PROXY_URL
        if proxy_url and proxy_url.startswith("socks5://"):
             # Fallback: Try http scheme which is natively supported by httpx
             proxy_url = proxy_url.replace("socks5://", "http://")
        
        logger.info(f"Attempting to connect with proxy: {proxy_url}")
        
        request = HTTPXRequest(proxy_url=proxy_url)
        bot = Bot(token=TOKEN_TO_USE, request=request)
        # Verify bot connection
        me = await bot.get_me()
        logger.info(f"Bot connected as @{me.username}")
    except Exception as e:
        logger.error(f"Failed to initialize Bot with proxy {proxy_url}: {e}")
        # Last resort: Try without proxy
        try:
            logger.info("Retrying without proxy...")
            bot = Bot(token=TOKEN_TO_USE)
            me = await bot.get_me()
            logger.info(f"Bot connected as @{me.username} (No Proxy)")
        except Exception as e2:
             logger.error(f"Failed to initialize Bot without proxy: {e2}")
             return
    
    # Initialize DB
    await init_db()
    
    async with AsyncSessionLocal() as session:
        # Get ALL users, not just referrals
        stmt = select(User)
        result = await session.execute(stmt)
        users = result.scalars().all()
        
        logger.info(f"Found {len(users)} users to check.")
        
        updated_count = 0
        
        for user in users:
            user_id = user.id
            try:
                # Check member status
                # ChatMember status: creator, administrator, member, restricted, left, kicked
                chat_member = await bot.get_chat_member(chat_id=REQUIRED_CHANNEL_ID, user_id=user_id)
                
                # Check if user is a member/admin/creator
                is_member = chat_member.status in ["creator", "administrator", "member"]
                
                # Update User table
                if user.is_channel_member != is_member:
                    user.is_channel_member = is_member
                    updated_count += 1
                    logger.info(f"User {user_id} status changed to {is_member}.")
                
                # Also update Referral table if applicable (for backward compatibility)
                if is_member:
                    # Check if there is a referral record for this user
                    ref_stmt = select(Referral).where(Referral.invitee_id == user_id)
                    ref_result = await session.execute(ref_stmt)
                    referral = ref_result.scalar_one_or_none()
                    
                    if referral and not referral.channel_reward_claimed:
                        referral.channel_reward_claimed = True
                        logger.info(f"User {user_id} referral reward marked claimed.")
                
                # Rate limiting
                await asyncio.sleep(0.05)
                
            except TelegramError as e:
                # Common errors: User not found, Chat not found, Bot was blocked by the user
                logger.warning(f"Telegram API Error for user {user_id}: {e}")
                # If user not found (e.g. deleted account), maybe set is_channel_member to False?
                # Let's keep it as is or set to False if we are sure.
                # For safety, we only update if we get a valid response.
                pass
            except Exception as e:
                logger.error(f"Unexpected error for user {user_id}: {e}")
                
        if updated_count > 0:
            await session.commit()
            logger.info(f"Successfully updated {updated_count} user records.")
        else:
            logger.info("No records needed updating.")

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(sync_channel_status())
