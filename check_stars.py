import asyncio
from telegram import Bot
import os
from dotenv import load_dotenv

load_dotenv()
token = os.getenv("BOT_TOKEN")

async def check():
    if not token:
        print("Error: BOT_TOKEN not found in environment.")
        return
        
    bot = Bot(token=token)
    try:
        print("Fetching more Star transactions...")
        transactions = await bot.get_star_transactions(limit=10, offset=5)
        
        if not transactions.transactions:
            print("No more Star transactions found.")
            return
            
        for tx in transactions.transactions:
            date_str = tx.date.strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{date_str}] Amount: {tx.amount} Stars, ID: {tx.id}")
            print(f"  --> Details: {tx.to_dict()}")
            print("-" * 50)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(check())
