import asyncio
import sys
from src.database.core import AsyncSessionLocal
from src.quota import QuotaManager

async def main():
    manager = QuotaManager()
    user_id = 10000000046617
    
    # Try calling process_channel_reward manually
    inviter_id = await manager.process_channel_reward(user_id)
    print(f"Result of process_channel_reward: {inviter_id}")

if __name__ == "__main__":
    asyncio.run(main())
