import logging
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from dashboard.backend.schemas import TemplateContributionResponse
from dashboard.backend.services.template_admin_service import (
    approve_contribution_payload,
    delete_contribution_payload,
    get_template_contributions_payload,
)
from src.database.core import get_db

router = APIRouter(prefix="/api/templates", tags=["templates"])
logger = logging.getLogger("dashboard.templates")


@router.get("/contributions", response_model=List[TemplateContributionResponse])
async def get_template_contributions(db: AsyncSession = Depends(get_db)):
    """Get all template contributions with user info"""
    return await get_template_contributions_payload(
        db=db,
        logger_override=logger,
    )


@router.post("/contributions/{contribution_id}/approve")
async def approve_contribution(
    contribution_id: int, db: AsyncSession = Depends(get_db)
):
    """Approve a contribution: move in MinIO and mark as reviewed"""
    return await approve_contribution_payload(
        contribution_id=contribution_id,
        db=db,
        logger_override=logger,
    )


@router.delete("/contributions/{contribution_id}")
async def delete_contribution(contribution_id: int, db: AsyncSession = Depends(get_db)):
    """Reject/Delete a contribution: delete from MinIO and database record"""
    return await delete_contribution_payload(
        contribution_id=contribution_id,
        db=db,
        logger_override=logger,
    )
