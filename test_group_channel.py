import asyncio
from telegram import Bot
from config import BOT_TOKEN, REQUIRED_CHANNEL_ID, REFUGE_GROUP_ID

async def main():
    bot = Bot(token=BOT_TOKEN)
    user_id = 5011247498
    
    channel_id = int(REQUIRED_CHANNEL_ID) if REQUIRED_CHANNEL_ID.lstrip('-').isdigit() else REQUIRED_CHANNEL_ID
    group_id = int(REFUGE_GROUP_ID) if REFUGE_GROUP_ID.lstrip('-').isdigit() else REFUGE_GROUP_ID

    try:
        member_c = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        print(f"Channel ({channel_id}) Status: {member_c.status}")
    except Exception as e:
        print(f"Channel Error: {e}")

    try:
        member_g = await bot.get_chat_member(chat_id=group_id, user_id=user_id)
        print(f"Group ({group_id}) Status: {member_g.status}")
    except Exception as e:
        print(f"Group Error: {e}")

asyncio.run(main())
