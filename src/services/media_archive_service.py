"""Transactional archive outbox and receipt service.

This service never contacts NAS or R2. It only coordinates durable work.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Sequence

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
    MediaArchiveRestoreOutbox,
)


async def enqueue_history_media_archive(
    session: AsyncSession, history: History, *, priority: int = 0
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
            MediaArchiveOutbox(
                history_id=history.id,
                manifest_hash=manifest_hash,
                priority=max(0, min(priority, 100)),
            )
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
    max_priority: int = 100,
    history_ids: Sequence[int] | None = None,
) -> list[dict[str, Any]]:
    now = datetime.now()
    exact_history_ids = tuple(sorted(set(history_ids or ())))
    result = await session.execute(
        select(MediaArchiveOutbox, History)
        .join(History, History.id == MediaArchiveOutbox.history_id)
        .where(
            MediaArchiveOutbox.available_at <= now,
            MediaArchiveOutbox.priority <= max(0, min(max_priority, 100)),
            *(
                [MediaArchiveOutbox.history_id.in_(exact_history_ids)]
                if exact_history_ids
                else []
            ),
            or_(
                MediaArchiveOutbox.status.in_(("pending", "retry")),
                (MediaArchiveOutbox.status == "leased")
                & (MediaArchiveOutbox.lease_expires_at < now),
            ),
        )
        .order_by(
            MediaArchiveOutbox.priority,
            History.created_at.desc(),
            MediaArchiveOutbox.id,
        )
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


async def renew_archive_lease(
    session: AsyncSession,
    *,
    history_id: int,
    worker_id: str,
    revision: int,
    lease_seconds: int = 900,
) -> datetime:
    """Extend only the currently owned revision of an active lease."""
    result = await session.execute(
        select(MediaArchiveOutbox)
        .where(MediaArchiveOutbox.history_id == history_id)
        .with_for_update()
    )
    outbox = result.scalar_one_or_none()
    if outbox is None or outbox.status != "leased":
        raise ValueError("archive job is not leased")
    if outbox.lease_owner != worker_id:
        raise ValueError("archive lease is owned by another worker")
    if outbox.revision != revision:
        raise ValueError("archive lease revision changed")
    expires_at = datetime.now() + timedelta(seconds=max(60, lease_seconds))
    outbox.lease_expires_at = expires_at
    await session.commit()
    return expires_at


async def record_archive_receipts(
    session: AsyncSession,
    *,
    history_id: int,
    worker_id: str,
    revision: int,
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
    if outbox.revision != revision:
        raise ValueError("archive receipt revision changed")
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
    revision: int,
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
    if outbox.revision != revision:
        raise ValueError("archive failure revision changed")
    outbox.status = "retry" if retryable else "manual_review"
    delay_minutes = min(360, 2 ** min(int(outbox.attempts or 1), 8))
    outbox.available_at = datetime.now() + timedelta(minutes=delay_minutes)
    outbox.lease_owner = None
    outbox.lease_expires_at = None
    outbox.last_error_code = error_code[:64]
    outbox.last_error_message = message[:1000]
    await session.commit()


async def enqueue_history_media_restore(
    session: AsyncSession, history: History, *, priority: int = 0
) -> bool:
    """Transactionally request R2 rehydration only for a verified archive."""
    await session.flush()
    archived = (
        await session.execute(
            select(MediaArchiveOutbox).where(
                MediaArchiveOutbox.history_id == history.id,
                MediaArchiveOutbox.status == "archived",
            )
        )
    ).scalar_one_or_none()
    if archived is None:
        return False
    result = await session.execute(
        select(MediaArchiveRestoreOutbox)
        .where(MediaArchiveRestoreOutbox.history_id == history.id)
        .with_for_update()
    )
    outbox = result.scalar_one_or_none()
    if outbox is None:
        session.add(
            MediaArchiveRestoreOutbox(
                history_id=history.id,
                priority=max(0, min(priority, 100)),
            )
        )
        return True
    if outbox.status in {"pending", "leased", "retry"}:
        return False
    outbox.revision = int(outbox.revision or 0) + 1
    outbox.status = "pending"
    outbox.priority = max(0, min(priority, 100))
    outbox.available_at = datetime.now()
    outbox.lease_owner = None
    outbox.lease_expires_at = None
    outbox.restored_at = None
    outbox.last_error_code = None
    outbox.last_error_message = None
    return True


async def claim_restore_jobs(
    session: AsyncSession,
    *,
    worker_id: str,
    limit: int = 20,
    lease_seconds: int = 900,
) -> list[dict[str, Any]]:
    now = datetime.now()
    result = await session.execute(
        select(MediaArchiveRestoreOutbox, History)
        .join(History, History.id == MediaArchiveRestoreOutbox.history_id)
        .where(
            MediaArchiveRestoreOutbox.available_at <= now,
            or_(
                MediaArchiveRestoreOutbox.status.in_(("pending", "retry")),
                (MediaArchiveRestoreOutbox.status == "leased")
                & (MediaArchiveRestoreOutbox.lease_expires_at < now),
            ),
        )
        .order_by(
            MediaArchiveRestoreOutbox.priority,
            MediaArchiveRestoreOutbox.id,
        )
        .limit(max(1, min(limit, 100)))
        .with_for_update(skip_locked=True)
    )
    jobs = []
    for outbox, history in result.all():
        receipts = (
            (
                await session.execute(
                    select(MediaArchiveReceipt)
                    .where(
                        MediaArchiveReceipt.history_id == history.id,
                        MediaArchiveReceipt.status == "archived_verified",
                    )
                    .order_by(MediaArchiveReceipt.role, MediaArchiveReceipt.ordinal)
                )
            )
            .scalars()
            .all()
        )
        if not receipts:
            outbox.status = "manual_review"
            outbox.last_error_code = "ARCHIVE_RECEIPTS_MISSING"
            continue
        outbox.status = "leased"
        outbox.lease_owner = worker_id
        outbox.lease_expires_at = now + timedelta(seconds=max(60, lease_seconds))
        outbox.attempts = int(outbox.attempts or 0) + 1
        jobs.append(
            {
                "history_id": history.id,
                "task_id": history.task_id,
                "history_type": history.type,
                "revision": outbox.revision,
                "assets": [
                    {
                        "role": receipt.role,
                        "ordinal": receipt.ordinal,
                        "source_ref": receipt.source_ref,
                        "sha256": receipt.sha256,
                        "byte_size": receipt.byte_size,
                        "mime_type": receipt.mime_type,
                        "nas_bucket": receipt.nas_bucket,
                        "nas_key": receipt.nas_key,
                    }
                    for receipt in receipts
                ],
            }
        )
    await session.commit()
    return jobs


async def renew_restore_lease(
    session: AsyncSession,
    *,
    history_id: int,
    worker_id: str,
    revision: int,
    lease_seconds: int = 900,
) -> datetime:
    result = await session.execute(
        select(MediaArchiveRestoreOutbox)
        .where(MediaArchiveRestoreOutbox.history_id == history_id)
        .with_for_update()
    )
    outbox = result.scalar_one_or_none()
    if outbox is None or outbox.status != "leased":
        raise ValueError("restore job is not leased")
    if outbox.lease_owner != worker_id:
        raise ValueError("restore lease is owned by another worker")
    if outbox.revision != revision:
        raise ValueError("restore lease revision changed")
    expires_at = datetime.now() + timedelta(seconds=max(60, lease_seconds))
    outbox.lease_expires_at = expires_at
    await session.commit()
    return expires_at


async def record_restore_receipt(
    session: AsyncSession,
    *,
    history_id: int,
    worker_id: str,
    revision: int,
    restored_assets: list[dict[str, Any]],
) -> None:
    result = await session.execute(
        select(MediaArchiveRestoreOutbox)
        .where(MediaArchiveRestoreOutbox.history_id == history_id)
        .with_for_update()
    )
    outbox = result.scalar_one_or_none()
    if outbox is None or outbox.status != "leased":
        raise ValueError("restore job is not receivable")
    if outbox.lease_owner != worker_id:
        raise ValueError("restore lease is owned by another worker")
    if outbox.revision != revision:
        raise ValueError("restore receipt revision changed")
    expected = {
        (receipt.role, receipt.ordinal)
        for receipt in (
            (
                await session.execute(
                    select(MediaArchiveReceipt).where(
                        MediaArchiveReceipt.history_id == history_id,
                        MediaArchiveReceipt.status == "archived_verified",
                    )
                )
            )
            .scalars()
            .all()
        )
    }
    restored = {(str(item["role"]), int(item["ordinal"])) for item in restored_assets}
    if not expected or not expected.issubset(restored):
        raise ValueError("restore receipt does not cover verified archive assets")
    outbox.status = "restored"
    outbox.restored_at = datetime.now()
    outbox.lease_owner = None
    outbox.lease_expires_at = None
    await session.commit()


async def record_restore_failure(
    session: AsyncSession,
    *,
    history_id: int,
    worker_id: str,
    revision: int,
    error_code: str,
    message: str,
    retryable: bool,
) -> None:
    result = await session.execute(
        select(MediaArchiveRestoreOutbox)
        .where(MediaArchiveRestoreOutbox.history_id == history_id)
        .with_for_update()
    )
    outbox = result.scalar_one_or_none()
    if outbox is None:
        raise ValueError("restore job not found")
    if outbox.lease_owner and outbox.lease_owner != worker_id:
        raise ValueError("restore lease is owned by another worker")
    if outbox.revision != revision:
        raise ValueError("restore failure revision changed")
    outbox.status = "retry" if retryable else "manual_review"
    outbox.available_at = datetime.now() + timedelta(
        minutes=min(360, 2 ** min(int(outbox.attempts or 1), 8))
    )
    outbox.lease_owner = None
    outbox.lease_expires_at = None
    outbox.last_error_code = error_code[:64]
    outbox.last_error_message = message[:1000]
    await session.commit()
