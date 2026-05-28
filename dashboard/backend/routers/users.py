import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from dashboard.backend.schemas import (
    AdminGiftRequest,
    UpdateCreditsRequest,
    UpdateIdentityRequest,
    UpdateGroupRequest,
    UpdateChannelMemberRequest,
)
from dashboard.backend.services.user_admin_service import (
    admin_gift_plan_payload,
    clear_user_history_payload,
    delete_user_payload,
    get_user_favorites_payload,
    get_user_stats_payload,
    get_users_payload,
    update_user_channel_member_payload,
    update_user_credits_payload,
    update_user_group_payload,
    update_user_identity_payload,
)
from src.database.core import get_db
from src.web_api.schemas.gallery_schema import PaginatedGalleryResponse

router = APIRouter(prefix="/api/users", tags=["users"])
logger = logging.getLogger("dashboard.users")


@router.get("")
async def get_users(
    skip: int = 0,
    limit: int = 20,
    query: str = None,
    query_partial: bool = True,
    identity: str = None,
    user_group: str = None,
    username: str = None,
    username_partial: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Get paginated user list with basic info"""
    return await get_users_payload(
        db=db,
        skip=skip,
        limit=limit,
        query=query,
        query_partial=query_partial,
        identity=identity,
        user_group=user_group,
        username=username,
        username_partial=username_partial,
        logger_override=logger,
    )


@router.get("/{user_id}/stats")
async def get_user_stats(user_id: int, db: AsyncSession = Depends(get_db)):
    """Get detailed heavy stats for a specific user"""
    return await get_user_stats_payload(user_id=user_id, db=db, logger_override=logger)


@router.get("/{user_id}/favorites", response_model=PaginatedGalleryResponse)
async def get_user_favorites(
    user_id: int,
    page: int = 1,
    size: int = 12,
    task_type: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Get a user's favorites using the same payload builder as the Web favorites page."""
    return await get_user_favorites_payload(
        user_id=user_id,
        page=page,
        size=size,
        task_type=task_type,
        db=db,
        logger_override=logger,
    )


@router.delete("/{user_id}")
async def delete_user(user_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a user and all their associated data from the database"""
    return await delete_user_payload(user_id=user_id, db=db, logger_override=logger)


@router.post("/{user_id}/credits")
async def update_user_credits(
    user_id: int, request: UpdateCreditsRequest, db: AsyncSession = Depends(get_db)
):
    """Update user credits and checkin count"""
    return await update_user_credits_payload(
        user_id=user_id,
        request=request,
        db=db,
        logger_override=logger,
    )


@router.delete("/{user_id}/history")
async def clear_user_history(user_id: int, db: AsyncSession = Depends(get_db)):
    """Clear user history (database records and files)"""
    return await clear_user_history_payload(user_id=user_id, db=db, logger_override=logger)


@router.post("/{user_id}/gift")
async def admin_gift_plan(
    user_id: int, request: AdminGiftRequest, db: AsyncSession = Depends(get_db)
):
    """Manually gift a membership plan to a user"""
    return await admin_gift_plan_payload(
        user_id=user_id,
        request=request,
        db=db,
        logger_override=logger,
    )


@router.post("/{user_id}/identity")
async def update_user_identity(
    user_id: int, request: UpdateIdentityRequest, db: AsyncSession = Depends(get_db)
):
    """Update user identity and expiration date with optional value conversion"""
    return await update_user_identity_payload(
        user_id=user_id,
        request=request,
        db=db,
        logger_override=logger,
    )


@router.post("/{user_id}/group")
async def update_user_group(
    user_id: int, request: UpdateGroupRequest, db: AsyncSession = Depends(get_db)
):
    """Update user group (修为)"""
    return await update_user_group_payload(
        user_id=user_id,
        request=request,
        db=db,
        logger_override=logger,
    )


@router.post("/{user_id}/channel_member")
async def update_user_channel_member(
    user_id: int,
    request: UpdateChannelMemberRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update user channel member status (已入宗门)"""
    return await update_user_channel_member_payload(
        user_id=user_id,
        request=request,
        db=db,
        logger_override=logger,
    )
