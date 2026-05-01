import logging

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.core import AsyncSessionLocal
from src.database.models import History, User
from src.web_api.dependencies import get_current_user
from src.web_api.schemas.auth_schema import InvitationRechargeStats, UserResponse
from src.web_api.schemas.user_schema import PaginatedHistory, CheckinResponse
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

@router.get("/me", response_model=UserResponse)
async def get_user_profile(current_user: User = Depends(get_current_user)):
    """
    Get current logged in user's profile and credit balance.
    """
    from src.core.user_facade import get_user_dashboard_info
    
    # We pass telegram_id and full_name to the facade.
    dto = await get_user_dashboard_info(
        current_user.telegram_id, 
        current_user.full_name or current_user.username or "道友"
    )
    
    return UserResponse(
        id=current_user.id,
        telegram_id=current_user.telegram_id,
        username=current_user.username,
        full_name=current_user.full_name,
        language_code=current_user.language_code,
        credits=dto.credits,
        user_group=dto.current_group,
        current_identity=dto.current_identity,
        identity_expire_at=dto.identity_expire_at,
        priority=dto.current_priority,
        generation_count=dto.generations,
        checkin_count=dto.checkins,
        invitation_count=dto.invitations,
        invitation_recharge=InvitationRechargeStats(**dto.invitation_recharge),
        breakthrough_conditions=[cond.dict() for cond in dto.breakthrough_conditions],
        is_unlocked=dto.is_unlocked
    )

class PreferencesUpdate(BaseModel):
    language_code: str

@router.patch("/preferences")
async def update_user_preferences(
    prefs: PreferencesUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update user preferences like language_code.
    """
    from src.database.models import User
    from sqlalchemy import update
    
    stmt = (
        update(User)
        .where(User.id == current_user.id)
        .values(language_code=prefs.language_code)
    )
    await db.execute(stmt)
    await db.commit()
    
    # Sync to Redis cache
    from src.services.redis_client import redis_client
    if redis_client and redis_client.redis:
        await redis_client.redis.set(f"allbot:user_lang:{current_user.id}", prefs.language_code)
        
    return {"status": "success", "language_code": prefs.language_code}

@router.get("/history", response_model=PaginatedHistory)
async def get_user_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get generation history for the current user, limited to the 8 most recent items
    to save VPS bandwidth, reduce CDN caching pressure, and protect privacy.
    """
    limit = 8
    
    # Get items
    stmt = (
        select(History)
        .where(History.user_id == current_user.id)
        .order_by(History.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    items = result.scalars().all()
    
    return PaginatedHistory(
        items=list(items),
        total=len(items),
        page=1,
        size=limit
    )

@router.post("/checkin", response_model=CheckinResponse)
async def checkin_user(current_user: User = Depends(get_current_user)):
    """
    Perform daily check-in for the current user.
    """
    from src.services.permission_service import permission_service
    
    success, current_credits, error_msg, total_days, reward = await permission_service.perform_checkin(
        current_user.telegram_id, 
        current_user.username or "", 
        current_user.full_name or ""
    )
    
    return CheckinResponse(
        success=success,
        current_credits=current_credits,
        error_msg=error_msg,
        total_days=total_days,
        reward=reward
    )
