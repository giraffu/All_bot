from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, or_, select, update
from telegram.error import BadRequest, Forbidden, RetryAfter

from src.database.core import AsyncSessionLocal
from src.database.models import (
    SupportNotificationAttempt,
    SupportNotificationOutbox,
    SupportNotificationRecipient,
    SupportTicket,
)

logger = logging.getLogger(__name__)

MAX_NOTIFICATION_RECIPIENTS = 20
TELEGRAM_MESSAGE_LIMIT = 4096
MAX_DELIVERY_ATTEMPTS = 8
RETRY_DELAYS_SECONDS = (5, 30, 120, 600, 1800, 3600, 10800)
CATEGORY_LABELS = {
    "recharge": "充值问题",
    "bug": "Bug反馈",
    "suggestion": "意见反馈",
    "business": "商业合作",
    "uncategorized": "未分类",
}


async def list_support_notification_recipient_ids(db) -> list[int]:
    result = await db.execute(
        select(SupportNotificationRecipient).order_by(
            SupportNotificationRecipient.telegram_user_id
        )
    )
    return [int(item.telegram_user_id) for item in result.scalars().all()]


async def replace_support_notification_recipient_ids(
    db,
    telegram_user_ids: Sequence[int],
) -> list[int]:
    normalized: list[int] = []
    for raw_user_id in telegram_user_ids:
        if isinstance(raw_user_id, bool):
            raise ValueError("telegram user ID must be a positive integer")
        user_id = int(raw_user_id)
        if user_id <= 0:
            raise ValueError("telegram user ID must be a positive integer")
        normalized.append(user_id)
    normalized = sorted(set(normalized))
    if len(normalized) > MAX_NOTIFICATION_RECIPIENTS:
        raise ValueError(
            f"at most {MAX_NOTIFICATION_RECIPIENTS} notification recipients are allowed"
        )

    await db.execute(delete(SupportNotificationRecipient))
    db.add_all(
        [
            SupportNotificationRecipient(telegram_user_id=user_id)
            for user_id in normalized
        ]
    )
    await db.commit()
    return normalized


@dataclass(frozen=True)
class ClaimedSupportNotification:
    outbox_id: int
    ticket_id: int
    recipient_telegram_user_id: int
    payload_text: str
    attempt_number: int
    lease_token: str


def notification_retry_delay_seconds(attempt_count: int) -> int:
    index = max(0, min(int(attempt_count) - 1, len(RETRY_DELAYS_SECONDS) - 1))
    return RETRY_DELAYS_SECONDS[index]


def build_support_ticket_notification(
    *,
    ticket: SupportTicket,
    messages: Sequence[dict[str, Any]],
) -> str:
    category = CATEGORY_LABELS.get(ticket.category, ticket.category)
    sender = ticket.full_name or (
        f"@{ticket.username}" if ticket.username else str(ticket.telegram_user_id)
    )
    lines = [
        f"新客服工单 #{ticket.id}",
        f"分类：{category}",
        f"用户：{sender}（TG {ticket.telegram_user_id}）",
        "",
        "提交内容：",
    ]
    for index, message in enumerate(messages, start=1):
        body = str(message.get("body") or "").strip()
        attachments = list(message.get("attachments") or [])
        content_parts = []
        if body:
            content_parts.append(body)
        for attachment in attachments:
            filename = str(attachment.get("filename") or "附件")
            content_parts.append(f"[附件] {filename}")
        if content_parts:
            lines.append(f"{index}. " + "\n".join(content_parts))

    text = "\n".join(lines)
    if len(text) <= TELEGRAM_MESSAGE_LIMIT:
        return text
    suffix = "\n…（内容过长，请到管理后台查看完整工单）"
    return text[: TELEGRAM_MESSAGE_LIMIT - len(suffix)] + suffix


async def enqueue_support_ticket_notifications(
    db,
    *,
    ticket: SupportTicket,
    messages: Sequence[dict[str, Any]],
) -> list[SupportNotificationOutbox]:
    recipient_ids = await list_support_notification_recipient_ids(db)
    if not recipient_ids:
        return []
    payload_text = build_support_ticket_notification(ticket=ticket, messages=messages)
    deliveries = [
        SupportNotificationOutbox(
            ticket_id=ticket.id,
            recipient_telegram_user_id=recipient_id,
            payload_text=payload_text,
        )
        for recipient_id in recipient_ids
    ]
    db.add_all(deliveries)
    return deliveries


async def claim_due_support_notifications(
    *,
    now: datetime,
    worker_id: str,
    batch_size: int,
    lease_seconds: int,
) -> list[ClaimedSupportNotification]:
    lease_token = uuid4().hex
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(SupportNotificationOutbox)
                .where(
                    SupportNotificationOutbox.next_attempt_at <= now,
                    or_(
                        SupportNotificationOutbox.status.in_(("pending", "retry")),
                        (
                            SupportNotificationOutbox.status == "processing"
                        )
                        & or_(
                            SupportNotificationOutbox.lease_until.is_(None),
                            SupportNotificationOutbox.lease_until < now,
                        ),
                    ),
                )
                .order_by(
                    SupportNotificationOutbox.next_attempt_at,
                    SupportNotificationOutbox.id,
                )
                .with_for_update(skip_locked=True)
                .limit(max(1, min(int(batch_size), 100)))
            )
        ).scalars().all()
        claimed: list[ClaimedSupportNotification] = []
        for delivery in rows:
            if delivery.status == "processing":
                await session.execute(
                    update(SupportNotificationAttempt)
                    .where(
                        SupportNotificationAttempt.outbox_id == delivery.id,
                        SupportNotificationAttempt.status == "processing",
                    )
                    .values(
                        status="abandoned",
                        error_type="LeaseExpired",
                        error_message="delivery lease expired before completion",
                        finished_at=now,
                    )
                )
            delivery.status = "processing"
            delivery.attempt_count = int(delivery.attempt_count or 0) + 1
            delivery.lease_token = lease_token
            delivery.lease_owner = worker_id[:128]
            delivery.lease_until = now + timedelta(seconds=max(30, lease_seconds))
            delivery.updated_at = now
            session.add(
                SupportNotificationAttempt(
                    outbox_id=delivery.id,
                    attempt_number=delivery.attempt_count,
                    status="processing",
                    worker_id=worker_id[:128],
                )
            )
            claimed.append(
                ClaimedSupportNotification(
                    outbox_id=delivery.id,
                    ticket_id=delivery.ticket_id,
                    recipient_telegram_user_id=delivery.recipient_telegram_user_id,
                    payload_text=delivery.payload_text,
                    attempt_number=delivery.attempt_count,
                    lease_token=lease_token,
                )
            )
        await session.commit()
        return claimed


async def complete_support_notification(
    job: ClaimedSupportNotification,
    *,
    telegram_message_id: int | None,
) -> None:
    now = datetime.now()
    async with AsyncSessionLocal() as session:
        delivery = (
            await session.execute(
                select(SupportNotificationOutbox)
                .where(
                    SupportNotificationOutbox.id == job.outbox_id,
                    SupportNotificationOutbox.status == "processing",
                    SupportNotificationOutbox.lease_token == job.lease_token,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if delivery is None:
            return
        delivery.status = "sent"
        delivery.sent_at = now
        delivery.lease_token = None
        delivery.lease_owner = None
        delivery.lease_until = None
        delivery.last_error_type = None
        delivery.last_error_message = None
        delivery.updated_at = now
        await session.execute(
            update(SupportNotificationAttempt)
            .where(
                SupportNotificationAttempt.outbox_id == job.outbox_id,
                SupportNotificationAttempt.attempt_number == job.attempt_number,
                SupportNotificationAttempt.status == "processing",
            )
            .values(
                status="sent",
                telegram_message_id=telegram_message_id,
                finished_at=now,
            )
        )
        await session.commit()


async def fail_support_notification(
    job: ClaimedSupportNotification,
    *,
    error_type: str,
    error_message: str,
    retryable: bool,
    retry_after_seconds: int,
) -> None:
    now = datetime.now()
    safe_error_type = str(error_type)[:100]
    safe_error_message = str(error_message)[:500]
    async with AsyncSessionLocal() as session:
        delivery = (
            await session.execute(
                select(SupportNotificationOutbox)
                .where(
                    SupportNotificationOutbox.id == job.outbox_id,
                    SupportNotificationOutbox.status == "processing",
                    SupportNotificationOutbox.lease_token == job.lease_token,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if delivery is None:
            return
        should_retry = retryable and int(delivery.attempt_count or 0) < MAX_DELIVERY_ATTEMPTS
        retry_at = (
            now + timedelta(seconds=max(1, int(retry_after_seconds)))
            if should_retry
            else None
        )
        delivery.status = "retry" if should_retry else "failed"
        if retry_at is not None:
            delivery.next_attempt_at = retry_at
        else:
            delivery.failed_at = now
        delivery.lease_token = None
        delivery.lease_owner = None
        delivery.lease_until = None
        delivery.last_error_type = safe_error_type
        delivery.last_error_message = safe_error_message
        delivery.updated_at = now
        await session.execute(
            update(SupportNotificationAttempt)
            .where(
                SupportNotificationAttempt.outbox_id == job.outbox_id,
                SupportNotificationAttempt.attempt_number == job.attempt_number,
                SupportNotificationAttempt.status == "processing",
            )
            .values(
                status="retry" if should_retry else "failed",
                error_type=safe_error_type,
                error_message=safe_error_message,
                retry_at=retry_at,
                finished_at=now,
            )
        )
        await session.commit()


def _retry_after_seconds(exc: Exception, *, attempt_number: int) -> int:
    if isinstance(exc, RetryAfter):
        value = exc.retry_after
        if isinstance(value, timedelta):
            return max(1, int(value.total_seconds()))
        return max(1, int(value))
    return notification_retry_delay_seconds(attempt_number)


def _is_retryable(exc: Exception) -> bool:
    return not isinstance(exc, (BadRequest, Forbidden))


class SupportNotificationDispatcher:
    def __init__(
        self,
        *,
        send_message: Callable[..., Awaitable[Any]],
        worker_id: str,
        claim_func: Callable[..., Awaitable[list[ClaimedSupportNotification]]] = claim_due_support_notifications,
        complete_func: Callable[..., Awaitable[None]] = complete_support_notification,
        fail_func: Callable[..., Awaitable[None]] = fail_support_notification,
        batch_size: int = 20,
        concurrency: int = 5,
        lease_seconds: int = 120,
        now_func: Callable[[], datetime] = datetime.now,
    ) -> None:
        self._send_message = send_message
        self._worker_id = worker_id
        self._claim_func = claim_func
        self._complete_func = complete_func
        self._fail_func = fail_func
        self._batch_size = max(1, min(int(batch_size), 100))
        self._concurrency = max(1, min(int(concurrency), 20))
        self._lease_seconds = max(30, int(lease_seconds))
        self._now_func = now_func
        self._lock = asyncio.Lock()

    @property
    def busy(self) -> bool:
        return self._lock.locked()

    async def _deliver_one(self, job: ClaimedSupportNotification) -> None:
        try:
            message = await self._send_message(
                chat_id=job.recipient_telegram_user_id,
                text=job.payload_text,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(
                "support notification delivery failed ticket_id=%s recipient_id=%s attempt=%s error_type=%s",
                job.ticket_id,
                job.recipient_telegram_user_id,
                job.attempt_number,
                type(exc).__name__,
            )
            await self._fail_func(
                job,
                error_type=type(exc).__name__,
                error_message=str(exc),
                retryable=_is_retryable(exc),
                retry_after_seconds=_retry_after_seconds(
                    exc,
                    attempt_number=job.attempt_number,
                ),
            )
            return
        await self._complete_func(
            job,
            telegram_message_id=getattr(message, "message_id", None),
        )

    async def run_once(self) -> int:
        async with self._lock:
            jobs = await self._claim_func(
                now=self._now_func(),
                worker_id=self._worker_id,
                batch_size=self._batch_size,
                lease_seconds=self._lease_seconds,
            )
            semaphore = asyncio.Semaphore(self._concurrency)

            async def deliver(job: ClaimedSupportNotification) -> None:
                async with semaphore:
                    await self._deliver_one(job)

            outcomes = await asyncio.gather(
                *(deliver(job) for job in jobs),
                return_exceptions=True,
            )
            for job, outcome in zip(jobs, outcomes):
                if isinstance(outcome, Exception):
                    logger.error(
                        "support notification bookkeeping failed ticket_id=%s recipient_id=%s error_type=%s",
                        job.ticket_id,
                        job.recipient_telegram_user_id,
                        type(outcome).__name__,
                    )
            return len(jobs)
