import asyncio
import logging
from telegram import Bot
from telegram.request import HTTPXRequest
from config import BOT_TOKEN, REQUIRED_CHANNEL_ID, PROXY_URL

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def check_chat():
    # Rely on environment variables for proxy
    request = HTTPXRequest() 
    bot = Bot(token=BOT_TOKEN, request=request)
    
    logger.info(f"Checking Chat ID: {REQUIRED_CHANNEL_ID}")
    try:
        chat = await bot.get_chat(chat_id=REQUIRED_CHANNEL_ID)
        logger.info(f"Chat found: {chat.title} ({chat.type})")
        
        # Check bot's own member status
        me = await bot.get_me()
        member = await bot.get_chat_member(chat_id=REQUIRED_CHANNEL_ID, user_id=me.id)
        logger.info(f"Bot status in chat: {member.status}")
        
    except Exception as e:
        logger.error(f"Error checking chat: {e}")

if __name__ == "__main__":
    asyncio.run(check_chat())
