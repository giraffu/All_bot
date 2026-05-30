from __future__ import annotations

from sqlalchemy import update as sa_update

from src.database.core import AsyncSessionLocal
from src.database.models import History


async def mark_history_public_by_task_id(task_id: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            sa_update(History).where(History.task_id == task_id).values(is_public=True)
        )
        await session.commit()


async def update_history_rating_by_task_id(task_id: str, rating_value: int) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            sa_update(History)
            .where(History.task_id == task_id)
            .values(rating=rating_value)
        )
        await session.commit()
