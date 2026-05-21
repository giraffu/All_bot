import inspect
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import GalleryPost, History, User
from src.core.media_paths import (
    build_history_r2_media_key,
    build_history_r2_thumbnail_key,
    get_media_type_from_history,
    resolve_storage_object,
)
from src.core.media_urls import (
    build_storage_presigned_url,
)
from src.core.media_processor import (
    extract_media_metadata_from_storage,
    generate_and_upload_thumbnail,
)
from src.services.storage import storage
from src.web_api.presenters.user_presenter import (
    build_user_response_from_dashboard_dto,
)
from src.services.affiliate_redeem_service import (
    AffiliateMembershipRedeemResult,
    AffiliateRedeemConflictError,
    AffiliateRedeemInsufficientBalanceError,
    invalidate_affiliate_redeem_cache_after_commit,
    is_affiliate_membership_redeem_enabled,
    is_membership_settlement_v2_enabled,
    redeem_affiliate_balance_to_credits,
    redeem_affiliate_balance_to_membership,
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
)
from src.web_api.schemas.gallery_schema import (
    PaginatedGalleryResponse,
    ApplyContextResponse,
)
from src.web_api.routers.utils import (
    resolve_history_billing_resolution,
)
from src.web_api.presenters.media_presenter import resolve_history_media_urls
from fastapi import HTTPException, BackgroundTasks
from pydantic import BaseModel
from src.web_api.services.history_delivery_service import send_history_record_to_telegram
from src.web_api.services.users_history_service import (
    build_gallery_post_map as service_build_gallery_post_map,
    get_history_apply_context_payload,
    get_my_favorites_payload,
    get_user_history_payload,
    pick_history_media_urls as service_pick_history_media_urls,
    pick_preferred_gallery_post as service_pick_preferred_gallery_post,
)

router = APIRouter()
logger = logging.getLogger(__name__)


from src.web_api.dependencies import get_current_user, get_db

CurrentUserDep = Annotated[User, Depends(get_current_user)]
DbSessionDep = Annotated[AsyncSession, Depends(get_db)]


async def _pick_favorite_media_urls(
    *,
    task_id: str | None,
    output_file: str | None,
    history_type: str | None,
) -> tuple[str, str]:
    return await service_pick_history_media_urls(
        resolve_history_media_urls=resolve_history_media_urls,
        task_id=task_id,
        output_file=output_file,
        history_type=history_type,
    )


async def _pick_history_media_urls(
    *,
    task_id: str | None,
    output_file: str | None,
    history_type: str | None,
) -> tuple[str, str]:
    return await service_pick_history_media_urls(
        resolve_history_media_urls=resolve_history_media_urls,
        task_id=task_id,
        output_file=output_file,
        history_type=history_type,
    )


def _pick_preferred_gallery_post(
    posts: list[GalleryPost] | tuple[GalleryPost, ...],
) -> GalleryPost | None:
    return service_pick_preferred_gallery_post(posts)


def _build_gallery_post_map(posts: list[GalleryPost]) -> dict[str, GalleryPost]:
    return service_build_gallery_post_map(posts)


@router.get("/me", response_model=UserResponse)
async def get_user_profile(current_user: User = Depends(get_current_user)):
    """
    Get current logged in user's profile and credit balance.
    """
    from src.core.user_facade import get_user_dashboard_info

    # We pass telegram_id and full_name to the facade.
    dto = await get_user_dashboard_info(
        current_user.telegram_id,
        current_user.full_name or current_user.username or "道友",
    )
    return build_user_response_from_dashboard_dto(current_user, dto)


@router.post(
    "/me/affiliate/redeem-credits",
    response_model=AffiliateCreditsRedeemResponse,
)
async def redeem_current_user_affiliate_credits(
    payload: AffiliateCreditsRedeemRequest,
    current_user: CurrentUserDep,
    db: DbSessionDep,
) -> AffiliateCreditsRedeemResponse:
    user_id = current_user.id
    committed_here = False

    try:
        result = await redeem_affiliate_balance_to_credits(
            db,
            user_id=user_id,
            amount_usdt=payload.amount_usdt,
            idempotency_key=payload.idempotency_key,
        )
        in_transaction = db.in_transaction()
        if inspect.isawaitable(in_transaction):
            in_transaction = await in_transaction
        if in_transaction:
            await db.commit()
            committed_here = True
    except AffiliateRedeemConflictError as exc:
        raise HTTPException(
            status_code=409, detail="同一幂等键已被不同兑换参数占用"
        ) from exc
    except AffiliateRedeemInsufficientBalanceError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "返佣可用余额不足",
                "available_balance_usdt": float(exc.available_balance_usdt),
                "requested_amount_usdt": float(exc.requested_amount_usdt),
            },
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if committed_here:
        await invalidate_affiliate_redeem_cache_after_commit(user_id)

    return AffiliateCreditsRedeemResponse(
        redeem_id=result.redeem_id,
        redeem_type=result.redeem_type,
        amount_usdt=float(result.amount_usdt),
        credits_granted=result.credits_granted,
        status=result.status,
        idempotency_key=result.idempotency_key,
        available_balance_usdt=float(result.available_balance_usdt),
        current_credits=result.current_credits,
        exchange_rate_snapshot=result.exchange_rate_snapshot,
        rounding_mode=result.rounding_mode,
    )


def _to_membership_redeem_response(
    result: AffiliateMembershipRedeemResult,
) -> AffiliateMembershipRedeemResponse:
    return AffiliateMembershipRedeemResponse(
        redeem_id=result.redeem_id,
        redeem_type=result.redeem_type,
        option_key=result.option_key,
        target_plan_id=result.target_plan_id,
        target_identity=result.target_identity,
        duration_days=result.duration_days,
        amount_usdt=f"{result.amount_usdt:.4f}",
        credits_granted=result.credits_granted,
        status=result.status,
        idempotency_key=result.idempotency_key,
        available_balance_usdt=f"{result.available_balance_usdt:.4f}",
        current_identity=result.current_identity,
        identity_expire_at=result.identity_expire_at,
        current_credits=result.current_credits,
        converted_days=result.converted_days,
        settlement_reason=result.settlement_reason,
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
    if not (
        is_membership_settlement_v2_enabled()
        and is_affiliate_membership_redeem_enabled()
    ):
        raise HTTPException(status_code=404, detail="返佣兑换身份功能未开启")

    user_id = current_user.id
    committed_here = False

    try:
        result = await redeem_affiliate_balance_to_membership(
            db,
            user_id=user_id,
            option_key=payload.option_key,
            idempotency_key=payload.idempotency_key,
        )
        in_transaction = db.in_transaction()
        if inspect.isawaitable(in_transaction):
            in_transaction = await in_transaction
        if in_transaction:
            await db.commit()
            committed_here = True
    except AffiliateRedeemConflictError as exc:
        raise HTTPException(
            status_code=409, detail="同一幂等键已被不同兑换参数占用"
        ) from exc
    except AffiliateRedeemInsufficientBalanceError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "返佣可用余额不足",
                "available_balance_usdt": float(exc.available_balance_usdt),
                "requested_amount_usdt": float(exc.requested_amount_usdt),
            },
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if committed_here:
        await invalidate_affiliate_redeem_cache_after_commit(user_id)

    return _to_membership_redeem_response(result)


class PreferencesUpdate(BaseModel):
    language_code: str


@router.patch("/preferences")
async def update_user_preferences(
    prefs: PreferencesUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
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
        await redis_client.redis.set(
            f"allbot:user_lang:{current_user.id}", prefs.language_code
        )

    return {"status": "success", "language_code": prefs.language_code}


@router.get("/history", response_model=PaginatedHistory)
async def get_user_history(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
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
async def checkin_user(current_user: User = Depends(get_current_user)):
    """
    Perform daily check-in for the current user.
    """
    from src.services.permission_service import permission_service

    (
        success,
        current_credits,
        error_msg,
        total_days,
        reward,
    ) = await permission_service.perform_checkin(
        current_user.telegram_id,
        current_user.username or "",
        current_user.full_name or "",
    )

    return CheckinResponse(
        success=success,
        current_credits=current_credits,
        error_msg=error_msg,
        total_days=total_days,
        reward=reward,
    )


@router.post("/history/{task_id}/favorite")
async def favorite_history(
    task_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(History).where(
        History.task_id == task_id, History.user_id == current_user.id
    )
    result = await db.execute(stmt)
    history = result.scalar_one_or_none()

    if not history:
        raise HTTPException(status_code=404, detail="未找到原任务详情")

    if not history.output_file:
        raise HTTPException(status_code=400, detail="该任务没有生成文件")

    if not history.is_favorited:
        history.is_favorited = True
        await db.commit()

        # 触发 R2 上传
        from src.core.gallery_core import async_copy_to_r2_background

        bucket_name, object_name = resolve_storage_object(history.output_file)
        media_type = get_media_type_from_history(history.type)
        r2_object_name = build_history_r2_media_key(history.task_id, history.output_file)

        background_tasks.add_task(
            async_copy_to_r2_background, bucket_name, object_name, r2_object_name
        )
        background_tasks.add_task(
            generate_and_upload_thumbnail,
            history.output_file,
            media_type,
            build_history_r2_thumbnail_key(history.task_id, media_type),
        )

    return {"status": "success", "message": "收藏成功"}


@router.delete("/history/{task_id}/favorite")
async def unfavorite_history(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(History).where(
        History.task_id == task_id, History.user_id == current_user.id
    )
    result = await db.execute(stmt)
    history = result.scalar_one_or_none()

    if not history:
        raise HTTPException(status_code=404, detail="未找到原任务详情")

    if history.is_favorited:
        history.is_favorited = False
        await db.commit()

    return {"status": "success", "message": "已取消收藏"}


@router.delete("/history/{history_id}")
async def delete_history(
    history_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import update
    from src.database.models import GalleryPost

    stmt = select(History).where(
        History.id == history_id, History.user_id == current_user.id
    )
    result = await db.execute(stmt)
    history = result.scalar_one_or_none()

    if not history:
        raise HTTPException(status_code=404, detail="未找到对应的记录")

    if not history.is_visible:
        return {"status": "success", "message": "记录已删除"}

    # Soft delete in history
    history.is_visible = False

    # If it was public and has a task_id, also hide the gallery post
    if history.is_public and history.task_id:
        upd_stmt = (
            update(GalleryPost)
            .where(
                GalleryPost.task_id == history.task_id,
                GalleryPost.user_id == current_user.id,
                GalleryPost.is_active == True,
            )
            .values(is_active=False)
        )
        upd_result = await db.execute(upd_stmt)

        if upd_result.rowcount > 0:
            current_user.total_contributions = max(
                current_user.total_contributions - 1, 0
            )

    await db.commit()
    return {"status": "success", "message": "记录已删除"}


@router.get("/my-favorites", response_model=PaginatedGalleryResponse)
async def get_my_favorites(
    page: int = 1,
    size: int = 20,
    task_type: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
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
        build_input_file_url=lambda file_path: build_storage_presigned_url(
            file_path,
            lambda object_name, bucket_name: storage.get_presigned_url(
                object_name, bucket=bucket_name
            ),
        ),
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
