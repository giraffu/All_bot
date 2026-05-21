import logging

from fastapi import APIRouter, Query

from src.database.models import GalleryPost
from src.core.media_processor import (
    extract_media_metadata_from_storage,
)
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
    PaginatedHistory,
    PreferencesUpdate,
)
from src.web_api.schemas.gallery_schema import (
    PaginatedGalleryResponse,
    ApplyContextResponse,
)
from src.web_api.routers.utils import (
    build_storage_input_file_url,
    resolve_history_billing_resolution,
)
from src.web_api.presenters.media_presenter import resolve_history_media_urls
from fastapi import BackgroundTasks
from src.web_api.services.history_delivery_service import send_history_record_to_telegram
from src.web_api.services.users_history_service import (
    build_gallery_post_map as service_build_gallery_post_map,
    get_history_apply_context_payload,
    get_my_favorites_payload,
    get_user_history_payload,
    pick_history_media_urls as service_pick_history_media_urls,
    pick_preferred_gallery_post as service_pick_preferred_gallery_post,
)
from src.web_api.services.user_preferences_service import (
    update_user_language_preference,
)
from src.web_api.services.user_profile_service import (
    get_current_user_profile_payload,
    perform_user_checkin,
)
from src.web_api.services.user_affiliate_redeem_api_service import (
    redeem_user_affiliate_credits_payload,
    redeem_user_affiliate_membership_payload,
)
from src.web_api.services.users_history_mutation_service import (
    favorite_user_history,
    soft_delete_user_history,
    unfavorite_user_history,
)

router = APIRouter()
logger = logging.getLogger(__name__)


# Backward-compatible test seam for focused users_* router tests.
async def _pick_history_media_urls(
    *,
    task_id: str | None,
    output_file: str | None,
    history_type: str | None,
) -> tuple[str, str]:  # pyright: ignore[reportUnusedFunction]
    return await service_pick_history_media_urls(
        resolve_history_media_urls=resolve_history_media_urls,
        task_id=task_id,
        output_file=output_file,
        history_type=history_type,
    )


def _pick_preferred_gallery_post(
    posts: list[GalleryPost] | tuple[GalleryPost, ...],
) -> GalleryPost | None:  # pyright: ignore[reportUnusedFunction]
    return service_pick_preferred_gallery_post(posts)


def _build_gallery_post_map(
    posts: list[GalleryPost],
) -> dict[str, GalleryPost]:  # pyright: ignore[reportUnusedFunction]
    return service_build_gallery_post_map(posts)


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
    return await redeem_user_affiliate_credits_payload(
        db=db,
        user_id=current_user.id,
        amount_usdt=payload.amount_usdt,
        idempotency_key=payload.idempotency_key,
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
    return await redeem_user_affiliate_membership_payload(
        db=db,
        user_id=current_user.id,
        option_key=payload.option_key,
        idempotency_key=payload.idempotency_key,
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
    return await update_user_language_preference(
        db=db,
        user_id=current_user.id,
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
    return await get_user_history_payload(
        current_user=current_user,
        db=db,
        resolve_history_media_urls=resolve_history_media_urls,
        limit=8,
    )


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
        background_tasks=background_tasks,
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
        resolve_history_media_urls=resolve_history_media_urls,
        resolve_history_billing_resolution=resolve_history_billing_resolution,
    )


@router.get("/history/{task_id}/apply-context", response_model=ApplyContextResponse)
async def get_favorite_apply_context(
    task_id: str,
    current_user: CurrentUserDep,
    db: DbSessionDep,
):
    return await get_history_apply_context_payload(
        task_id=task_id,
        user_id=current_user.id,
        db=db,
        build_input_file_url=build_storage_input_file_url,
        probe_media_metadata=extract_media_metadata_from_storage,
        logger=logger,
    )


@router.post("/history/{task_id}/send-to-bot")
async def send_history_to_bot(
    task_id: str,
    current_user: CurrentUserDep,
    db: DbSessionDep,
):
    return await send_history_record_to_telegram(
        task_id=task_id,
        current_user=current_user,
        db=db,
    )
