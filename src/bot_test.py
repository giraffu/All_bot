import logging
import os
import uuid
from urllib.parse import urlparse

import httpx
from asgi_correlation_id import correlation_id

# ================= PATCH TELEGRAM FILE DOWNLOAD =================
from telegram import File, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    PreCheckoutQueryHandler,
    TypeHandler,
    filters,
)
from telegram.request import HTTPXRequest

from src.database.core import init_db
from src.handlers.callback_handler import handle_callback_query
from src.handlers.command_handler import (
    cancel,
    setup_commands,
    start,
    toggle_maintenance,
)
from src.handlers.message_handler import (
    handle_document,
    handle_photo,
    handle_prompt,
    handle_video,
)
from src.logger import setup_logging

logger = logging.getLogger(__name__)

original_download_to_drive = File.download_to_drive

async def custom_download_to_drive(self, custom_path=None, read_timeout=None, write_timeout=None, connect_timeout=None, pool_timeout=None):
    bot = self.get_bot()
    if bot.base_file_url and "8082" in bot.base_file_url:
        
        raw_path = self.file_path
        if raw_path.startswith("http"):
            raw_path = urlparse(raw_path).path
        if not raw_path.startswith("/"):
            raw_path = "/" + raw_path
        url = f"http://69.63.220.115:8082{raw_path}"

        logger.info(f"Custom downloading file from: {url}")
        async with httpx.AsyncClient(proxy=None) as client:
            response = await client.get(url, timeout=120.0)
            response.raise_for_status()
            with open(custom_path, "wb") as f:
                f.write(response.content)
        return self
    else:
        return await original_download_to_drive(self, custom_path, read_timeout, write_timeout, connect_timeout, pool_timeout)

File.download_to_drive = custom_download_to_drive
# ================================================================

import asyncio

from src.services.payment_validator import TonPaymentValidator
from src.services.recovery_service import recover_active_tasks
from src.services.task_registry import TaskRegistry


async def clean_zombies_loop(bot=None):
    from src.services.zombie_cleaner_service import clean_zombies
    core_logger = logging.getLogger("bot.core")
    while True:
        try:
            await clean_zombies(bot)
        except Exception as e:
            core_logger.error(f"Error in clean_zombies_loop: {e}")
        await asyncio.sleep(600)  # Check every 10 minutes

async def inject_trace_id(update: Update, context):
    trace_id = str(uuid.uuid4())
    correlation_id.set(trace_id)
    core_logger = logging.getLogger("bot.core")
    if update.callback_query:
        core_logger.info(f"Received callback query: {update.callback_query.data}")
    elif update.message and update.message.text:
        pass # Already logged in handle_prompt

async def post_init(application):
    from src.handlers.prompt_router import build_global_menu_filter
    build_global_menu_filter()
    
    await init_db()
    await setup_commands(application)
    
    # Create a set to hold strong references to background tasks
    # The event loop only keeps weak references, so tasks can be garbage collected mid-execution if not stored.
    if "bg_tasks" not in application.bot_data:
        application.bot_data["bg_tasks"] = set()
    
    # Initialize and start Payment Validator
    payment_validator = TonPaymentValidator(bot_app=application)
    task_payment = asyncio.create_task(payment_validator.poll_transactions())
    application.bot_data["bg_tasks"].add(task_payment)
    task_payment.add_done_callback(application.bot_data["bg_tasks"].discard)
    
    # Recover tasks from Redis
    task_recover = asyncio.create_task(recover_active_tasks(application))
    application.bot_data["bg_tasks"].add(task_recover)
    task_recover.add_done_callback(application.bot_data["bg_tasks"].discard)
    
    # Start automated zombie task cleaner
    task_zombies = asyncio.create_task(clean_zombies_loop(application.bot))
    application.bot_data["bg_tasks"].add(task_zombies)
    task_zombies.add_done_callback(application.bot_data["bg_tasks"].discard)

async def post_shutdown(application):
    core_logger = logging.getLogger("bot.core")
    core_logger.info("Bot is shutting down. Tasks are persisted in Redis.")
    await TaskRegistry.refund_all(application.bot)
    from src.services.redis_client import redis_client
    await redis_client.close()

def main():
    setup_logging()
    core_logger = logging.getLogger("bot.core")
    
    # Determine which token to use
    bot_type = os.getenv("BOT_TYPE", "TEST")
    
    # Reload from env directly just to be safe
    from dotenv import dotenv_values
    env_vars = dotenv_values(".env")
    
    token_prod = os.getenv("BOT_TOKEN") or env_vars.get("BOT_TOKEN")
    token_test = os.getenv("BOT_TOKEN_test") or env_vars.get("BOT_TOKEN_test") or os.getenv("BOT_TOKEN_TEST") or env_vars.get("BOT_TOKEN_TEST")
    
    token = token_prod if bot_type == "PROD" else token_test
    
    if not token:
        core_logger.error(f"Failed to start: {bot_type} token is not configured.")
        return

    core_logger.info(f"Starting bot in {bot_type} mode...")

    if bot_type == "TEST":
        # 🧪 TEST: 直连 VPS Local API Server，抛弃商业代理
        core_logger.info("🧪 TEST模式：已启用 Local Bot API 直连 (http://69.63.220.115:8081)")
        
        request = HTTPXRequest(
            proxy=None, # MUST EXPLICITLY SET NO PROXY to bypass env variables!
            connect_timeout=60.0,
            read_timeout=120.0,
            write_timeout=120.0,
            connection_pool_size=500,
        )
        
        app = (
            ApplicationBuilder()
            .token(token)
            .base_url("http://69.63.220.115:8081/bot")
            .base_file_url("http://69.63.220.115:8082")
            .request(request)
            .get_updates_request(request)
            .post_init(post_init)
            .post_shutdown(post_shutdown)
            .concurrent_updates(True)
            .build()
        )
    else:
        # 🚀 PROD: 直连 VPS Local API Server
        core_logger.info("🚀 PROD模式：已启用 Local Bot API 直连 (http://69.63.220.115:8081)")

        request = HTTPXRequest(
            proxy=None,
            connect_timeout=60.0,
            read_timeout=120.0,
            write_timeout=120.0,
            connection_pool_size=500,
        )

        app = (
            ApplicationBuilder()
            .token(token)
            .base_url("http://69.63.220.115:8081/bot")
            .base_file_url("http://69.63.220.115:8082")
            .request(request)
            .get_updates_request(request)
            .post_init(post_init)
            .post_shutdown(post_shutdown)
            .concurrent_updates(True)
            .build()
        )
    
    from src.handlers.fsm.custom_video_fsm import get_custom_video_fsm_handler
    from src.handlers.fsm.edit_image_fsm import get_edit_image_fsm_handler
    from src.handlers.fsm.face_video_fsm import get_face_video_fsm_handler
    from src.handlers.fsm.faceswap_fsm import get_faceswap_fsm_handler
    from src.handlers.fsm.gallery_apply_fsm import get_gallery_apply_fsm_handler
    from src.handlers.fsm.ltx_video_fsm import get_ltx_video_fsm_handler
    from src.handlers.fsm.quick_image_fsm import get_quick_image_fsm_handler
    from src.handlers.fsm.quick_video_fsm import get_quick_video_fsm_handler
    from src.handlers.fsm.video_lora_fsm import get_video_lora_fsm_handler
    from src.handlers.payment_handler import (
        precheckout_callback,
        successful_payment_callback,
    )

    
    # Register FSM Handlers first (they must intercept text/callbacks before fallback handlers)
    app.add_handler(TypeHandler(Update, inject_trace_id), group=-1)
    app.add_handler(get_gallery_apply_fsm_handler())
    app.add_handler(get_face_video_fsm_handler())
    app.add_handler(get_faceswap_fsm_handler())
    app.add_handler(get_edit_image_fsm_handler())
    app.add_handler(get_custom_video_fsm_handler())
    app.add_handler(get_ltx_video_fsm_handler())
    app.add_handler(get_video_lora_fsm_handler())
    app.add_handler(get_quick_image_fsm_handler())
    app.add_handler(get_quick_video_fsm_handler())

    # Register Fallback Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("maintenance", toggle_maintenance))
    app.add_handler(CallbackQueryHandler(handle_callback_query))
    app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VIDEO, handle_video))
    app.add_handler(MessageHandler(filters.Document.IMAGE | filters.Document.VIDEO, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_prompt))

    core_logger.info(f"🧪 {bot_type} Telegram Bot started")
    import signal
    app.run_polling(
        poll_interval=2.0, 
        timeout=30,
        stop_signals=(signal.SIGINT, signal.SIGTERM, signal.SIGABRT)
    )

if __name__ == "__main__":
    main()
