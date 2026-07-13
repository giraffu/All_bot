from __future__ import annotations

from collections.abc import Awaitable, Callable
from logging import Logger

from fastapi import HTTPException


async def run_dashboard_route(
    loader: Callable[[], Awaitable[object]],
    *,
    logger: Logger,
    error_message: str,
):
    try:
        return await loader()
    except Exception as exc:
        logger.error(f"{error_message}: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
