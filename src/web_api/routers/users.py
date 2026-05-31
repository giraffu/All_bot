from fastapi import APIRouter, Query
from src.web_api.dependencies import (
    CurrentUserDep,
    DbSessionDep,
)
from src.web_api.schemas.affiliate_redeem_schema import (
    AffiliateCreditsRedeemRequest,
    AffiliateCreditsRedeemResponse,
    AffiliateMembershipRedeemRequest,
    AffiliateMembershipRedeemResponse,
)
from src.web_api.schemas.auth_schema import UserResponse
from src.web_api.schemas.user_schema import (
    CheckinResponse,
    HistoryItem,
    PaginatedHistory,
    PreferencesUpdate,
    Wan22HistoryChainResponse,
)
from src.web_api.schemas.gallery_schema import (
    PaginatedGalleryResponse,
    ApplyContextResponse,
)
from fastapi import BackgroundTasks
from src.web_api.services.history_delivery_service import (
    send_current_user_history_record_to_telegram,
)
from src.web_api.services.users_history_service import (
    get_default_user_history_payload,
    get_history_apply_context_for_current_user,
    get_my_favorites_payload,
)
from src.web_api.services.wan22_history_chain_service import (
    get_wan22_history_chain_payload,
    stitch_wan22_history_chain_response,
)
from src.web_api.services.user_social_service import (
    follow_user_payload,
    get_my_following_payload,
    get_public_user_profile_payload,
    unfollow_user_payload,
)
from src.web_api.services.user_affiliate_redeem_api_service import (
    redeem_current_user_affiliate_credits_payload,
    redeem_current_user_affiliate_membership_payload,
)
from src.web_api.services.users_history_mutation_service import (
    favorite_user_history,
    soft_delete_user_history,
    unfavorite_user_history,
)
from src.web_api.services.user_task_api_service import (
    get_current_user_profile_payload,
    perform_user_checkin,
    update_user_language_preference_payload,
)
from src.web_api.schemas.user_social_schema import (
    FollowActionResponse,
    FollowingListResponse,
    PublicUserProfileResponse,
)

router = APIRouter()
__all__ = ["router"]


@router.get("/me", response_model=UserResponse)
async def get_user_profile(current_user: CurrentUserDep):
    """
    Get current logged in user's profile and credit balance.
    """
    return await get_current_user_profile_payload(current_user)


@router.post(
    "/me/affiliate/redeem-credits",
    response_model=AffiliateCreditsRedeemResponse,
)
async def redeem_current_user_affiliate_credits(
    payload: AffiliateCreditsRedeemRequest,
    current_user: CurrentUserDep,
    db: DbSessionDep,
) -> AffiliateCreditsRedeemResponse:
    return await redeem_current_user_affiliate_credits_payload(
        payload=payload,
        current_user=current_user,
        db=db,
    )


@router.post(
    "/me/affiliate/redeem-membership",
    response_model=AffiliateMembershipRedeemResponse,
)
async def redeem_current_user_affiliate_membership(
    payload: AffiliateMembershipRedeemRequest,
    current_user: CurrentUserDep,
    db: DbSessionDep,
) -> AffiliateMembershipRedeemResponse:
    return await redeem_current_user_affiliate_membership_payload(
        payload=payload,
        current_user=current_user,
        db=db,
    )


@router.patch("/preferences")
async def update_user_preferences(
    prefs: PreferencesUpdate,
    current_user: CurrentUserDep,
    db: DbSessionDep,
):
    """
    Update user preferences like language_code.
    """
    return await update_user_language_preference_payload(
        db=db,
        user_id=current_user.id,
        telegram_user_id=current_user.telegram_id,
        language_code=prefs.language_code,
    )


@router.get("/history", response_model=PaginatedHistory)
async def get_user_history(
    current_user: CurrentUserDep,
    db: DbSessionDep,
):
    """
    Get generation history for the current user, limited to the 8 most recent items
    to save VPS bandwidth, reduce CDN caching pressure, and protect privacy.
    """
    return await get_default_user_history_payload(current_user=current_user, db=db)


@router.post("/checkin", response_model=CheckinResponse)
async def checkin_user(current_user: CurrentUserDep):
    """
    Perform daily check-in for the current user.
    """
    return await perform_user_checkin(current_user)


@router.post("/history/{task_id}/favorite")
async def favorite_history(
    task_id: str,
    background_tasks: BackgroundTasks,
    current_user: CurrentUserDep,
    db: DbSessionDep,
):
    return await favorite_user_history(
        task_id=task_id,
        current_user=current_user,
        db=db,
        schedule_background_task=getattr(background_tasks, "add_task", None),
    )


@router.delete("/history/{task_id}/favorite")
async def unfavorite_history(
    task_id: str,
    current_user: CurrentUserDep,
    db: DbSessionDep,
):
    return await unfavorite_user_history(
        task_id=task_id,
        current_user=current_user,
        db=db,
    )


@router.delete("/history/{history_id}")
async def delete_history(
    history_id: int,
    current_user: CurrentUserDep,
    db: DbSessionDep,
):
    return await soft_delete_user_history(
        history_id=history_id,
        current_user=current_user,
        db=db,
    )


@router.get("/my-favorites", response_model=PaginatedGalleryResponse)
async def get_my_favorites(
    current_user: CurrentUserDep,
    db: DbSessionDep,
    page: int = 1,
    size: int = 20,
    task_type: str | None = Query(default=None),
):
    return await get_my_favorites_payload(
        page=page,
        size=size,
        task_type=task_type,
        current_user=current_user,
        db=db,
    )


@router.get("/me/follows", response_model=FollowingListResponse)
async def get_my_following(
    current_user: CurrentUserDep,
    db: DbSessionDep,
):
    return await get_my_following_payload(current_user=current_user, db=db)


@router.get("/{user_id}/public-profile", response_model=PublicUserProfileResponse)
async def get_public_user_profile(
    user_id: int,
    current_user: CurrentUserDep,
    db: DbSessionDep,
):
    return await get_public_user_profile_payload(
        target_user_id=user_id,
        current_user=current_user,
        db=db,
    )


@router.post("/{user_id}/follow", response_model=FollowActionResponse)
async def follow_user(
    user_id: int,
    current_user: CurrentUserDep,
    db: DbSessionDep,
):
    return await follow_user_payload(
        target_user_id=user_id,
        current_user=current_user,
        db=db,
    )


@router.delete("/{user_id}/follow", response_model=FollowActionResponse)
async def unfollow_user(
    user_id: int,
    current_user: CurrentUserDep,
    db: DbSessionDep,
):
    return await unfollow_user_payload(
        target_user_id=user_id,
        current_user=current_user,
        db=db,
    )


@router.get("/history/{task_id}/apply-context", response_model=ApplyContextResponse)
async def get_favorite_apply_context(
    task_id: str,
    current_user: CurrentUserDep,
    db: DbSessionDep,
):
    return await get_history_apply_context_for_current_user(
        task_id=task_id,
        current_user=current_user,
        db=db,
    )


@router.post("/history/{task_id}/send-to-bot")
async def send_history_to_bot(
    task_id: str,
    current_user: CurrentUserDep,
    db: DbSessionDep,
):
    return await send_current_user_history_record_to_telegram(
        task_id=task_id,
        current_user=current_user,
        db=db,
    )


@router.get("/history/{task_id}/wan22-chain", response_model=Wan22HistoryChainResponse)
async def get_wan22_history_chain(
    task_id: str,
    current_user: CurrentUserDep,
    db: DbSessionDep,
):
    return await get_wan22_history_chain_payload(
        task_id=task_id,
        current_user=current_user,
        db=db,
    )


@router.post("/history/{task_id}/wan22-chain/stitch", response_model=HistoryItem)
async def stitch_wan22_history_chain(
    task_id: str,
    current_user: CurrentUserDep,
    db: DbSessionDep,
):
    return await stitch_wan22_history_chain_response(
        task_id=task_id,
        current_user=current_user,
        db=db,
    )
