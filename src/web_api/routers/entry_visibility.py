from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.core import get_db
from src.services.feature_entry_visibility_service import (
    build_public_entry_visibility_flags,
    load_feature_entry_visibility_config_payload,
)


router = APIRouter(prefix="/api/app", tags=["app"])


@router.get("/entry-visibility")
async def get_public_entry_visibility(
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    payload = await load_feature_entry_visibility_config_payload(db)
    response.headers["Cache-Control"] = "no-store"
    return {"flags": build_public_entry_visibility_flags(payload["config"])}
