import hashlib
import hmac
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import PrivateQqccBot
from src.services.private_qqcc_bot_webhook_queue import (
    PrivateQqccBotWebhookQueueError,
    enqueue_private_qqcc_bot_update,
)
from src.web_api.dependencies import get_db


router = APIRouter()
PRIVATE_BOT_WEBHOOK_MAX_BYTES = 1024 * 1024


def _webhook_secret_is_valid(
    *, provided_secret: str | None, stored_hash: str | None
) -> bool:
    candidate_hash = hashlib.sha256((provided_secret or "").encode("utf-8")).hexdigest()
    return hmac.compare_digest(candidate_hash, stored_hash or "")


def _valid_update_id(update: dict[str, Any]) -> int | None:
    update_id = update.get("update_id")
    if isinstance(update_id, bool) or not isinstance(update_id, int) or update_id <= 0:
        return None
    return update_id


@router.post("/webhook/{public_id}")
async def receive_private_bot_webhook(
    public_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PrivateQqccBot).where(
            PrivateQqccBot.webhook_public_id == public_id
        )
    )
    private_bot = result.scalar_one_or_none()
    if private_bot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Private bot webhook not found",
        )

    provided_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if not _webhook_secret_is_valid(
        provided_secret=provided_secret,
        stored_hash=private_bot.webhook_secret_hash,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook secret",
        )

    if (
        not private_bot.owner_enabled
        or not private_bot.admin_enabled
        or private_bot.runtime_status != "active"
    ):
        return {"status": "dropped", "reason": "inactive"}

    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > PRIVATE_BOT_WEBHOOK_MAX_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="Telegram update is too large",
            )
    try:
        update = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Telegram update",
        ) from None

    if not isinstance(update, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Telegram update",
        )
    update_id = _valid_update_id(update)
    if update_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Telegram update",
        )

    try:
        queued = await enqueue_private_qqcc_bot_update(
            private_bot_id=private_bot.id,
            update_id=update_id,
            update=update,
        )
    except PrivateQqccBotWebhookQueueError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook queue unavailable",
        ) from None

    if not queued:
        return {"status": "duplicate"}
    return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content={"status": "queued"})
