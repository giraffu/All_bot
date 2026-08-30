import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

from fastapi import HTTPException
from sqlalchemy import desc, func, select

from dashboard.backend.presenters.history_presenter import build_history_item_payload
from src.database.models import History, PrivateBotTaskSubmission, User, WorkerLog
from src.services.qqcc_regenerate_metadata import QQCC_REGENERATE_CONTEXT_KEY
from src.services.storage import storage
from src.web_api.presenters.media_presenter import resolve_history_media_urls

logger = logging.getLogger("dashboard.history")
HistoryCountCacheKey = tuple[object, ...]


class HistoryCountCache:
    """Short-lived exact totals; history rows themselves are never cached."""

    def __init__(self, *, ttl_seconds: int = 300, max_items: int = 128):
        self._ttl_seconds = ttl_seconds
        self._max_items = max_items
        self._values: dict[HistoryCountCacheKey, tuple[float, int]] = {}
        self._locks: dict[HistoryCountCacheKey, asyncio.Lock] = {}

    def _get_lock(self, cache_key: HistoryCountCacheKey) -> asyncio.Lock:
        lock = self._locks.get(cache_key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[cache_key] = lock
        return lock

    def _store(self, cache_key: HistoryCountCacheKey, value: int) -> int:
        now = time.monotonic()
        if len(self._values) >= self._max_items and cache_key not in self._values:
            expired_keys = [
                key for key, (expires_at, _) in self._values.items()
                if expires_at <= now
            ]
            for key in expired_keys:
                self._values.pop(key, None)
                self._locks.pop(key, None)
            if len(self._values) >= self._max_items:
                oldest_key = min(
                    self._values,
                    key=lambda key: self._values[key][0],
                )
                self._values.pop(oldest_key, None)
                self._locks.pop(oldest_key, None)
        self._values[cache_key] = (now + self._ttl_seconds, value)
        return value

    async def get_or_load(
        self,
        cache_key: HistoryCountCacheKey,
        loader: Callable[[], Awaitable[int]],
    ) -> int:
        now = time.monotonic()
        cached = self._values.get(cache_key)
        if cached and cached[0] > now:
            return cached[1]

        async with self._get_lock(cache_key):
            now = time.monotonic()
            cached = self._values.get(cache_key)
            if cached and cached[0] > now:
                return cached[1]
            return self._store(cache_key, await loader())

    async def refresh(
        self,
        cache_key: HistoryCountCacheKey,
        loader: Callable[[], Awaitable[int]],
    ) -> int:
        async with self._get_lock(cache_key):
            return self._store(cache_key, await loader())


def _history_count_cache_key(
    *,
    type: str | None,
    rating: int | None,
    is_public: bool | None,
    worker_id: str | None,
    source: str | None,
    username: str | None,
) -> HistoryCountCacheKey:
    type_key = (
        tuple(sorted(type.split(","))) if type and type != "all" else ()
    )
    worker_key = worker_id if worker_id and worker_id != "all" else ""
    username_key = (username or "").strip().lstrip("@").lower()
    return (type_key, rating, is_public, worker_key, source or "", username_key)


def _build_history_filters(
    *,
    type: str | None,
    rating: int | None,
    is_public: bool | None,
    worker_id: str | None,
    source: str | None,
    username: str | None,
) -> list:
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
    normalized_username = (username or "").strip().lstrip("@")
    if normalized_username:
        filters.append(func.lower(User.username) == normalized_username.lower())
    qqcc_history = History.extra_outputs[QQCC_REGENERATE_CONTEXT_KEY].is_not(None)
    private_submission_exists = (
        select(1)
        .where(PrivateBotTaskSubmission.registry_task_id == History.task_id)
        .exists()
    )
    private_qqcc_history = (
        select(1)
        .where(
            PrivateBotTaskSubmission.registry_task_id == History.task_id,
            PrivateBotTaskSubmission.client_type.startswith("bot:qqcc-private:"),
        )
        .exists()
    )
    if source == "web":
        filters.append(History.source == "web")
    elif source == "bot":
        filters.extend(
            (History.source == "bot", ~qqcc_history, ~private_submission_exists)
        )
    elif source == "bot:qqcc":
        filters.extend(
            (History.source == "bot", qqcc_history, ~private_submission_exists)
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
    return filters


async def _load_history_count(*, db, filters: list) -> int:
    count_stmt = (
        select(func.count(History.id))
        .select_from(History)
        .join(User, History.user_id == User.id)
        .where(*filters)
    )
    return (await db.execute(count_stmt)).scalar() or 0


async def refresh_default_history_count_cache(
    *, count_cache: HistoryCountCache, session_factory
) -> int:
    cache_key = _history_count_cache_key(
        type=None,
        rating=None,
        is_public=None,
        worker_id=None,
        source=None,
        username=None,
    )
    async with session_factory() as db:
        total = await count_cache.refresh(
            cache_key,
            lambda: _load_history_count(db=db, filters=[]),
        )
        await db.rollback()
        return total


async def run_history_count_cache_warmer(
    *,
    count_cache: HistoryCountCache,
    session_factory,
    refresh_interval_seconds: int = 240,
    retry_interval_seconds: int = 30,
    logger_override: logging.Logger | None = None,
) -> None:
    active_logger = logger_override or logger
    while True:
        delay_seconds = refresh_interval_seconds
        try:
            total = await refresh_default_history_count_cache(
                count_cache=count_cache,
                session_factory=session_factory,
            )
            active_logger.info(
                "Dashboard history count cache warmed: total=%s", total
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            delay_seconds = retry_interval_seconds
            active_logger.warning(
                "Dashboard history count cache warm failed: %s", exc
            )
        await asyncio.sleep(delay_seconds)


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
    username: str | None = None,
    count_cache: HistoryCountCache | None = None,
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

        filters = _build_history_filters(
            type=type,
            rating=rating,
            is_public=is_public,
            worker_id=worker_id,
            source=source,
            username=username,
        )
        if count_cache is None:
            total = await _load_history_count(db=db, filters=filters)
        else:
            cache_key = _history_count_cache_key(
                type=type,
                rating=rating,
                is_public=is_public,
                worker_id=worker_id,
                source=source,
                username=username,
            )
            total = await count_cache.get_or_load(
                cache_key,
                lambda: _load_history_count(db=db, filters=filters),
            )
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
