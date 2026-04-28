import logging

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.core import AsyncSessionLocal
from src.database.models import History, User
from src.web_api.dependencies import get_current_user
from src.web_api.schemas.auth_schema import InvitationRechargeStats, UserResponse
from src.web_api.schemas.user_schema import PaginatedHistory

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
    # Use PermissionService to get real-time calculated stats
    from src.services.permission_service import permission_service
    stats = await permission_service.get_user_detailed_stats(current_user.telegram_id)
    
    # Map stats to UserResponse
    # stats returned by get_user_detailed_stats:
    # "group", "identity", "identity_expire_at", "priority", "credits", "invitations",
    # "checkins", "generations", "total_contributions", "approved_contributions", "invitation_recharge"
    
    return UserResponse(
        id=current_user.id,
        telegram_id=current_user.telegram_id,
        username=current_user.username,
        full_name=current_user.full_name,
        credits=stats.get("credits", current_user.credits),
        user_group=stats.get("group", current_user.user_group),
        current_identity=stats.get("identity", current_user.current_identity),
        identity_expire_at=stats.get("identity_expire_at"),
        priority=stats.get("priority", 0),
        generation_count=stats.get("generations", 0),
        checkin_count=stats.get("checkins", 0),
        invitation_count=stats.get("invitations", 0),
        invitation_recharge=InvitationRechargeStats(**stats.get("invitation_recharge", {}))
    )

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
