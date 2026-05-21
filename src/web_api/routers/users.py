import asyncio
import inspect
import logging
from datetime import datetime
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
    HistoryItem,
    PaginatedHistory,
)
from src.web_api.schemas.gallery_schema import (
    PaginatedGalleryResponse,
    ApplyContextResponse,
    GalleryPostResponse,
)
from src.web_api.routers.utils import (
    build_history_apply_context_response,
    resolve_history_billing_resolution,
)
from src.web_api.presenters.media_presenter import resolve_history_media_urls
from fastapi import HTTPException, BackgroundTasks
from pydantic import BaseModel
import httpx
import re

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
    return await resolve_history_media_urls(
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
    return await resolve_history_media_urls(
        task_id=task_id,
        output_file=output_file,
        history_type=history_type,
    )


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
    task_type: str | None = Query(default=None),
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

    if task_type:
        stmt = stmt.where(History.type == task_type)

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
                billing_resolution=resolve_history_billing_resolution(
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
    current_user: CurrentUserDep,
    db: DbSessionDep,
):
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

    return await build_history_apply_context_response(
        history=history,
        post_id=gallery_post.id if gallery_post else history.id,
        source_post_id=gallery_post.id if gallery_post else None,
        gallery_post=gallery_post,
        primary_width=history.width,
        primary_height=history.height,
        primary_duration=history.duration,
        fallback_width=gallery_post.width if gallery_post else None,
        fallback_height=gallery_post.height if gallery_post else None,
        fallback_duration=gallery_post.duration if gallery_post else None,
        build_input_file_url=lambda file_path: build_storage_presigned_url(
            file_path,
            lambda object_name, bucket_name: storage.get_presigned_url(
                object_name, bucket=bucket_name
            ),
        ),
        probe_output_file=history.output_file,
        probe_media_metadata=extract_media_metadata_from_storage,
        logger=logger,
    )


@router.post("/history/{task_id}/send-to-bot")
async def send_history_to_bot(
    task_id: str,
    current_user: CurrentUserDep,
    db: DbSessionDep,
):
    from src.services.storage import storage
    from config import TELEGRAM_API_BASE_URL, BOT_TOKEN
    user_id = current_user.id
    telegram_id = current_user.telegram_id

    if not telegram_id:
        raise HTTPException(
            status_code=400, detail="您尚未绑定 Telegram 账号，无法发送至私聊"
        )

    from src.services.redis_client import redis_client

    lock_key = f"rate_limit:send_to_bot:{user_id}"
    if redis_client and redis_client.redis:
        is_locked = await redis_client.redis.set(lock_key, "1", nx=True, ex=10)
        if not is_locked:
            raise HTTPException(
                status_code=429, detail="操作过于频繁，请10秒后再试"
            )

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
