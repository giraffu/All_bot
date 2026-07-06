from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query  # noqa: F401

from .analytics_common import (
    _fetchrow,
    _masked_dsn,
    _media_base_url,
    _media_bucket,
    _row,
)


router = APIRouter()


@router.get("/api/health")
async def health() -> dict[str, Any]:
    row = await _fetchrow("select current_database() as database_name, now() as checked_at")
    return {
        "status": "ok",
        "database": _row(row),
        "database_url": _masked_dsn(),
        "media_bucket": _media_bucket(),
        "media_url_enabled": bool(_media_base_url()),
    }
