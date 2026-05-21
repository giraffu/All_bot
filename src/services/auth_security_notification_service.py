import asyncio
import logging
import os

import aiohttp

from config import BOT_TOKEN, BOT_TOKEN_TEST, TELEGRAM_API_BASE_URL

logger = logging.getLogger(__name__)


def _resolve_bot_token() -> str | None:
    bot_type = os.getenv("BOT_TYPE", "PROD")
    return BOT_TOKEN_TEST if bot_type == "TEST" else BOT_TOKEN


def _log_background_task_result(task: asyncio.Task) -> None:
    try:
        task.result()
    except Exception:
        logger.exception("Security notification background task failed")


async def send_security_notification(telegram_id: int | None, message: str) -> None:
    token = _resolve_bot_token()
    if not token or not telegram_id:
        return

    url = f"{TELEGRAM_API_BASE_URL}/bot{token}/sendMessage"
    payload = {"chat_id": telegram_id, "text": message, "parse_mode": "Markdown"}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, proxy=None) as response:
                if response.status != 200:
                    logger.error(
                        "Failed to send security notification to %s: %s",
                        telegram_id,
                        await response.text(),
                    )
    except Exception:
        logger.exception(
            "Exception sending security notification to telegram_id=%s", telegram_id
        )


def schedule_password_login_notification(
    telegram_id: int | None, client_ip: str
) -> None:
    task = asyncio.create_task(
        send_security_notification(
            telegram_id,
            f"⚠️ **结界异动提醒**\n您的修仙结界刚刚通过密咒登录 (IP: {client_ip})。若非本人操作，请及时前往个人中心重置密咒。",
        )
    )
    task.add_done_callback(_log_background_task_result)


def schedule_password_changed_notification(telegram_id: int | None) -> None:
    task = asyncio.create_task(
        send_security_notification(
            telegram_id,
            "🔒 **密咒变更提醒**\n您的修仙结界密咒已重新设置，旧会话已全部强制失效。若非本人操作，您的 Telegram 账号可能存在极高风险！",
        )
    )
    task.add_done_callback(_log_background_task_result)
