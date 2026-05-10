import logging
import time
import httpx

logger = logging.getLogger("utils.exchange_rates")

_exchange_rates_cache = {
    "rates": {"ton_to_usdt": 5.0, "rmb_to_usdt": 0.14, "stars_to_usdt": 0.013},
    "last_fetched": 0,
}


async def get_exchange_rates() -> dict:
    """Get current exchange rates to USDT with 1-hour caching"""
    now = time.time()
    if now - _exchange_rates_cache["last_fetched"] < 3600:  # cache for 1 hour
        return _exchange_rates_cache["rates"]

    rates = _exchange_rates_cache["rates"].copy()
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # TON to USDT
            resp1 = await client.get(
                "https://tonapi.io/v2/rates?tokens=ton&currencies=usd"
            )
            if resp1.status_code == 200:
                data = resp1.json()
                if "rates" in data and "TON" in data["rates"]:
                    rates["ton_to_usdt"] = float(data["rates"]["TON"]["prices"]["USD"])

            # RMB to USDT
            resp2 = await client.get("https://api.exchangerate-api.com/v4/latest/USD")
            if resp2.status_code == 200:
                data = resp2.json()
                if "rates" in data and "CNY" in data["rates"]:
                    cny_rate = float(data["rates"]["CNY"])
                    rates["rmb_to_usdt"] = 1.0 / cny_rate

        _exchange_rates_cache["rates"] = rates
        _exchange_rates_cache["last_fetched"] = now
    except Exception as e:
        logger.error(f"Error fetching exchange rates: {e}")

    return rates
