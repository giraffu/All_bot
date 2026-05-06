import asyncio
from telegram import Bot
from config import BOT_TOKEN

async def main():
    bot = Bot(token=BOT_TOKEN)
    try:
        chat = await bot.get_chat(chat_id="@AiVisionAV")
        print(f"Chat ID: {chat.id}")
    except Exception as e:
        print(f"Error: {e}")

asyncio.run(main())
