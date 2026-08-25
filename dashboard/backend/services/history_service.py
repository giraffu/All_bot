import asyncio
import logging

from fastapi import HTTPException
from sqlalchemy import desc, func, select

from dashboard.backend.presenters.history_presenter import build_history_item_payload
from src.database.models import History, PrivateBotTaskSubmission, User, WorkerLog
from src.services.qqcc_regenerate_metadata import QQCC_REGENERATE_CONTEXT_KEY
from src.services.storage import storage
from src.web_api.presenters.media_presenter import resolve_history_media_urls

logger = logging.getLogger("dashboard.history")


async def _resolve_history_media_preview(
    *,
    history,
    resolve_media_urls_func,
    active_logger: logging.Logger,
) -> tuple[str | None, str | None]:
    try:
        return await resolve_media_urls_func(
            task_id=history.task_id,
            output_file=history.output_file,
            history_type=history.type,
            r2_lookup_strategy="s3_cached",
        )
    except Exception as exc:
        active_logger.warning(
            "History media preview lookup degraded for task_id=%s: %s",
            history.task_id,
            exc,
        )
        return None, None


async def get_all_history_payload(
    *,
    db,
    page: int = 1,
    page_size: int = 20,
    type: str | None = None,
    rating: int | None = None,
    is_public: bool | None = None,
    worker_id: str | None = None,
    source: str | None = None,
    storage_service=None,
    resolve_media_urls_func=resolve_history_media_urls,
    logger_override: logging.Logger | None = None,
) -> dict:
    active_logger = logger_override or logger
    if storage_service is None:
        storage_service = storage

    try:
        offset = (page - 1) * page_size
        worker_id_value = (
            select(WorkerLog.worker_id)
            .where(WorkerLog.task_id == History.task_id)
            .order_by(WorkerLog.id.desc())
            .limit(1)
            .scalar_subquery()
        )
        private_client_type = (
            select(PrivateBotTaskSubmission.client_type)
            .where(
                PrivateBotTaskSubmission.registry_task_id == History.task_id
            )
            .limit(1)
            .scalar_subquery()
        )
        stmt = (
            select(
                History,
                User.username,
                User.full_name,
                worker_id_value,
                private_client_type,
            )
            .join(User, History.user_id == User.id)
            .order_by(desc(History.created_at))
        )

        filters = []
        if type and type != "all":
            filters.append(History.type.in_(type.split(",")))
        if rating is not None:
            filters.append(History.rating == rating)
        if is_public is not None:
            filters.append(History.is_public == is_public)
        if worker_id is not None and worker_id != "all":
            filters.append(
                select(1)
                .where(
                    WorkerLog.task_id == History.task_id,
                    WorkerLog.worker_id == worker_id,
                )
                .exists()
            )
        qqcc_history = History.extra_outputs[QQCC_REGENERATE_CONTEXT_KEY].is_not(
            None
        )
        private_submission_exists = (
            select(1)
            .where(
                PrivateBotTaskSubmission.registry_task_id == History.task_id
            )
            .exists()
        )
        private_qqcc_history = (
            select(1)
            .where(
                PrivateBotTaskSubmission.registry_task_id == History.task_id,
                PrivateBotTaskSubmission.client_type.startswith(
                    "bot:qqcc-private:"
                ),
            )
            .exists()
        )
        if source == "web":
            filters.append(History.source == "web")
        elif source == "bot":
            filters.extend(
                (
                    History.source == "bot",
                    ~qqcc_history,
                    ~private_submission_exists,
                )
            )
        elif source == "bot:qqcc":
            filters.extend(
                (
                    History.source == "bot",
                    qqcc_history,
                    ~private_submission_exists,
                )
            )
        elif source == "bot:qqcc-private":
            filters.append(private_qqcc_history)
        elif source and source.startswith("bot:qqcc-private:"):
            filters.append(
                select(1)
                .where(
                    PrivateBotTaskSubmission.registry_task_id == History.task_id,
                    PrivateBotTaskSubmission.client_type == source,
                )
                .exists()
            )

        count_stmt = (
            select(func.count(History.id))
            .select_from(History)
            .join(User, History.user_id == User.id)
            .where(*filters)
        )
        total = (await db.execute(count_stmt)).scalar() or 0
        stmt = stmt.where(*filters)
        result = await db.execute(stmt.offset(offset).limit(page_size))
        rows = list(result)
        db.expunge_all()
        await db.rollback()

        media_results = await asyncio.gather(
            *(
                _resolve_history_media_preview(
                    history=row[0],
                    resolve_media_urls_func=resolve_media_urls_func,
                    active_logger=active_logger,
                )
                for row in rows
            )
        )
        items = [
            build_history_item_payload(
                history=row[0],
                username=row[1],
                full_name=row[2],
                worker_id=row[3],
                private_client_type=row[4],
                storage_service=storage_service,
                output_file_url=media_result[0],
                output_file_preview_url=media_result[1],
            )
            for row, media_result in zip(rows, media_results)
        ]
        return {"items": items, "total": total}
    except Exception as exc:
        active_logger.error(f"Error getting all history: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


async def get_user_history_payload(
    *,
    user_id: int,
    page: int = 1,
    page_size: int = 20,
    db,
    storage_service=None,
    resolve_media_urls_func=resolve_history_media_urls,
    logger_override: logging.Logger | None = None,
) -> list[dict]:
    active_logger = logger_override or logger
    if storage_service is None:
        storage_service = storage

    try:
        worker_id = (
            select(WorkerLog.worker_id)
            .where(WorkerLog.task_id == History.task_id)
            .order_by(WorkerLog.id.desc())
            .limit(1)
            .scalar_subquery()
        )
        private_client_type = (
            select(PrivateBotTaskSubmission.client_type)
            .where(
                PrivateBotTaskSubmission.registry_task_id == History.task_id
            )
            .order_by(PrivateBotTaskSubmission.id.desc())
            .limit(1)
            .scalar_subquery()
        )
        total = (
            await db.execute(
                select(func.count(History.id)).where(History.user_id == user_id)
            )
        ).scalar() or 0
        stmt = (
            select(
                History,
                worker_id,
                private_client_type,
            )
            .where(History.user_id == user_id)
            .order_by(desc(History.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await db.execute(stmt)
        rows = list(result)
        db.expunge_all()
        await db.rollback()
        media_results = await asyncio.gather(
            *(
                _resolve_history_media_preview(
                    history=row[0],
                    resolve_media_urls_func=resolve_media_urls_func,
                    active_logger=active_logger,
                )
                for row in rows
            )
        )
        return {
            "items": [
                build_history_item_payload(
                    history=row[0],
                    worker_id=row[1],
                    private_client_type=row[2],
                    storage_service=storage_service,
                    output_file_url=media_result[0],
                    output_file_preview_url=media_result[1],
                )
                for row, media_result in zip(rows, media_results)
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    except Exception as exc:
        active_logger.error(f"Error getting history: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
