from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from src.database.core import AsyncSessionLocal
from src.database.models import OfficialCharacterAssetView, OfficialEnvironmentAsset


async def finalize_official_asset(
    *, task_id: str, status: str, result_path: str | None
) -> None:
    async with AsyncSessionLocal() as db:
        view = (
            await db.execute(
                select(OfficialCharacterAssetView).where(
                    OfficialCharacterAssetView.task_id == task_id
                )
            )
        ).scalar_one_or_none()
        if view is not None:
            if view.status == "ready" and view.object_key:
                return
            view.status = "ready" if status == "done" and result_path else "failed"
            if view.status == "ready":
                view.object_key = result_path
            view.updated_at = datetime.now()
            await db.commit()
            return
        environment = (
            await db.execute(
                select(OfficialEnvironmentAsset).where(
                    OfficialEnvironmentAsset.task_id == task_id
                )
            )
        ).scalar_one_or_none()
        if environment is None or (
            environment.status == "ready" and environment.object_key
        ):
            return
        environment.status = "ready" if status == "done" and result_path else "draft"
        if environment.status == "ready":
            environment.object_key = result_path
        environment.updated_at = datetime.now()
        await db.commit()
