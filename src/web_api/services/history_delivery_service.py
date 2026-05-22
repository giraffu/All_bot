import asyncio
import logging

import httpx
from fastapi import HTTPException
from sqlalchemy import select

from config import BOT_TOKEN, TELEGRAM_API_BASE_URL
from src.core.media_paths import resolve_storage_object
from src.database.models import History
from src.services.redis_client import redis_client
from src.services.storage import storage

logger = logging.getLogger(__name__)


async def _acquire_send_to_bot_rate_limit(user_id: int):
    lock_key = f"rate_limit:send_to_bot:{user_id}"
    if redis_client and redis_client.redis:
        is_locked = await redis_client.redis.set(lock_key, "1", nx=True, ex=10)
        if not is_locked:
            raise HTTPException(status_code=429, detail="操作过于频繁，请10秒后再试")


async def _load_owned_history_record(task_id: str, user_id: int, db) -> History:
    stmt = select(History).where(History.task_id == task_id, History.user_id == user_id)
    result = await db.execute(stmt)
    history = result.scalar_one_or_none()
    if not history:
        raise HTTPException(status_code=404, detail="未找到对应的任务记录")
    if not history.output_file:
        raise HTTPException(status_code=400, detail="该任务没有生成文件")
    return history


async def _download_history_bytes(output_file: str) -> tuple[str, bytes]:
    bucket_name, object_name = resolve_storage_object(output_file)
    try:
        file_bytes = await asyncio.to_thread(
            storage.get_file_bytes,
            object_name,
            bucket_name,
        )
    except Exception as exc:
        logger.error("Failed to download %s from %s: %s", object_name, bucket_name, exc)
        file_bytes = None

    if not file_bytes:
        raise HTTPException(status_code=500, detail="无法读取文件内容")
    return object_name, file_bytes


def _build_telegram_upload_request(
    *,
    telegram_id: int,
    history_type: str | None,
    history_prompt: str | None,
    object_name: str,
    file_bytes: bytes,
) -> tuple[str, dict[str, str], dict[str, tuple[str, bytes, str]]]:
    is_video = history_type and "video" in history_type.lower()
    method = "sendVideo" if is_video else "sendPhoto"
    url = f"{TELEGRAM_API_BASE_URL}/bot{BOT_TOKEN}/{method}"
    payload = {"chat_id": str(telegram_id)}

    if history_prompt:
        payload["caption"] = (
            history_prompt[:100] + "..." if len(history_prompt) > 100 else history_prompt
        )

    filename = object_name.split("/")[-1]
    if is_video:
        files = {"video": (filename, file_bytes, "video/mp4")}
    else:
        ext = filename.split(".")[-1].lower() if "." in filename else "jpeg"
        content_type = f"image/{ext}" if ext != "jpg" else "image/jpeg"
        files = {"photo": (filename, file_bytes, content_type)}

    return url, payload, files


async def _post_telegram_upload(url: str, payload: dict[str, str], files: dict):
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(url, data=payload, files=files, timeout=60.0)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in [400, 403]:
                error_msg = exc.response.text
                logger.error("Telegram API Error (400/403): %s", error_msg)
                if (
                    "wrong file identifier" in error_msg
                    or "failed to get HTTP URL content" in error_msg
                ):
                    raise HTTPException(
                        status_code=400,
                        detail="发送失败：Telegram 无法访问该文件或文件格式错误",
                    )
                raise HTTPException(
                    status_code=403,
                    detail="发送失败，请确保您在 Telegram 中已允许机器人发送消息",
                )
            logger.error("Telegram API Error: %s", exc.response.text)
            raise HTTPException(status_code=500, detail="发送失败，Telegram 服务器异常")
        except Exception as exc:
            logger.error("Send to bot request failed: %s", exc)
            raise HTTPException(status_code=500, detail="发送失败，网络连接异常")


async def send_history_record_to_telegram(*, task_id: str, current_user, db):
    telegram_id = current_user.telegram_id
    if not telegram_id:
        raise HTTPException(
            status_code=400,
            detail="您尚未绑定 Telegram 账号，无法发送至私聊",
        )

    await _acquire_send_to_bot_rate_limit(current_user.id)
    history = await _load_owned_history_record(task_id, current_user.id, db)
    object_name, file_bytes = await _download_history_bytes(history.output_file)
    url, payload, files = _build_telegram_upload_request(
        telegram_id=telegram_id,
        history_type=history.type,
        history_prompt=history.prompt,
        object_name=object_name,
        file_bytes=file_bytes,
    )
    await _post_telegram_upload(url, payload, files)

    return {"status": "success", "message": "已发送至您的 Telegram 私聊"}


async def send_current_user_history_record_to_telegram(
    *,
    task_id: str,
    current_user,
    db,
    service_fn=None,
):
    if service_fn is None:
        service_fn = send_history_record_to_telegram
    return await service_fn(
        task_id=task_id,
        current_user=current_user,
        db=db,
    )
