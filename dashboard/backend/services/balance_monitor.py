import asyncio
import logging
import os

import httpx
from telegram import Bot

from src.services.redis_client import redis_client

logger = logging.getLogger("dashboard.balance_monitor")


def _decode_redis_value(value):
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return value


def _build_bot(bot_token: str | None, proxy_url: str | None):
    if not bot_token:
        return None

    if proxy_url:
        from telegram.request import HTTPXRequest

        request = HTTPXRequest(proxy=proxy_url)
        return Bot(token=bot_token, request=request)
    return Bot(token=bot_token)


def _configured_proxy_url() -> str | None:
    """Return an explicitly configured proxy without inventing a local default."""
    return os.getenv("PROXY_URL") or None


async def _fetch_ton_balances(client: httpx.AsyncClient, ton_address: str | None) -> tuple[float, float]:
    if not ton_address:
        return 0.0, 0.0

    ton_balance = 0.0
    usdt_balance = 0.0
    try:
        resp = await client.get(
            f"https://toncenter.com/api/v2/getAddressBalance?address={ton_address}"
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("ok"):
                ton_balance = round(float(data.get("result", 0)) / 1e9, 2)

        resp_jettons = await client.get(f"https://tonapi.io/v2/accounts/{ton_address}/jettons")
        if resp_jettons.status_code == 200:
            data = resp_jettons.json()
            balances = data.get("balances", [])
            for balance in balances:
                jetton = balance.get("jetton", {})
                symbol = jetton.get("symbol", "")
                if symbol in ["USDT", "USD₮"]:
                    decimals = jetton.get("decimals", 6)
                    balance_str = balance.get("balance", "0")
                    usdt_balance = round(float(balance_str) / (10**decimals), 2)
                    break
    except Exception as e:
        logger.error(f"Error fetching TON/USDT balance: {e}")

    return ton_balance, usdt_balance


async def _load_star_cursor_and_balance() -> tuple[str | None, int]:
    if not redis_client or not redis_client.redis:
        return None, 0

    last_tx_id = _decode_redis_value(
        await redis_client.redis.get("dashboard:last_star_tx_id")
    )
    cached_balance = _decode_redis_value(
        await redis_client.redis.get("dashboard:star_balance")
    )
    return (
        str(last_tx_id) if last_tx_id else None,
        int(cached_balance) if cached_balance else 0,
    )


async def _fetch_star_balance(bot) -> int | None:
    if not bot:
        return None

    try:
        last_tx_id, star_balance = await _load_star_cursor_and_balance()
        offset = 0
        limit = 100
        new_stars_added = 0
        found_last = False
        first_tx_id_in_batch = None

        while True:
            response = await bot.get_star_transactions(
                limit=limit,
                offset=offset,
                read_timeout=30,
                connect_timeout=30,
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

        if first_tx_id_in_batch:
            star_balance += new_stars_added
            if redis_client and redis_client.redis:
                await redis_client.redis.set(
                    "dashboard:last_star_tx_id",
                    str(first_tx_id_in_batch),
                )
        return star_balance
    except Exception as e:
        logger.error(f"Error fetching Stars balance: {e}")
        return None


async def _cache_external_balances(
    *,
    ton_balance: float,
    usdt_balance: float,
    star_balance: int | None,
) -> None:
    if not redis_client or not redis_client.redis:
        return

    await redis_client.redis.set("dashboard:ton_balance", str(ton_balance))
    await redis_client.redis.set("dashboard:usdt_balance", str(usdt_balance))
    if star_balance is not None:
        await redis_client.redis.set("dashboard:star_balance", str(star_balance))


async def _update_external_balances_once(
    *,
    client: httpx.AsyncClient,
    bot,
    ton_address: str | None,
) -> None:
    ton_balance, usdt_balance = await _fetch_ton_balances(client, ton_address)
    star_balance = await _fetch_star_balance(bot)
    await _cache_external_balances(
        ton_balance=ton_balance,
        usdt_balance=usdt_balance,
        star_balance=star_balance,
    )


async def update_external_balances():
    ton_address = os.getenv("VITE_MERCHANT_ADDRESS")
    bot_token = os.getenv("BOT_TOKEN")
    proxy_url = _configured_proxy_url()
    bot = _build_bot(bot_token, proxy_url)

    async with httpx.AsyncClient() as client:
        while True:
            try:
                await _update_external_balances_once(
                    client=client,
                    bot=bot,
                    ton_address=ton_address,
                )
            except Exception as e:
                logger.error(f"Error in external balance monitor loop: {e}")

            await asyncio.sleep(300)
