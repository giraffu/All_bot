from sqlalchemy import desc, func, select

from dashboard.backend.presenters.worker_admin_presenter import build_worker_history_item
from dashboard.backend.schemas import WorkerHistoryListResponse
from src.database.models import WorkerLog


async def get_worker_list_payload(*, db) -> dict:
    result = await db.execute(select(WorkerLog.worker_id).distinct())
    workers = [row[0] for row in result.all()]
    return {"workers": workers}


async def get_worker_history_payload(*, worker_id: str | None, page: int, size: int, db):
    query = select(WorkerLog)
    if worker_id:
        query = query.where(WorkerLog.worker_id == worker_id)

    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar()
    result = await db.execute(
        query.order_by(desc(WorkerLog.start_time)).offset((page - 1) * size).limit(size)
    )
    logs = result.scalars().all()
    return WorkerHistoryListResponse(
        total=total,
        page=page,
        size=size,
        data=[build_worker_history_item(log) for log in logs],
    )
