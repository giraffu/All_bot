import asyncio
from db import init_db, save_message
import json

async def main():
    await init_db()
    await save_message(
        chat_id=-1002607185647,
        message_id=1,
        user_id=123,
        username="Test User",
        message_type="text",
        content="Hello world",
        media_file_id="",
        raw_data={"test": "data"}
    )
    print("Test passed")

asyncio.run(main())
