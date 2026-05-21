from collections.abc import Awaitable, Callable
from typing import TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.media_urls import build_storage_presigned_url
from src.services.storage import storage
from src.web_api.services.apply_context_service import (
    build_apply_context_response,
    build_history_apply_context_response,
    probe_apply_context_media_metadata,
    resolve_apply_context_media_metadata,
    resolve_history_billing_resolution,
)

T = TypeVar("T")

__all__ = [
    "build_apply_context_response",
    "build_history_apply_context_response",
    "probe_apply_context_media_metadata",
    "resolve_apply_context_media_metadata",
    "resolve_history_billing_resolution",
    "build_storage_input_file_url",
    "run_with_optional_db",
    "call_with_optional_db",
]


def build_storage_input_file_url(file_path: str | None) -> str | None:
    return build_storage_presigned_url(
        file_path,
        lambda object_name, bucket_name: storage.get_presigned_url(
            object_name,
            bucket=bucket_name,
        ),
    )


async def run_with_optional_db(
    *,
    db: AsyncSession | None,
    action: Callable[[AsyncSession], Awaitable[T]],
    session_factory: Callable[[], AsyncSession],
) -> T:
    if db is not None:
        return await action(db)

    async with session_factory() as fallback_db:
        return await action(fallback_db)


async def call_with_optional_db(
    *,
    db: AsyncSession | None,
    service_fn: Callable[..., Awaitable[T]],
    session_factory: Callable[[], AsyncSession],
    session_kwarg: str = "db",
    **kwargs,
) -> T:
    async def _action(session: AsyncSession) -> T:
        return await service_fn(**{session_kwarg: session, **kwargs})

    return await run_with_optional_db(
        db=db,
        action=_action,
        session_factory=session_factory,
    )
