import asyncio
import os
from telegram import Bot
from dotenv import load_dotenv

load_dotenv()
token = os.getenv("BOT_TOKEN")

async def calculate_total():
    if not token:
        print("Error: BOT_TOKEN not found in environment.")
        return
        
    bot = Bot(token=token)
    try:
        print("Fetching all Star transactions...")
        total_revenue = 0
        total_transactions = 0
        offset = 0
        limit = 100
        
        while True:
            response = await bot.get_star_transactions(limit=limit, offset=offset)
            transactions = response.transactions
            
            if not transactions:
                break
                
            for tx in transactions:
                # print(f"Tx amount: {tx.amount}")
                if tx.amount > 0:
                    total_revenue += tx.amount
                    total_transactions += 1
            
            offset += len(transactions)
            print(f"Fetched {offset} records so far...")
            
        print("="*50)
        print(f"Total Successful Payments: {total_transactions}")
        print(f"Total Stars Revenue: {total_revenue} Stars")
        print("="*50)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(calculate_total())
