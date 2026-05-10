from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.core import get_db
from src.database.models import WorkerLog

router = APIRouter(prefix="/api/workers", tags=["workers"])


@router.get("/list")
async def get_worker_list(db: AsyncSession = Depends(get_db)):
    """Get a list of all unique worker IDs"""
    result = await db.execute(select(WorkerLog.worker_id).distinct())
    workers = [row[0] for row in result.all()]
    return {"workers": workers}


@router.get("/history")
async def get_worker_history(
    worker_id: Optional[str] = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get worker history with pagination and optional filtering by worker_id"""
    query = select(WorkerLog)

    if worker_id:
        query = query.where(WorkerLog.worker_id == worker_id)

    # Count total records
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Get paginated data
    query = query.order_by(desc(WorkerLog.start_time))
    query = query.offset((page - 1) * size).limit(size)

    result = await db.execute(query)
    logs = result.scalars().all()

    return {
        "total": total,
        "page": page,
        "size": size,
        "data": [
            {
                "id": log.id,
                "worker_id": log.worker_id,
                "task_id": log.task_id,
                "task_type": log.task_type,
                "status": log.status,
                "start_time": log.start_time.isoformat() if log.start_time else None,
                "end_time": log.end_time.isoformat() if log.end_time else None,
                "duration": log.duration,
                "error_message": log.error_message,
            }
            for log in logs
        ],
    }
