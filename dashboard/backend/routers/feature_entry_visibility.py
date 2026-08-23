from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from dashboard.backend.schemas import (
    FeatureEntryVisibilityConfigRequest,
    FeatureEntryVisibilityConfigResponse,
)
from src.database.core import get_db
from src.services.feature_entry_visibility_service import (
    load_feature_entry_visibility_config_payload,
    save_feature_entry_visibility_config_payload,
)


router = APIRouter(prefix="/api/entry-visibility", tags=["entry_visibility"])


@router.get("", response_model=FeatureEntryVisibilityConfigResponse)
async def get_feature_entry_visibility_config(
    db: AsyncSession = Depends(get_db),
):
    return await load_feature_entry_visibility_config_payload(db)


@router.put("", response_model=FeatureEntryVisibilityConfigResponse)
async def update_feature_entry_visibility_config(
    payload: FeatureEntryVisibilityConfigRequest,
    db: AsyncSession = Depends(get_db),
):
    return await save_feature_entry_visibility_config_payload(
        db,
        payload.model_dump(),
    )
