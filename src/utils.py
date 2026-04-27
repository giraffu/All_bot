import asyncio
import configparser
import functools
import logging
import os
from typing import Any, Callable

import httpx
from telegram.error import BadRequest, Forbidden, NetworkError, RetryAfter, TimedOut

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
                        # Some debug messages might not be modified if they contain the same content
                        pass
                        return  # Successfully ignored

                    if isinstance(e, RetryAfter):
                        retry_after = e.retry_after
                        wait_seconds = (
                            retry_after.total_seconds()
                            if hasattr(retry_after, "total_seconds")
                            else float(retry_after)
                        )
                        if attempt == max_retries:
                            logger.error(
                                f"Function {func.__name__} failed after {max_retries} retries due to flood control: {e}"
                            )
                            raise e

                        logger.warning(
                            f"Flood control in {func.__name__}: {e}. Retrying in {wait_seconds}s... ({attempt + 1}/{max_retries})"
                        )
                        await asyncio.sleep(wait_seconds)
                        continue

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
                    ) and not isinstance(e, BadRequest):
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
async def robust_edit_text(message, text: str, **kwargs):
    """Safely edit message text with retry and length limit"""
    if not message:
        return None
    try:
        text = text[:4000]
        return await message.edit_text(text, **kwargs)
    except BadRequest as e:
        if "Message is not modified" in str(e):
            return message
        logger.error(f"Failed to edit message: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error editing message: {e}")
        return None

def create_background_task(context, coro):
    """
    Safely create a background asyncio task and store a strong reference to it
    in context.bot_data['bg_tasks'] to prevent Python's garbage collector
    from destroying the task mid-execution.
    """
    import asyncio
    task = asyncio.create_task(coro)
    if "bg_tasks" not in context.bot_data:
        context.bot_data["bg_tasks"] = set()
    context.bot_data["bg_tasks"].add(task)
    task.add_done_callback(context.bot_data["bg_tasks"].discard)
    return task


@async_retry(max_retries=3)
async def robust_edit_reply_markup(message, reply_markup=None, **kwargs):
    return await message.edit_reply_markup(reply_markup=reply_markup, **kwargs)


@async_retry(max_retries=3)
async def robust_edit_caption(message, caption, **kwargs):
    return await message.edit_caption(caption=caption, **kwargs)


@async_retry(max_retries=3)
async def robust_send_photo(bot, chat_id, photo, **kwargs):
    kwargs.setdefault('read_timeout', 180)
    kwargs.setdefault('write_timeout', 180)
    kwargs.setdefault('connect_timeout', 120)
    kwargs.setdefault('pool_timeout', 60)
    return await bot.send_photo(chat_id=chat_id, photo=photo, **kwargs)


@async_retry(max_retries=3)
async def robust_send_video(bot, chat_id, video, **kwargs):
    kwargs.setdefault('read_timeout', 300)
    kwargs.setdefault('write_timeout', 300)
    kwargs.setdefault('connect_timeout', 120)
    kwargs.setdefault('pool_timeout', 60)
    kwargs.setdefault('supports_streaming', True)
    kwargs.setdefault('filename', 'video.mp4')
    import time
    start_t = time.time()
    logger.info(f"Uploading video to user {chat_id}...")
    res = await bot.send_video(chat_id=chat_id, video=video, **kwargs)
    logger.info(f"Video uploaded to user {chat_id} in {time.time() - start_t:.2f} seconds.")
    return res


async def robust_delete_message(message):
    try:
        return await message.delete()
    except BadRequest as e:
        error_msg = str(e).lower()
        if "message to delete not found" in error_msg or "message can't be deleted" in error_msg:
            logger.warning(f"Message deletion skipped: {e}")
            return None
        raise e

async def safe_answer_query(query, **kwargs):
    """
    Safely answer a callback query, catching and logging the "Query is too old" 
    BadRequest exception. This prevents the entire handler from crashing if 
    the bot was too slow to respond to the click event.
    """
    try:
        await query.answer(**kwargs)
    except BadRequest as e:
        if "query is too old" in str(e).lower() or "query id is invalid" in str(e).lower():
            logger.warning(f"Callback query too old/invalid for user {query.from_user.id}, ignoring answer but proceeding with logic.")
        else:
            raise e
