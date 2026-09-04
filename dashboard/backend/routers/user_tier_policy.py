from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from dashboard.backend.schemas import (
    UserTierPolicyConfigRequest,
    UserTierPolicyConfigResponse,
)
from src.database.core import get_db
from src.services.user_tier_policy_service import (
    load_user_tier_policy_config_payload,
    save_user_tier_policy_config_payload,
)


router = APIRouter(prefix="/api/user-tier-policy", tags=["user_tier_policy"])


@router.get("", response_model=UserTierPolicyConfigResponse)
async def get_user_tier_policy_config(db: AsyncSession = Depends(get_db)):
    return await load_user_tier_policy_config_payload(db)


@router.put("", response_model=UserTierPolicyConfigResponse)
async def update_user_tier_policy_config(
    payload: UserTierPolicyConfigRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await save_user_tier_policy_config_payload(db, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
