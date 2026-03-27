import asyncio
from src.database.core import init_db

async def main():
    await init_db()
    print("DB initialized")

asyncio.run(main())
