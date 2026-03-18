from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    CallbackQueryHandler,
    filters,
)
from telegram.request import HTTPXRequest
import logging
from config import BOT_TOKEN_TEST, PROXY_URL
from src.logger import setup_logging
from src.handlers.command_handler import start, setup_commands
from src.handlers.message_handler import handle_photo, handle_prompt, handle_video, handle_document
from src.handlers.callback_handler import handle_callback_query
from src.database.core import init_db
from src.quota import QuotaManager
from datetime import time, timezone, timedelta
import socket
from urllib.parse import urlparse

def get_best_proxy(default_proxy):
    """
    Check if the default proxy is accessible. If not, try fallback proxies.
    Fallback: local machine ports and other common ports.
    """
    logger = logging.getLogger("bot.network")
    proxies = [default_proxy]
    
    # Add local machine proxies as fallback
    proxies.append("socks5://127.0.0.1:7890")
    proxies.append("http://127.0.0.1:7890")
    proxies.append("socks5://127.0.0.1:10808")
    proxies.append("http://127.0.0.1:10809")
    
    try:
        parsed = urlparse(default_proxy)
        ip = parsed.hostname
        if ip and ip != "127.0.0.1":
            # Add fallback proxies for the same IP
            proxies.append(f"socks5://{ip}:10808")
            proxies.append(f"http://{ip}:10809")
    except Exception as e:
        logger.warning(f"⚠️ Error parsing proxy URL: {e}")
    
    # Deduplicate while preserving order
    unique_proxies = []
    for p in proxies:
        if p not in unique_proxies:
            unique_proxies.append(p)
    
    for proxy in unique_proxies:
        try:
            parsed = urlparse(proxy)
            host = parsed.hostname
            port = parsed.port
            
            if not host or not port:
                continue

            # Try to connect with a short timeout
            with socket.create_connection((host, port), timeout=2):
                logger.info(f"✅ Proxy Success: {proxy}")
                return proxy
        except Exception:
            continue
            
    logger.warning("⚠️ All proxies failed. Trying direct connection...")
    return None # Return None to use direct connection

async def clear_temp_credits_job(context):
    """Job to clear temporary credits every 48 hours at midnight"""
    logger = logging.getLogger("bot.jobs")
    logger.info("🕒 Running 48-hour temporary credits clearance...")
    qm = QuotaManager()
    await qm.clear_temp_credits()
    await qm.clear_temporary_ingots()
    logger.info("✅ 48-hour temporary credits clearance completed.")

async def post_init(application):
    await init_db()
    await setup_commands(application)
    
    # Schedule job to clear temporary credits every 48 hours at midnight (Beijing Time)
    beijing_tz = timezone(timedelta(hours=8))
    # run_repeating is used instead of run_daily to allow intervals longer than 24 hours
    # 48 hours = 48 * 60 * 60 = 172800 seconds
    from datetime import datetime
    
    # Calculate the next midnight in Beijing time to start the interval
    now = datetime.now(beijing_tz)
    # Move to tomorrow's midnight
    next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    
    application.job_queue.run_repeating(
        clear_temp_credits_job,
        interval=timedelta(hours=48),
        first=next_midnight
    )

def main():
    setup_logging()
    logger = logging.getLogger("bot.core")
    
    # Detect best proxy
    active_proxy = get_best_proxy(PROXY_URL)
    logger.info(f"🌐 Using Proxy: {active_proxy}")

    request = HTTPXRequest(
        proxy=active_proxy,
        connect_timeout=60.0,
        read_timeout=120.0,
        write_timeout=120.0,
        connection_pool_size=100,
    )

    # Use BOT_TOKEN_TEST for the test bot
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN_TEST)
        .request(request)
        .get_updates_request(request) # Ensure get_updates uses same request config
        .post_init(post_init) # Call setup_commands on startup
        .concurrent_updates(True)
        .build()
    )
    
    # Register Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_callback_query))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VIDEO, handle_video))
    app.add_handler(MessageHandler(filters.Document.IMAGE | filters.Document.VIDEO, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_prompt))

    logger.info("🧪 TEST Telegram Bot started")
    app.run_polling(poll_interval=2.0, timeout=30)

if __name__ == "__main__":
    main()
