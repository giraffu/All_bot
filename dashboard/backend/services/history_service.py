import logging

from fastapi import HTTPException
from sqlalchemy import desc, func, select

from dashboard.backend.presenters.history_presenter import build_history_item_payload
from src.database.models import History, User, WorkerLog
from src.services.storage import storage

logger = logging.getLogger("dashboard.history")


async def get_all_history_payload(
    *,
    db,
    page: int = 1,
    page_size: int = 20,
    type: str | None = None,
    rating: int | None = None,
    is_public: bool | None = None,
    worker_id: str | None = None,
    storage_service=None,
    logger_override: logging.Logger | None = None,
) -> dict:
    active_logger = logger_override or logger
    if storage_service is None:
        storage_service = storage

    try:
        offset = (page - 1) * page_size
        stmt = (
            select(History, User.username, User.full_name, WorkerLog.worker_id)
            .join(User, History.user_id == User.id)
            .outerjoin(WorkerLog, History.task_id == WorkerLog.task_id)
            .order_by(desc(History.created_at))
        )

        if type and type != "all":
            stmt = stmt.where(History.type.in_(type.split(",")))
        if rating is not None:
            stmt = stmt.where(History.rating == rating)
        if is_public is not None:
            stmt = stmt.where(History.is_public == is_public)
        if worker_id is not None and worker_id != "all":
            stmt = stmt.where(WorkerLog.worker_id == worker_id)

        total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
        result = await db.execute(stmt.offset(offset).limit(page_size))

        items = [
            build_history_item_payload(
                history=row[0],
                username=row[1],
                full_name=row[2],
                worker_id=row[3],
                storage_service=storage_service,
            )
            for row in result
        ]
        return {"items": items, "total": total}
    except Exception as exc:
        active_logger.error(f"Error getting all history: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


async def get_user_history_payload(
    *,
    user_id: int,
    db,
    storage_service=None,
    logger_override: logging.Logger | None = None,
) -> list[dict]:
    active_logger = logger_override or logger
    if storage_service is None:
        storage_service = storage

    try:
        stmt = (
            select(History, WorkerLog.worker_id)
            .outerjoin(WorkerLog, History.task_id == WorkerLog.task_id)
            .where(History.user_id == user_id)
            .order_by(desc(History.created_at))
            .limit(100)
        )
        result = await db.execute(stmt)
        return [
            build_history_item_payload(
                history=row[0],
                worker_id=row[1],
                storage_service=storage_service,
            )
            for row in result
        ]
    except Exception as exc:
        active_logger.error(f"Error getting history: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
