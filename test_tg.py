import asyncio
from telegram import Bot
from config import BOT_TOKEN, REQUIRED_CHANNEL_ID

async def main():
    bot = Bot(token=BOT_TOKEN)
    channel_id = int(REQUIRED_CHANNEL_ID) if REQUIRED_CHANNEL_ID.lstrip('-').isdigit() else REQUIRED_CHANNEL_ID
    try:
        member = await bot.get_chat_member(chat_id=channel_id, user_id=5011247498)
        print(f"Status: {member.status}")
    except Exception as e:
        print(f"Error: {e}")

asyncio.run(main())
