import asyncio
import logging
import os
import httpx
from telegram import Bot
from src.services.redis_client import redis_client

logger = logging.getLogger("dashboard.balance_monitor")

async def update_external_balances():
    ton_address = os.getenv("VITE_MERCHANT_ADDRESS")
    bot_token = os.getenv("BOT_TOKEN")
    proxy_url = os.getenv("PROXY_URL", "http://127.0.0.1:7890")
    
    bot = None
    if bot_token:
        if proxy_url:
            from telegram.request import HTTPXRequest
            request = HTTPXRequest(proxy=proxy_url)
            bot = Bot(token=bot_token, request=request)
        else:
            bot = Bot(token=bot_token)

    # Use a single httpx client for the lifetime of the background task
    async with httpx.AsyncClient() as client:
        while True:
            try:
                ton_balance = 0.0
                usdt_balance = 0.0
                
                try:
                    if ton_address:
                        resp = await client.get(
                            f"https://toncenter.com/api/v2/getAddressBalance?address={ton_address}"
                        )
                        if resp.status_code == 200:
                            data = resp.json()
                            if data.get("ok"):
                                ton_balance = round(float(data.get("result", 0)) / 1e9, 2)

                        # Fetch USDT balance
                        resp_jettons = await client.get(
                            f"https://tonapi.io/v2/accounts/{ton_address}/jettons"
                        )
                        if resp_jettons.status_code == 200:
                            data = resp_jettons.json()
                            balances = data.get("balances", [])
                            for b in balances:
                                jetton = b.get("jetton", {})
                                symbol = jetton.get("symbol", "")
                                if symbol in ["USDT", "USD₮"]:
                                    decimals = jetton.get("decimals", 6)
                                    balance_str = b.get("balance", "0")
                                    usdt_balance = round(
                                        float(balance_str) / (10**decimals), 2
                                    )
                                    break
                except Exception as e:
                    logger.error(f"Error fetching TON/USDT balance: {e}")

                try:
                    if bot:
                        # Incremental Stars pulling
                        last_tx_id = None
                        star_balance = 0
                        
                        if redis_client and redis_client.redis:
                            last_tx_id = await redis_client.redis.get("dashboard:last_star_tx_id")
                            if last_tx_id:
                                last_tx_id = last_tx_id.decode("utf-8") if isinstance(last_tx_id, bytes) else str(last_tx_id)
                            
                            cached_balance = await redis_client.redis.get("dashboard:star_balance")
                            if cached_balance:
                                star_balance = int(cached_balance)

                        offset = 0
                        limit = 100
                        new_stars_added = 0
                        found_last = False
                        first_tx_id_in_batch = None

                        while True:
                            response = await bot.get_star_transactions(
                                limit=limit, offset=offset, read_timeout=30, connect_timeout=30
                            )
                            transactions = response.transactions
                            if not transactions:
                                break

                            for tx in transactions:
                                if not first_tx_id_in_batch:
                                    first_tx_id_in_batch = tx.id
                                    
                                if last_tx_id and str(tx.id) == last_tx_id:
                                    found_last = True
                                    break
                                    
                                if tx.amount > 0:
                                    new_stars_added += tx.amount

                            if found_last or len(transactions) < limit:
                                break
                                
                            offset += len(transactions)
                            
                        # Update balance and last tx id
                        if first_tx_id_in_batch:
                            star_balance += new_stars_added
                            if redis_client and redis_client.redis:
                                await redis_client.redis.set("dashboard:last_star_tx_id", str(first_tx_id_in_batch))

                except Exception as e:
                    logger.error(f"Error fetching Stars balance: {e}")

                if redis_client and redis_client.redis:
                    await redis_client.redis.set("dashboard:ton_balance", str(ton_balance))
                    await redis_client.redis.set("dashboard:usdt_balance", str(usdt_balance))
                    # star_balance is already updated and cached if successful
                    if 'star_balance' in locals() and bot:
                        await redis_client.redis.set("dashboard:star_balance", str(star_balance))

            except Exception as e:
                logger.error(f"Error in external balance monitor loop: {e}")
                
            await asyncio.sleep(300)  # 5 minutes
