import httpx
import asyncio

async def fetch_exchange_rates():
    rates = {
        "ton_to_usdt": 5.0,
        "rmb_to_usdt": 0.14,
        "stars_to_usdt": 0.013
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp1 = await client.get("https://api.binance.com/api/v3/ticker/price?symbol=TONUSDT")
            if resp1.status_code == 200:
                rates["ton_to_usdt"] = float(resp1.json()["price"])
                
            resp2 = await client.get("https://api.exchangerate-api.com/v4/latest/USD")
            if resp2.status_code == 200:
                cny_rate = float(resp2.json()["rates"]["CNY"])
                rates["rmb_to_usdt"] = 1.0 / cny_rate
    except Exception as e:
        print(f"Error fetching rates: {e}")
        
    return rates

print(asyncio.run(fetch_exchange_rates()))
