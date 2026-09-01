from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .config import get_settings
from .models import (
    AuditLog,
    CreditEntry,
    MediaFile,
    MediaKind,
    Task,
    TaskAttempt,
    TaskStatus,
    TaskType,
    User,
    Worker,
)
from .pricing import quote_points
from .schemas import TaskView


settings = get_settings()
ACTIVE_STATUSES = {
    TaskStatus.CLAIMED,
    TaskStatus.PREPROCESSING,
    TaskStatus.RUNNING,
    TaskStatus.UPLOADING,
}
VIDEO_UPSCALE_MAX_BYTES = 40 * 1024 * 1024
VIDEO_UPSCALE_MAX_SECONDS = 5.0


async def apply_credit_entry(
    db: AsyncSession,
    *,
    user: User,
    kind: str,
    available_delta: int,
    reserved_delta: int,
    idempotency_key: str,
    task_id: str | None = None,
    details: dict | None = None,
) -> CreditEntry:
    existing = await db.scalar(
        select(CreditEntry).where(CreditEntry.idempotency_key == idempotency_key)
    )
    if existing:
        if (
            existing.user_id != user.id
            or existing.available_delta != available_delta
            or existing.reserved_delta != reserved_delta
            or existing.task_id != task_id
        ):
            raise HTTPException(status_code=409, detail="idempotency_conflict")
        return existing
    if user.available_points + available_delta < 0:
        raise HTTPException(status_code=402, detail="insufficient_points")
    if user.reserved_points + reserved_delta < 0:
        raise HTTPException(status_code=409, detail="invalid_reserved_balance")
    user.available_points += available_delta
    user.reserved_points += reserved_delta
    entry = CreditEntry(
        user_id=user.id,
        task_id=task_id,
        kind=kind,
        available_delta=available_delta,
        reserved_delta=reserved_delta,
        idempotency_key=idempotency_key,
        details=details or {},
    )
    db.add(entry)
    return entry


async def create_task(
    db: AsyncSession,
    *,
    user_id: str,
    source_file_id: str,
    task_type: TaskType,
    multiplier: int,
) -> Task:
    user = await db.scalar(
        select(User).where(User.id == user_id).with_for_update()
    )
    source = await db.get(MediaFile, source_file_id)
    if user is None or source is None or source.owner_id != user_id or source.deleted_at:
        raise HTTPException(status_code=404, detail="source_not_found")
    if task_type != TaskType.VIDEO_UPSCALE:
        raise HTTPException(status_code=422, detail="video_upscale_only")
    if multiplier != 2:
        raise HTTPException(status_code=422, detail="video_upscale_requires_2x")
    if (source.duration_seconds or 0) > VIDEO_UPSCALE_MAX_SECONDS:
        raise HTTPException(status_code=422, detail="video_upscale_max_5_seconds")
    if source.size_bytes > VIDEO_UPSCALE_MAX_BYTES:
        raise HTTPException(status_code=422, detail="video_upscale_max_40_mb")
    expected_kind = (
        MediaKind.IMAGE
        if task_type == TaskType.IMAGE_UPSCALE
        else MediaKind.VIDEO
    )
    if source.media_kind != expected_kind:
        raise HTTPException(status_code=422, detail="media_kind_mismatch")
    try:
        cost = quote_points(task_type, multiplier, source.duration_seconds)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    task = Task(
        user_id=user.id,
        source_file_id=source.id,
        task_type=task_type,
        multiplier=multiplier,
        status=TaskStatus.QUEUED,
        status_reason="no_worker_online",
        cost_points=cost,
    )
    db.add(task)
    await db.flush()
    attempt = TaskAttempt(task_id=task.id, attempt_number=1)
    db.add(attempt)
    await db.flush()
    task.current_attempt_id = attempt.id
    await apply_credit_entry(
        db,
        user=user,
        task_id=task.id,
        kind="task_reserve",
        available_delta=-cost,
        reserved_delta=cost,
        idempotency_key=f"task_reserve:{task.id}:1",
    )
    return task


async def release_reservation(
    db: AsyncSession, task: Task, *, reason: str
) -> None:
    if task.charged_points or task.status == TaskStatus.SUCCEEDED:
        return
    user = await db.scalar(
        select(User).where(User.id == task.user_id).with_for_update()
    )
    if user is None:
        raise HTTPException(status_code=404, detail="user_not_found")
    await apply_credit_entry(
        db,
        user=user,
        task_id=task.id,
        kind="task_release",
        available_delta=task.cost_points,
        reserved_delta=-task.cost_points,
        idempotency_key=f"task_release:{reason}:{task.id}",
        details={"reason": reason},
    )


async def capture_reservation(db: AsyncSession, task: Task) -> None:
    if task.charged_points:
        return
    user = await db.scalar(
        select(User).where(User.id == task.user_id).with_for_update()
    )
    if user is None:
        raise HTTPException(status_code=404, detail="user_not_found")
    await apply_credit_entry(
        db,
        user=user,
        task_id=task.id,
        kind="task_capture",
        available_delta=0,
        reserved_delta=-task.cost_points,
        idempotency_key=f"task_capture:{task.id}",
    )
    task.charged_points = task.cost_points


async def task_view(db: AsyncSession, task: Task) -> TaskView:
    if task.status == TaskStatus.QUEUED:
        cutoff = datetime.now(timezone.utc) - timedelta(
            seconds=settings.worker_online_seconds
        )
        online = await db.scalar(
            select(func.count())
            .select_from(Worker)
            .where(Worker.enabled.is_(True), Worker.last_seen_at >= cutoff)
        )
        task.status_reason = None if online else "no_worker_online"
    if "attempts" not in task.__dict__:
        task = (
            await db.execute(
                select(Task)
                .where(Task.id == task.id)
                .options(selectinload(Task.attempts))
            )
        ).scalar_one()
    return TaskView(
        id=task.id,
        task_type=task.task_type,
        multiplier=task.multiplier,
        status=task.status,
        status_reason=task.status_reason,
        progress=task.progress,
        cost_points=task.cost_points,
        charged_points=task.charged_points,
        refunded_points=task.refunded_points,
        source_file_id=task.source_file_id,
        output_file_id=task.output_file_id,
        error_code=task.error_code,
        created_at=task.created_at,
        updated_at=task.updated_at,
        attempts=task.attempts,
    )


def add_audit(
    db: AsyncSession,
    *,
    actor_id: str | None,
    action: str,
    target_type: str,
    target_id: str,
    details: dict | None = None,
) -> None:
    db.add(
        AuditLog(
            actor_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            details=details or {},
        )
    )
