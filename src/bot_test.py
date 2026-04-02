from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    CallbackQueryHandler,
    PreCheckoutQueryHandler,
    filters,
)
from telegram.request import HTTPXRequest
import logging
import os
from config import PROXY_URL
from src.logger import setup_logging
from src.handlers.command_handler import start, setup_commands, toggle_maintenance
from src.handlers.message_handler import handle_photo, handle_prompt, handle_video, handle_document
from src.handlers.callback_handler import handle_callback_query
from src.database.core import init_db
import socket
from urllib.parse import urlparse
import asyncio
from src.services.payment_validator import TonPaymentValidator
from src.services.task_registry import TaskRegistry
from src.services.recovery_service import recover_active_tasks

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

async def clean_zombies_loop():
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(__file__)))
    from clean_zombies import main as run_clean_zombies
    logger = logging.getLogger("bot.core")
    while True:
        try:
            await run_clean_zombies()
        except Exception as e:
            logger.error(f"Error in clean_zombies_loop: {e}")
        await asyncio.sleep(600)  # Check every 10 minutes

async def post_init(application):
    await init_db()
    await setup_commands(application)
    
    # Initialize and start Payment Validator
    payment_validator = TonPaymentValidator(bot_app=application)
    asyncio.create_task(payment_validator.poll_transactions())
    
    # Recover tasks from Redis
    asyncio.create_task(recover_active_tasks(application))
    
    # Start automated zombie task cleaner
    asyncio.create_task(clean_zombies_loop())

async def post_shutdown(application):
    logger = logging.getLogger("bot.core")
    logger.info("Bot is shutting down. Tasks are persisted in Redis.")
    await TaskRegistry.refund_all(application.bot)
    from src.services.redis_client import redis_client
    await redis_client.close()
    from src.services.image_service import image_service
    await image_service.close()

def main():
    setup_logging()
    logger = logging.getLogger("bot.core")
    
    # Determine which token to use
    bot_type = os.getenv("BOT_TYPE", "TEST")
    
    # Reload from env directly just to be safe
    from dotenv import dotenv_values
    env_vars = dotenv_values(".env")
    
    token_prod = os.getenv("BOT_TOKEN") or env_vars.get("BOT_TOKEN")
    token_test = os.getenv("BOT_TOKEN_test") or env_vars.get("BOT_TOKEN_test") or os.getenv("BOT_TOKEN_TEST") or env_vars.get("BOT_TOKEN_TEST")
    
    token = token_prod if bot_type == "PROD" else token_test
    
    if not token:
        logger.error(f"Failed to start: {bot_type} token is not configured.")
        return

    logger.info(f"Starting bot in {bot_type} mode...")

    # Detect best proxy
    active_proxy = get_best_proxy(PROXY_URL)
    logger.info(f"🌐 Using Proxy: {active_proxy}")

    request = HTTPXRequest(
        proxy=active_proxy,
        connect_timeout=60.0,
        read_timeout=120.0,
        write_timeout=120.0,
        connection_pool_size=500,  # Increased for higher concurrency
    )

    app = (
        ApplicationBuilder()
        .token(token)
        .request(request)
        .get_updates_request(request) # Ensure get_updates uses same request config
        .post_init(post_init) # Call setup_commands on startup
        .post_shutdown(post_shutdown) # Call refund on shutdown
        .concurrent_updates(True)
        .build()
    )
    
    from src.handlers.payment_handler import precheckout_callback, successful_payment_callback
    
    # Register Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("maintenance", toggle_maintenance))
    app.add_handler(CallbackQueryHandler(handle_callback_query))
    app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VIDEO, handle_video))
    app.add_handler(MessageHandler(filters.Document.IMAGE | filters.Document.VIDEO, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_prompt))

    logger.info(f"🧪 {bot_type} Telegram Bot started")
    app.run_polling(poll_interval=2.0, timeout=30)

if __name__ == "__main__":
    main()
