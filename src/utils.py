import asyncio
import configparser
import functools
import logging
import os
from typing import Any, Callable

import httpx
from telegram.error import Forbidden, NetworkError, TimedOut

logger = logging.getLogger(__name__)

# Constants for project root and maintenance file
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAINTENANCE_FILE = os.path.join(PROJECT_ROOT, 'MAINTENANCE')


def is_maintenance_mode() -> bool:
    """Check if the system is in maintenance mode by looking for the MAINTENANCE file."""
    return os.path.exists(MAINTENANCE_FILE)


def async_retry(max_retries: int = 3, delay: float = 1.0, backoff: float = 2.0):
    """
    Decorator to retry async functions on network errors.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            current_delay = delay
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    # Ignore "Message is not modified" errors (case-insensitive) across all exception types
                    err_msg = str(e).lower()
                    if "message is not modified" in err_msg:
                        # logger.warning(f"Message not modified in {func.__name__}, ignoring.")
                        return  # Successfully ignored

                    # Handle Forbidden (Bot blocked by user)
                    if isinstance(e, Forbidden):
                        logger.warning(
                            f"Bot blocked by user in {func.__name__}: {e}. Action skipped."
                        )
                        return  # Stop retrying and return None

                    # Handle Network-related errors for retry
                    if isinstance(
                        e,
                        (
                            httpx.ConnectError,
                            httpx.ReadTimeout,
                            httpx.WriteTimeout,
                            httpx.RequestError,
                            NetworkError,
                            TimedOut,
                        ),
                    ):
                        if attempt == max_retries:
                            logger.error(
                                f"Function {func.__name__} failed after {max_retries} retries: {e}"
                            )
                            raise e

                        logger.warning(
                            f"Network error in {func.__name__}: {e}. Retrying in {current_delay}s... ({attempt + 1}/{max_retries})"
                        )
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff
                        continue

                    # Other exceptions (like generic BadRequest that isn't 'message not modified') should be raised
                    raise e

        return wrapper

    return decorator


@functools.lru_cache(maxsize=1)
def load_prompts(file_path: str = "prompts.ini") -> dict:
    """
    Load prompts from an INI file.
    Returns a dictionary of prompts.
    Cached to avoid repeated file I/O.
    """
    config = configparser.ConfigParser()
    if not os.path.exists(file_path):
        # Fallback defaults if file missing
        return {
            "undress": "undress",
            "face_swap": "face swap",
            "negative_prompt": "low quality, bad anatomy, ugly, deformed, blurry, watermark, text",
        }

    config.read(file_path, encoding="utf-8")
    if "prompts" in config:
        return dict(config["prompts"])
    return {}


# Robust wrappers for Telegram Bot methods


@async_retry(max_retries=3)
async def robust_send_message(bot, chat_id, text, **kwargs):
    return await bot.send_message(chat_id=chat_id, text=text, **kwargs)


@async_retry(max_retries=3)
async def robust_reply_text(message, text, **kwargs):
    return await message.reply_text(text=text, **kwargs)


@async_retry(max_retries=3)
async def robust_edit_text(message, text, **kwargs):
    return await message.edit_text(text=text, **kwargs)


@async_retry(max_retries=3)
async def robust_edit_reply_markup(message, reply_markup=None, **kwargs):
    return await message.edit_reply_markup(reply_markup=reply_markup, **kwargs)


@async_retry(max_retries=3)
async def robust_edit_caption(message, caption, **kwargs):
    return await message.edit_caption(caption=caption, **kwargs)


@async_retry(max_retries=3)
async def robust_send_photo(bot, chat_id, photo, **kwargs):
    return await bot.send_photo(chat_id=chat_id, photo=photo, **kwargs)


@async_retry(max_retries=3)
async def robust_send_video(bot, chat_id, video, **kwargs):
    return await bot.send_video(chat_id=chat_id, video=video, **kwargs)


@async_retry(max_retries=3)
async def robust_delete_message(message):
    return await message.delete()
