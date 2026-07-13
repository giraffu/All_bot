async def get_exchange_rates() -> dict:
    """Get fixed exchange rates to USDT"""
    return {
        "ton_to_usdt": 1.4,
        "rmb_to_usdt": 1.0 / 6.7,
        "stars_to_usdt": 0.013
    }
