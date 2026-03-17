import asyncio
import logging
from telegram import Bot
from telegram.request import HTTPXRequest
from config import BOT_TOKEN, REQUIRED_CHANNEL_ID, PROXY_URL

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def check_chat():
    # Force use of local proxy if available, similar to bot_test.py logic
    proxy = "socks5://127.0.0.1:7890"
    logger.info(f"Using Proxy: {proxy}")
    
    request = HTTPXRequest(proxy=proxy, connect_timeout=30, read_timeout=30) 
    bot = Bot(token=BOT_TOKEN, request=request)
    
    logger.info(f"Checking Chat ID: {REQUIRED_CHANNEL_ID}")
    try:
        # Check bot's own member status
        me = await bot.get_me()
        logger.info(f"Bot Info: {me.username} ({me.id})")
        
        chat = await bot.get_chat(chat_id=REQUIRED_CHANNEL_ID)
        logger.info(f"Chat found: {chat.title} ({chat.type})")
        
        member = await bot.get_chat_member(chat_id=REQUIRED_CHANNEL_ID, user_id=me.id)
        logger.info(f"Bot status in chat: {member.status}")
        
    except Exception as e:
        logger.error(f"Error checking chat: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(check_chat())
