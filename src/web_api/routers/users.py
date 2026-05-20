import asyncio
import inspect
import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
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
    build_r2_media_key_candidates,
    build_r2_thumbnail_info,
)
from src.core.media_processor import (
    extract_media_metadata_from_storage,
    generate_and_upload_thumbnail,
)
from src.core.video_billing import (
    extract_video_prompt_prefix,
    infer_legacy_video_requested_duration,
    infer_billing_resolution_from_dimensions,
    is_video_billing_task_type,
    normalize_requested_billing_resolution,
)
from src.services.storage import storage
from src.services.affiliate_redeem_service import (
    AffiliateRedeemConflictError,
    AffiliateRedeemInsufficientBalanceError,
    invalidate_affiliate_redeem_cache_after_commit,
    redeem_affiliate_balance_to_credits,
)
from src.web_api.schemas.affiliate_redeem_schema import (
    AffiliateCreditsRedeemRequest,
    AffiliateCreditsRedeemResponse,
)
from src.web_api.schemas.auth_schema import InvitationRechargeStats, UserResponse
from src.web_api.schemas.user_schema import (
    CheckinResponse,
    HistoryItem,
    PaginatedHistory,
)
from src.web_api.schemas.gallery_schema import (
    PaginatedGalleryResponse,
    ApplyContextResponse,
    GalleryPostResponse,
)
from fastapi import HTTPException, BackgroundTasks, Request
from pydantic import BaseModel
import httpx
import re

router = APIRouter()
logger = logging.getLogger(__name__)


from src.web_api.dependencies import get_current_user, get_db, get_token

CurrentUserDep = Annotated[User, Depends(get_current_user)]
DbSessionDep = Annotated[AsyncSession, Depends(get_db)]


async def _get_r2_url_if_exists(object_key: str) -> str:
    public_url = storage.get_r2_public_url(object_key)
    if not public_url:
        return ""
    if await storage.async_r2_object_exists(object_key):
        return public_url
    return ""


async def _get_first_r2_url_if_exists(*object_keys: str) -> str:
    for object_key in object_keys:
        if not object_key:
            continue
        url = await _get_r2_url_if_exists(object_key)
        if url:
            return url
    return ""


async def _pick_favorite_media_urls(
    *,
    task_id: str | None,
    output_file: str | None,
    history_type: str | None,
) -> tuple[str, str]:
    if not output_file:
        return "", ""

    media_type = get_media_type_from_history(history_type)
    bucket_name, object_name = resolve_storage_object(output_file)
    media_r2_keys = build_r2_media_key_candidates(
        output_file=output_file,
        task_id=task_id,
    )
    thumb_file, thumb_r2_keys = build_r2_thumbnail_info(
        output_file=output_file,
        media_type=media_type,
        task_id=task_id,
    )
    _, thumb_object_name = resolve_storage_object(thumb_file)

    media_url = storage.get_presigned_url(object_name, bucket=bucket_name)
    thumbnail_url = ""

    if not task_id:
        media_r2_url, thumbnail_r2_url, thumb_exists = await asyncio.gather(
            _get_first_r2_url_if_exists(*media_r2_keys),
            _get_first_r2_url_if_exists(*thumb_r2_keys),
            storage.async_object_exists(bucket_name, thumb_object_name),
        )
        if media_r2_url:
            media_url = media_r2_url
        if thumbnail_r2_url:
            thumbnail_url = thumbnail_r2_url
        elif thumb_exists:
            thumbnail_url = storage.get_presigned_url(
                thumb_object_name, bucket=bucket_name
            )
        return media_url, thumbnail_url

    media_r2_url, thumbnail_r2_url, thumb_exists = await asyncio.gather(
        _get_first_r2_url_if_exists(*media_r2_keys),
        _get_first_r2_url_if_exists(*thumb_r2_keys),
        storage.async_object_exists(bucket_name, thumb_object_name),
    )

    if media_r2_url:
        media_url = media_r2_url
    if thumbnail_r2_url:
        thumbnail_url = thumbnail_r2_url
    elif thumb_exists:
        thumbnail_url = storage.get_presigned_url(thumb_object_name, bucket=bucket_name)

    return media_url, thumbnail_url


def _resolve_apply_prompt_and_requested_duration(history: History) -> tuple[str, int | None]:
    prompt = history.prompt or ""
    requested_duration = history.requested_duration

    if history.type == "ltx_video":
        _, _, clean_prompt = extract_video_prompt_prefix(prompt)
        prompt = clean_prompt

    return prompt, requested_duration


def _resolve_legacy_requested_duration(
    *,
    history: History,
    duration: int | None,
) -> int | None:
    if history.requested_duration is not None:
        return history.requested_duration
    return infer_legacy_video_requested_duration(history.type, duration)


async def _pick_history_media_urls(
    *,
    task_id: str | None,
    output_file: str | None,
    history_type: str | None,
) -> tuple[str, str]:
    if not output_file:
        return "", ""

    media_type = get_media_type_from_history(history_type)
    bucket_name, object_name = resolve_storage_object(output_file)
    media_r2_keys = build_r2_media_key_candidates(
        output_file=output_file,
        task_id=task_id,
    )
    thumb_file, thumb_r2_keys = build_r2_thumbnail_info(
        output_file=output_file,
        media_type=media_type,
        task_id=task_id,
    )
    _, thumb_object_name = resolve_storage_object(thumb_file)

    media_r2_url, thumbnail_r2_url, thumb_exists = await asyncio.gather(
        _get_first_r2_url_if_exists(*media_r2_keys),
        _get_first_r2_url_if_exists(*thumb_r2_keys),
        storage.async_object_exists(bucket_name, thumb_object_name),
    )

    output_file_url = ""
    thumbnail_url = ""
    if media_r2_url:
        output_file_url = media_r2_url
    else:
        output_file_url = storage.get_presigned_url(object_name, bucket=bucket_name)
    if thumbnail_r2_url:
        thumbnail_url = thumbnail_r2_url
    elif thumb_exists:
        thumbnail_url = storage.get_presigned_url(
            thumb_object_name, bucket=bucket_name
        )

    return output_file_url, thumbnail_url


def _gallery_post_sort_key(post: GalleryPost) -> tuple[int, datetime, int]:
    created_at = getattr(post, "created_at", None) or datetime.min
    return (
        1 if getattr(post, "is_active", False) else 0,
        created_at,
        getattr(post, "id", 0) or 0,
    )


def _pick_preferred_gallery_post(
    posts: list[GalleryPost] | tuple[GalleryPost, ...],
) -> GalleryPost | None:
    preferred: GalleryPost | None = None
    for post in posts:
        if post is None:
            continue
        if preferred is None or _gallery_post_sort_key(post) > _gallery_post_sort_key(
            preferred
        ):
            preferred = post
    return preferred


def _build_gallery_post_map(posts: list[GalleryPost]) -> dict[str, GalleryPost]:
    post_map: dict[str, GalleryPost] = {}
    for post in posts:
        if not post or not post.task_id:
            continue
        current = post_map.get(post.task_id)
        if current is None or _gallery_post_sort_key(post) > _gallery_post_sort_key(
            current
        ):
            post_map[post.task_id] = post
    return post_map


def _resolve_history_billing_resolution(
    history: History,
    *,
    gallery_post: GalleryPost | None = None,
    width: int | None = None,
    height: int | None = None,
) -> str | None:
    if not is_video_billing_task_type(history.type):
        return None
    if history.billing_resolution:
        normalized = normalize_requested_billing_resolution(
            history.billing_resolution, history.type
        )
        if normalized is not None:
            return normalized
    return infer_billing_resolution_from_dimensions(
        width if width is not None else history.width,
        height if height is not None else history.height,
        history.type,
    ) or (
        infer_billing_resolution_from_dimensions(
            getattr(gallery_post, "width", None),
            getattr(gallery_post, "height", None),
            history.type,
        )
        if gallery_post
        else None
    )


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
        is_unlocked=dto.is_unlocked,
    )


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
    limit = 8

    # First get the latest 8 items regardless of visibility to enforce the strict 8-item window limit
    subq = (
        select(History.id)
        .where(History.user_id == current_user.id)
        .order_by(History.created_at.desc())
        .limit(limit)
        .subquery()
    )

    # Then filter out the invisible ones from those 8 items
    stmt = (
        select(History)
        .where(History.id.in_(select(subq.c.id)))
        .where(History.is_visible.is_not(False))
        .order_by(History.created_at.desc())
    )
    result = await db.execute(stmt)
    items = result.scalars().all()

    # Batch check gallery status for items to avoid N+1 queries
    task_ids_to_check = [
        item.task_id for item in items if item.is_public and item.task_id
    ]

    active_task_ids = set()
    if task_ids_to_check:
        from src.database.models import GalleryPost

        gp_stmt = select(GalleryPost.task_id).where(
            GalleryPost.task_id.in_(task_ids_to_check), GalleryPost.is_active == True
        )
        gp_result = await db.execute(gp_stmt)
        active_task_ids = set(gp_result.scalars().all())

    url_pairs = await asyncio.gather(
        *[
            _pick_history_media_urls(
                task_id=item.task_id,
                output_file=item.output_file,
                history_type=item.type,
            )
            for item in items
        ]
    )

    response_items = []
    for item, (output_file_url, thumbnail_url) in zip(items, url_pairs):
        is_public = bool(item.is_public)
        if is_public and item.task_id and item.task_id not in active_task_ids:
            is_public = False

        response_items.append(
            HistoryItem(
                id=item.id,
                task_id=item.task_id,
                type=item.type,
                prompt=item.prompt,
                input_file=item.input_file,
                output_file=item.output_file,
                billing_resolution=item.billing_resolution,
                width=item.width,
                height=item.height,
                duration=item.duration,
                output_file_url=output_file_url,
                thumbnail_url=thumbnail_url,
                created_at=item.created_at,
                allow_contribute=item.allow_contribute,
                source=item.source,
                is_public=is_public,
                is_favorited=item.is_favorited,
            )
        )

    return PaginatedHistory(items=response_items, total=len(response_items), page=1, size=limit)


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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import desc

    # Query current user's favorite histories
    stmt = (
        select(History)
        .where(
            History.user_id == current_user.id,
            History.is_favorited == True,
            History.is_visible.is_not(False),
        )
        .order_by(desc(History.created_at))
    )

    # Get total
    from sqlalchemy import func

    total_query = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(total_query)).scalar()

    # Paginate
    offset = (page - 1) * size
    stmt = stmt.offset(offset).limit(size)
    result = await db.execute(stmt)
    histories = result.scalars().all()

    task_ids = [history.task_id for history in histories if history.task_id]
    gallery_post_map = {}
    if task_ids:
        gallery_posts = (
            await db.execute(select(GalleryPost).where(GalleryPost.task_id.in_(task_ids)))
        ).scalars().all()
        gallery_post_map = _build_gallery_post_map(gallery_posts)

    url_pairs = await asyncio.gather(
        *[
            _pick_favorite_media_urls(
                task_id=history.task_id,
                output_file=history.output_file,
                history_type=history.type,
            )
            for history in histories
        ]
    )

    response_items = []
    for history, (media_url, thumbnail_url) in zip(histories, url_pairs):
        gallery_post = gallery_post_map.get(history.task_id)

        # media_type mapping
        media_type = get_media_type_from_history(history.type)

        # extract tags from prompt
        tags = []
        if history.prompt:
            match = re.search(r"\[模型:\s*(.*?)\]", history.prompt)
            if match:
                tags.append(f"#{match.group(1).strip()}")

        response_items.append(
            GalleryPostResponse(
                id=history.id,
                task_id=history.task_id,
                media_type=media_type,
                billing_resolution=_resolve_history_billing_resolution(
                    history, gallery_post=gallery_post
                ),
                width=history.width if history.width is not None else (gallery_post.width if gallery_post else None),
                height=history.height if history.height is not None else (gallery_post.height if gallery_post else None),
                duration=history.duration if history.duration is not None else (gallery_post.duration if gallery_post else None),
                tags=tags,
                likes_count=0,
                dislikes_count=0,
                applied_count=0,
                thumbnail_url=thumbnail_url,
                media_url=media_url,
                created_at=history.created_at,
                is_active=True,
                prompt=history.prompt,
                task_type=history.type,
                has_liked=False,
                has_disliked=False,
            )
        )

    pages = (total + size - 1) // size
    return PaginatedGalleryResponse(
        items=response_items, total=total, page=page, size=size, pages=pages
    )


@router.get("/history/{task_id}/apply-context", response_model=ApplyContextResponse)
async def get_favorite_apply_context(
    task_id: str,
    token: str = Depends(get_token),
):
    from src.config_mapping import ALL_LORA_MODELS
    from src.database.core import AsyncSessionLocal
    from src.web_api.dependencies import get_current_user

    async with AsyncSessionLocal() as db:
        current_user = await get_current_user(db, token)
        user_id = current_user.id

        stmt = select(History).where(
            History.task_id == task_id, History.user_id == user_id
        )
        result = await db.execute(stmt)
        history = result.scalar_one_or_none()
    
        if not history:
            raise HTTPException(status_code=404, detail="未找到原任务详情")
    
        gallery_posts = (
            await db.execute(select(GalleryPost).where(GalleryPost.task_id == history.task_id))
        ).scalars().all()
        gallery_post = _pick_preferred_gallery_post(gallery_posts)

    input_file_url = None
    if history.input_file:
        from src.services.storage import storage

        bucket_name, object_name = resolve_storage_object(history.input_file)
        input_file_url = storage.get_presigned_url(
            object_name, bucket=bucket_name
        )

    prompt, requested_duration = _resolve_apply_prompt_and_requested_duration(history)
    lora_name = None
    match = re.search(r"\[模型:\s*(.*?)\]\s*(.*)", prompt, re.DOTALL)
    if match:
        lora_tag = match.group(1).strip()
        prompt = match.group(2).strip()

        reverse_lora_models = {v: k for k, v in ALL_LORA_MODELS.items()}
        reverse_lora_models["逼真"] = "qwen/YARN_1.0.safetensors"
        reverse_lora_models["菊花+内凹穴"] = "qwen/adjust_pussy_anus.safetensors"
        reverse_lora_models["真实质感"] = "qwen/realistic_texture.safetensors"
        reverse_lora_models["平胸/无毛穴"] = "qwen/flat_chest_hairless.safetensors"
        reverse_lora_models["扶他(阴茎)"] = "qwen/penis.safetensors"

        if lora_tag in reverse_lora_models:
            lora_name = reverse_lora_models[lora_tag]
        else:
            lora_name = lora_tag

    media_type = "image"
    if history.type and "video" in history.type.lower():
        media_type = "video"

    width = history.width
    height = history.height
    # Keep `duration` as probed media metadata. Canonical request duration is exposed
    # separately via `requested_duration`.
    duration = history.duration
    billing_resolution = _resolve_history_billing_resolution(
        history, gallery_post=gallery_post
    )

    if width is None and gallery_post:
        width = gallery_post.width
    if height is None and gallery_post:
        height = gallery_post.height
    if duration is None and gallery_post:
        duration = gallery_post.duration

    if history.output_file and (
        width is None or height is None or (media_type == "video" and duration is None)
    ):
        try:
            probed_width, probed_height, probed_duration = await extract_media_metadata_from_storage(
                history.output_file, media_type
            )
            width = probed_width if probed_width is not None else width
            height = probed_height if probed_height is not None else height
            duration = probed_duration if probed_duration is not None else duration
            if billing_resolution is None:
                billing_resolution = infer_billing_resolution_from_dimensions(
                    width, height, history.type
                )
        except Exception as exc:
            logger.warning(
                "Failed to probe media metadata for task %s: %s",
                history.task_id,
                exc,
            )

    requested_duration = _resolve_legacy_requested_duration(
        history=history,
        duration=duration,
    )

    return ApplyContextResponse(
        post_id=gallery_post.id if gallery_post else history.id,
        source_post_id=gallery_post.id if gallery_post else None,
        billing_resolution=billing_resolution,
        requested_duration=requested_duration,
        task_id=history.task_id,
        media_type=media_type,
        prompt=prompt,
        lora_name=lora_name,
        input_file=history.input_file,
        input_file_url=input_file_url,
        width=width,
        height=height,
        duration=duration,
        task_type=history.type,
    )


@router.post("/history/{task_id}/send-to-bot")
async def send_history_to_bot(task_id: str, request: Request):
    from src.services.storage import storage
    from config import TELEGRAM_API_BASE_URL, BOT_TOKEN
    from src.database.core import AsyncSessionLocal
    from src.web_api.dependencies import get_current_user

    token = request.query_params.get("token")
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]

    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    async with AsyncSessionLocal() as db:
        current_user = await get_current_user(db, token)
        user_id = current_user.id
        telegram_id = current_user.telegram_id

        # 1. 检查多渠道登录用户的 TG 绑定状态
        if not telegram_id:
            raise HTTPException(
                status_code=400, detail="您尚未绑定 Telegram 账号，无法发送至私聊"
            )

        # 2. Redis 10秒防刷锁（严格对齐现有 redis_client 模式）
        from src.services.redis_client import redis_client

        lock_key = f"rate_limit:send_to_bot:{user_id}"
        if redis_client and redis_client.redis:
            is_locked = await redis_client.redis.set(lock_key, "1", nx=True, ex=10)
            if not is_locked:
                raise HTTPException(
                    status_code=429, detail="操作过于频繁，请10秒后再试"
                )

        # 3. 校验历史记录与文件存在性
        stmt = select(History).where(
            History.task_id == task_id, History.user_id == user_id
        )
        result = await db.execute(stmt)
        history = result.scalar_one_or_none()

        if not history:
            raise HTTPException(status_code=404, detail="未找到对应的任务记录")
        if not history.output_file:
            raise HTTPException(status_code=400, detail="该任务没有生成文件")

        history_output_file = history.output_file
        history_type = history.type
        history_prompt = history.prompt

    # 4. 严谨提取 bucket 和 object_name
    bucket_name, object_name = resolve_storage_object(history_output_file)

    # 5. 从 MinIO 下载文件字节流到内存 (方案 B: 内存流直传)
    import asyncio
    try:
        # 【核心规范】必须使用 asyncio.to_thread 包装同步的 MinIO SDK 调用，防止阻塞 FastAPI 事件循环
        file_bytes = await asyncio.to_thread(
            storage.get_file_bytes, object_name, bucket_name
        )
    except Exception as e:
        logger.error(f"Failed to download {object_name} from {bucket_name}: {e}")
        file_bytes = None
        
    if not file_bytes:
        raise HTTPException(status_code=500, detail="无法读取文件内容")

    # 6. 构造 Local API 请求并以 multipart/form-data 发送
    is_video = history_type and "video" in history_type.lower()
    method = "sendVideo" if is_video else "sendPhoto"
    url = f"{TELEGRAM_API_BASE_URL}/bot{BOT_TOKEN}/{method}"

    # httpx 发送 multipart data 时，普通字段放 data，文件放 files
    payload = {"chat_id": str(telegram_id)}

    # 截取 Prompt 前 100 字符作为 caption，避免太长导致发送失败，同时避免传入 null
    if history_prompt:
        caption = (
            history_prompt[:100] + "..."
            if len(history_prompt) > 100
            else history_prompt
        )
        payload["caption"] = caption

    filename = object_name.split("/")[-1]
    files = {}
    if is_video:
        files["video"] = (filename, file_bytes, "video/mp4")
    else:
        # 简单推断 content_type
        ext = filename.split(".")[-1].lower() if "." in filename else "jpeg"
        content_type = f"image/{ext}" if ext != "jpg" else "image/jpeg"
        files["photo"] = (filename, file_bytes, content_type)

    async with httpx.AsyncClient() as client:
        try:
            # timeout 设置宽裕点 (60秒)，因为直传大文件需要时间
            resp = await client.post(url, data=payload, files=files, timeout=60.0)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code in [400, 403]:
                error_msg = e.response.text
                logger.error(f"Telegram API Error (400/403): {error_msg}")
                # 兼容不同类型的 Telegram 报错
                if "wrong file identifier" in error_msg or "failed to get HTTP URL content" in error_msg:
                    raise HTTPException(
                        status_code=400,
                        detail="发送失败：Telegram 无法访问该文件或文件格式错误"
                    )
                raise HTTPException(
                    status_code=403,
                    detail="发送失败，请确保您在 Telegram 中已允许机器人发送消息",
                )
            logger.error(f"Telegram API Error: {e.response.text}")
            raise HTTPException(status_code=500, detail="发送失败，Telegram 服务器异常")
        except Exception as e:
            logger.error(f"Send to bot request failed: {e}")
            raise HTTPException(status_code=500, detail="发送失败，网络连接异常")

    return {"status": "success", "message": "已发送至您的 Telegram 私聊"}
