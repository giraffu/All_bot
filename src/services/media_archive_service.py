"""Transactional archive outbox and receipt service.

This service never contacts NAS or R2. It only coordinates durable work.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.media_archive import (
    extract_history_media_assets,
    media_manifest_hash,
    receipts_cover_assets,
)
from src.database.models import (
    History,
    MediaArchiveOutbox,
    MediaArchiveReceipt,
)


async def enqueue_history_media_archive(
    session: AsyncSession, history: History
) -> bool:
    """Create or refresh one idempotent outbox row in the History transaction."""
    await session.flush()
    assets = extract_history_media_assets(history)
    if not assets:
        return False
    manifest_hash = media_manifest_hash(assets)
    result = await session.execute(
        select(MediaArchiveOutbox)
        .where(MediaArchiveOutbox.history_id == history.id)
        .with_for_update()
    )
    outbox = result.scalar_one_or_none()
    if outbox is None:
        session.add(
            MediaArchiveOutbox(history_id=history.id, manifest_hash=manifest_hash)
        )
        return True
    if outbox.manifest_hash == manifest_hash:
        return False

    outbox.manifest_hash = manifest_hash
    outbox.revision = int(outbox.revision or 0) + 1
    outbox.status = "pending"
    outbox.available_at = datetime.now()
    outbox.lease_owner = None
    outbox.lease_expires_at = None
    outbox.archived_at = None
    outbox.last_error_code = None
    outbox.last_error_message = None
    await session.execute(
        delete(MediaArchiveReceipt).where(MediaArchiveReceipt.history_id == history.id)
    )
    return True


async def claim_archive_jobs(
    session: AsyncSession,
    *,
    worker_id: str,
    limit: int = 20,
    lease_seconds: int = 900,
) -> list[dict[str, Any]]:
    now = datetime.now()
    result = await session.execute(
        select(MediaArchiveOutbox, History)
        .join(History, History.id == MediaArchiveOutbox.history_id)
        .where(
            MediaArchiveOutbox.available_at <= now,
            or_(
                MediaArchiveOutbox.status.in_(("pending", "retry")),
                (MediaArchiveOutbox.status == "leased")
                & (MediaArchiveOutbox.lease_expires_at < now),
            ),
        )
        .order_by(History.created_at.desc(), MediaArchiveOutbox.id)
        .limit(max(1, min(limit, 100)))
        .with_for_update(skip_locked=True)
    )
    jobs = []
    for outbox, history in result.all():
        outbox.status = "leased"
        outbox.lease_owner = worker_id
        outbox.lease_expires_at = now + timedelta(seconds=max(60, lease_seconds))
        outbox.attempts = int(outbox.attempts or 0) + 1
        jobs.append(
            {
                "outbox_id": outbox.id,
                "history_id": history.id,
                "task_id": history.task_id,
                "user_id": history.user_id,
                "created_at": history.created_at,
                "revision": outbox.revision,
                "manifest_hash": outbox.manifest_hash,
                "assets": [
                    asset.__dict__ for asset in extract_history_media_assets(history)
                ],
            }
        )
    await session.commit()
    return jobs


async def record_archive_receipts(
    session: AsyncSession,
    *,
    history_id: int,
    worker_id: str,
    receipts: list[dict[str, Any]],
) -> bool:
    outbox_result = await session.execute(
        select(MediaArchiveOutbox)
        .where(MediaArchiveOutbox.history_id == history_id)
        .with_for_update()
    )
    outbox = outbox_result.scalar_one_or_none()
    if outbox is None or outbox.status not in {"leased", "retry", "pending"}:
        raise ValueError("archive job is not receivable")
    if outbox.lease_owner and outbox.lease_owner != worker_id:
        raise ValueError("archive lease is owned by another worker")
    history = await session.get(History, history_id)
    if history is None:
        raise ValueError("history not found")

    for payload in receipts:
        existing_result = await session.execute(
            select(MediaArchiveReceipt).where(
                MediaArchiveReceipt.history_id == history_id,
                MediaArchiveReceipt.role == payload["role"],
                MediaArchiveReceipt.ordinal == payload["ordinal"],
            )
        )
        receipt = existing_result.scalar_one_or_none()
        values = dict(payload)
        values.update(history_id=history_id, status="archived_verified")
        if receipt is None:
            session.add(MediaArchiveReceipt(**values))
        else:
            for key, value in values.items():
                setattr(receipt, key, value)
    await session.flush()
    stored_result = await session.execute(
        select(MediaArchiveReceipt).where(MediaArchiveReceipt.history_id == history_id)
    )
    complete = receipts_cover_assets(
        extract_history_media_assets(history), stored_result.scalars().all()
    )
    if complete:
        outbox.status = "archived"
        outbox.archived_at = datetime.now()
        outbox.lease_owner = None
        outbox.lease_expires_at = None
    await session.commit()
    return complete


async def record_archive_failure(
    session: AsyncSession,
    *,
    history_id: int,
    worker_id: str,
    error_code: str,
    message: str,
    retryable: bool,
) -> None:
    result = await session.execute(
        select(MediaArchiveOutbox)
        .where(MediaArchiveOutbox.history_id == history_id)
        .with_for_update()
    )
    outbox = result.scalar_one_or_none()
    if outbox is None:
        raise ValueError("archive job not found")
    if outbox.lease_owner and outbox.lease_owner != worker_id:
        raise ValueError("archive lease is owned by another worker")
    outbox.status = "retry" if retryable else "manual_review"
    delay_minutes = min(360, 2 ** min(int(outbox.attempts or 1), 8))
    outbox.available_at = datetime.now() + timedelta(minutes=delay_minutes)
    outbox.lease_owner = None
    outbox.lease_expires_at = None
    outbox.last_error_code = error_code[:64]
    outbox.last_error_message = message[:1000]
    await session.commit()
