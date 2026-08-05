from __future__ import annotations

import hmac
import os
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.core import get_db
from src.services.media_archive_service import (
    claim_archive_jobs,
    record_archive_failure,
    record_archive_receipts,
)


router = APIRouter()


def require_archive_agent(
    authorization: str | None = Header(default=None),
) -> str:
    expected = os.getenv("MEDIA_ARCHIVE_AGENT_TOKEN", "").strip()
    supplied = (authorization or "").removeprefix("Bearer ").strip()
    if not expected:
        raise HTTPException(
            status_code=503, detail="media archive agent token is not configured"
        )
    if not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="invalid media archive agent token")
    return supplied


class ReceiptItem(BaseModel):
    role: str = Field(max_length=64)
    ordinal: int = Field(ge=0)
    source_ref: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    byte_size: int = Field(ge=0)
    mime_type: str | None = Field(default=None, max_length=128)
    nas_bucket: str = Field(max_length=128)
    nas_key: str
    verified_at: datetime


class ReceiptsRequest(BaseModel):
    history_id: int
    worker_id: str = Field(min_length=1, max_length=128)
    receipts: list[ReceiptItem]


class FailureRequest(BaseModel):
    history_id: int
    worker_id: str = Field(min_length=1, max_length=128)
    error_code: str = Field(min_length=1, max_length=64)
    message: str = Field(max_length=1000)
    retryable: bool = True


@router.get("/jobs", dependencies=[Depends(require_archive_agent)])
async def get_jobs(
    worker_id: str = Query(min_length=1, max_length=128),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    return {"jobs": await claim_archive_jobs(db, worker_id=worker_id, limit=limit)}


@router.post("/receipts", dependencies=[Depends(require_archive_agent)])
async def post_receipts(payload: ReceiptsRequest, db: AsyncSession = Depends(get_db)):
    try:
        complete = await record_archive_receipts(
            db,
            history_id=payload.history_id,
            worker_id=payload.worker_id,
            receipts=[item.model_dump() for item in payload.receipts],
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"accepted": True, "archive_complete": complete}


@router.post("/failures", dependencies=[Depends(require_archive_agent)])
async def post_failure(payload: FailureRequest, db: AsyncSession = Depends(get_db)):
    try:
        await record_archive_failure(db, **payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"accepted": True}
