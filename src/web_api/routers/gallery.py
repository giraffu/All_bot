import asyncio
import json
import logging
import re
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy import delete, desc, func, select, update
from sqlalchemy.orm import joinedload

from src.config_mapping import (
    ALL_LORA_MODELS,
    IMAGE_LORA_MODELS,
    VIDEO_LORA_MODELS,
    translate_tags,
)
from src.constants import (
    MODE_CUSTOM_VIDEO,
    MODE_EDIT,
    MODE_I2I_PRO,
    MODE_I2I_DRAW,
    MODE_LTX_VIDEO,
    MODE_NAME_MAP,
    MODE_VIDEO_LORA,
)
from src.core.media_paths import (
    build_history_r2_media_key,
    build_history_r2_thumbnail_key,
    build_legacy_r2_key,
    build_thumbnail_object_name,
    get_media_type_from_history,
    resolve_storage_object,
)
from src.core.media_urls import (
    build_r2_media_key_candidates,
    build_r2_thumbnail_info,
)
from src.core.video_billing import (
    extract_video_prompt_prefix,
    infer_legacy_video_requested_duration,
    infer_billing_resolution_from_dimensions,
    is_video_billing_task_type,
    normalize_requested_billing_resolution,
)
from src.database.core import AsyncSessionLocal
from src.database.models import GalleryPost, History, User, UserInteraction, GalleryComment
from src.services.storage import storage
from src.web_api.dependencies import get_current_user
from src.web_api.schemas.gallery_schema import (
    ApplyContextResponse,
    GalleryPostResponse,
    PaginatedGalleryResponse,
    GallerySubmitRequest,
    CommentCreate,
    CommentUserResponse,
    GalleryCommentResponse,
    PaginatedCommentResponse,
)

router = APIRouter()
logger = logging.getLogger(__name__)

# Allowed task types for web gallery submission
ALLOWED_WEB_SUBMIT_TYPES = {
    MODE_I2I_PRO,
    MODE_I2I_DRAW,
    MODE_EDIT,
    MODE_CUSTOM_VIDEO,
    MODE_VIDEO_LORA,
    MODE_LTX_VIDEO,
    "img2img_lora",
}


def _resolve_author_name(user: User | None, fallback_user_id: int | None = None) -> str:
    if user:
        return user.full_name or user.username or f"User {user.id}"
    if fallback_user_id is not None:
        return f"User {fallback_user_id}"
    return "匿名修士"


def _resolve_apply_prompt_and_requested_duration(history: History) -> tuple[str, int | None]:
    prompt = history.prompt or ""
    requested_duration = history.requested_duration

    if history.type == MODE_LTX_VIDEO:
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

async def get_media_url(
    output_file: str,
    task_id: str | None = None,
    r2_object_name: str | None = None,
    media_type: str | None = None,
) -> str:
    """
    Generate the media URL for a gallery post.
    Prefer an existing R2 object and fall back to the original storage path.
    """
    if not output_file:
        return ""

    for object_key in build_r2_media_key_candidates(
        output_file=output_file,
        task_id=task_id,
        preferred_r2_object_name=r2_object_name,
    ):
        public_url = storage.get_r2_public_url(object_key)
        if public_url and await storage.async_r2_object_exists(object_key):
            return public_url

    bucket_name, object_name = resolve_storage_object(output_file)
    return storage.get_presigned_url(object_name, bucket=bucket_name) or output_file


async def generate_thumbnail_url(
    output_file: str,
    media_type: str,
    task_id: str | None = None,
    r2_object_name: str | None = None,
) -> str:
    """
    Generate the thumbnail URL based on the original file path.
    Appends _thumb.jpg for videos and _thumb.webp for images.
    """
    if not output_file:
        return ""

    thumb_file, thumb_r2_keys = build_r2_thumbnail_info(
        output_file=output_file,
        media_type=media_type,
        task_id=task_id,
        preferred_r2_object_name=r2_object_name,
    )
    preferred_thumb_key = thumb_r2_keys[0] if thumb_r2_keys else None
    return await get_media_url(
        thumb_file,
        task_id=None,
        r2_object_name=preferred_thumb_key,
        media_type=media_type,
    )


async def _pick_gallery_media_urls(
    *,
    task_id: str | None,
    output_file: str | None,
    media_type: str,
) -> tuple[str, str]:
    if not output_file:
        return "", ""

    _, thumb_r2_keys = build_r2_thumbnail_info(
        output_file=output_file,
        media_type=media_type,
        task_id=task_id,
    )
    preferred_thumb_key = thumb_r2_keys[0] if thumb_r2_keys else None

    media_url, thumbnail_url = await asyncio.gather(
        get_media_url(output_file, task_id=task_id, media_type=media_type),
        generate_thumbnail_url(
            output_file,
            media_type,
            task_id=task_id,
            r2_object_name=preferred_thumb_key,
        ),
        return_exceptions=True,
    )
    if isinstance(media_url, Exception):
        logger.warning(
            "Failed to build gallery media URL for task_id=%s: %s",
            task_id,
            media_url,
            exc_info=media_url,
        )
        media_url = output_file
    if isinstance(thumbnail_url, Exception):
        logger.warning(
            "Failed to build gallery thumbnail URL for task_id=%s: %s",
            task_id,
            thumbnail_url,
            exc_info=thumbnail_url,
        )
        thumbnail_url = ""
    return media_url, thumbnail_url


def _resolve_history_billing_resolution(
    history: History,
    *,
    width: int | None = None,
    height: int | None = None,
    gallery_post: GalleryPost | None = None,
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


@router.get("/config")
async def get_gallery_config():
    return {
        "allowed_types": [
            {
                "id": MODE_I2I_PRO,
                "name": MODE_NAME_MAP.get(MODE_I2I_PRO, "task.mode_i2i_pro"),
            },
            {
                "id": MODE_I2I_DRAW,
                "name": MODE_NAME_MAP.get(MODE_I2I_DRAW, "task.mode_i2i_draw"),
            },
            {"id": MODE_EDIT, "name": MODE_NAME_MAP.get(MODE_EDIT, "task.mode_edit")},
            {"id": "img2img_lora", "name": "task.mode_img2img_lora"},
            {
                "id": MODE_CUSTOM_VIDEO,
                "name": MODE_NAME_MAP.get(MODE_CUSTOM_VIDEO, "task.mode_custom_video"),
            },
            {
                "id": MODE_VIDEO_LORA,
                "name": MODE_NAME_MAP.get(MODE_VIDEO_LORA, "task.mode_video_lora"),
            },
            {
                "id": MODE_LTX_VIDEO,
                "name": MODE_NAME_MAP.get(MODE_LTX_VIDEO, "task.mode_ltx_video"),
            },
        ],
        "lora_models": [{"id": k, "name": v} for k, v in VIDEO_LORA_MODELS.items()],
        "img2img_lora_models": [
            {"id": k, "name": v} for k, v in IMAGE_LORA_MODELS.items() if k
        ],
    }


async def _build_post_responses(session, posts, current_user: Optional[User]):
    if not posts:
        return []

    post_ids = [p.id for p in posts]
    task_ids = [p.task_id for p in posts if p.task_id]

    user_likes = set()
    user_dislikes = set()
    if current_user and post_ids:
        interactions = (
            (
                await session.execute(
                    select(UserInteraction)
                    .where(UserInteraction.user_id == current_user.id)
                    .where(UserInteraction.post_id.in_(post_ids))
                    .where(UserInteraction.action_type.in_(["like", "dislike"]))
                )
            )
            .scalars()
            .all()
        )
        for inter in interactions:
            if inter.action_type == "like":
                user_likes.add(inter.post_id)
            elif inter.action_type == "dislike":
                user_dislikes.add(inter.post_id)

    history_map = {}
    if task_ids:
        histories = (
            (
                await session.execute(
                    select(History).where(History.task_id.in_(task_ids))
                )
            )
            .scalars()
            .all()
        )
        history_map = {h.task_id: h for h in histories}

    user_ids = list(set([p.user_id for p in posts if p.user_id]))
    user_map = {}
    if user_ids:
        from src.database.models import User

        users = (
            (await session.execute(select(User).where(User.id.in_(user_ids))))
            .scalars()
            .all()
        )
        # use full_name, fallback to username or string ID
        for u in users:
            name = u.full_name if u.full_name else (u.username or f"User {u.id}")
            user_map[u.id] = name

    # 并发获取媒体 URL 和缩略图 URL
    tasks = []
    for post in posts:
        history = history_map.get(post.task_id)
        output_file = history.output_file if history else None
        tasks.append(
            _pick_gallery_media_urls(
                task_id=post.task_id,
                output_file=output_file,
                media_type=post.media_type,
            )
        )
    urls_results = await asyncio.gather(*tasks, return_exceptions=True)

    response_items = []
    for i, post in enumerate(posts):
        try:
            tags = json.loads(post.tags) if post.tags else []
        except Exception:
            tags = []
        translated_tags = translate_tags(tags)

        history = history_map.get(post.task_id)
        prompt = history.prompt if history else None
        task_type_from_history = history.type if history else None

        url_result = urls_results[i]
        if isinstance(url_result, Exception):
            logger.warning(
                "Failed to build gallery media URLs for post_id=%s task_id=%s: %s",
                post.id,
                post.task_id,
                url_result,
                exc_info=url_result,
            )
            media_url = history.output_file if history and history.output_file else ""
            thumbnail_url = ""
        else:
            media_url, thumbnail_url = url_result

        billing_resolution = None
        if history:
            billing_resolution = _resolve_history_billing_resolution(
                history,
                width=post.width if post.width is not None else history.width,
                height=post.height if post.height is not None else history.height,
                gallery_post=post,
            )

        response_items.append(
            GalleryPostResponse(
                id=post.id,
                task_id=post.task_id,
                media_type=post.media_type,
                billing_resolution=billing_resolution,
                width=post.width,
                height=post.height,
                duration=post.duration,
                tags=translated_tags,
                likes_count=post.likes_count,
                dislikes_count=post.dislikes_count,
                applied_count=post.applied_count,
                comments_count=post.comments_count or 0,
                thumbnail_url=thumbnail_url,
                media_url=media_url,
                created_at=post.created_at,
                is_active=post.is_active,
                prompt=prompt,
                task_type=task_type_from_history,
                has_liked=post.id in user_likes,
                has_disliked=post.id in user_dislikes,
                author_name=user_map.get(post.user_id) if post.user_id else "匿名修士",
            )
        )
    return response_items


@router.get("/posts", response_model=PaginatedGalleryResponse)
async def get_gallery_posts(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    media_type: Optional[str] = None,
    task_type: Optional[str] = None,
    lora_model: Optional[str] = None,
    sort_by: str = Query("latest", pattern="^(latest|likes|applied)$"),
    time_range: str = Query("all", pattern="^(today|week|month|all)$"),
    current_user: Optional[User] = Depends(get_current_user),
):
    posts, total = await get_gallery_feed(
        page=page,
        size=size,
        media_type=media_type if media_type != "all" else None,
        task_type=task_type if task_type != "all" else None,
        lora_model=lora_model,
        sort_by=sort_by,
        time_range=time_range,
        user_id=current_user.id if current_user else None,
    )

    async with AsyncSessionLocal() as session:
        response_items = await _build_post_responses(session, posts, current_user)

        pages = (total + size - 1) // size
        return PaginatedGalleryResponse(
            items=response_items, total=total, page=page, size=size, pages=pages
        )


@router.get("/my-posts", response_model=PaginatedGalleryResponse)
async def get_my_gallery_posts(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    task_type: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    async with AsyncSessionLocal() as session:
        query = (
            select(GalleryPost)
            .outerjoin(History, GalleryPost.task_id == History.task_id)
            .where(
                GalleryPost.user_id == current_user.id, History.is_visible.is_not(False)
            )
            .distinct()
        )

        if task_type:
            query = query.where(History.type == task_type)

        query = query.order_by(desc(GalleryPost.id))

        # Get total count
        from sqlalchemy import func

        total_query = select(func.count()).select_from(query.subquery())
        total = (await session.execute(total_query)).scalar()

        # Paginate
        offset = (page - 1) * size
        query = query.offset(offset).limit(size)

        result = await session.execute(query)
        posts = result.scalars().all()

        response_items = await _build_post_responses(session, posts, current_user)

        pages = (total + size - 1) // size
        return PaginatedGalleryResponse(
            items=response_items, total=total, page=page, size=size, pages=pages
        )


@router.get("/my-favorites", response_model=PaginatedGalleryResponse)
async def get_my_favorite_posts(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    filter_type: str = Query("all", pattern="^(all|like|apply)$"),
    task_type: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    async with AsyncSessionLocal() as session:
        action_types = ["like", "apply"]
        if filter_type == "like":
            action_types = ["like"]
        elif filter_type == "apply":
            action_types = ["apply"]

        query = (
            select(GalleryPost)
            .join(UserInteraction, GalleryPost.id == UserInteraction.post_id)
            .outerjoin(History, GalleryPost.task_id == History.task_id)
            .where(
                UserInteraction.user_id == current_user.id,
                UserInteraction.action_type.in_(action_types),
                GalleryPost.is_active == True,
            )
            .distinct()
            .order_by(desc(GalleryPost.id))
        )

        if task_type:
            query = query.where(History.type == task_type)

        # Get total count
        from sqlalchemy import func

        total_query = select(func.count()).select_from(query.subquery())
        total = (await session.execute(total_query)).scalar()

        # Paginate
        offset = (page - 1) * size
        query = query.offset(offset).limit(size)

        result = await session.execute(query)
        posts = result.scalars().all()

        response_items = await _build_post_responses(session, posts, current_user)

        pages = (total + size - 1) // size
        return PaginatedGalleryResponse(
            items=response_items, total=total, page=page, size=size, pages=pages
        )


@router.put("/posts/{post_id}/status")
async def update_post_status(
    post_id: int,
    is_active: bool = Query(...),
    current_user: User = Depends(get_current_user),
):
    async with AsyncSessionLocal() as session:
        post = (
            await session.execute(select(GalleryPost).where(GalleryPost.id == post_id))
        ).scalar_one_or_none()
        if not post:
            raise HTTPException(status_code=404, detail="帖子不存在")
        if post.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="无权操作此帖子")

        await session.execute(
            update(GalleryPost)
            .where(GalleryPost.id == post_id)
            .values(is_active=is_active)
        )
        await session.commit()
        return {"status": "success", "message": f"已{'上架' if is_active else '下架'}"}


@router.delete("/posts/{post_id}")
async def delete_post(post_id: int, current_user: User = Depends(get_current_user)):
    r2_cleanup_keys: set[str] = set()
    async with AsyncSessionLocal() as session:
        post = (
            await session.execute(select(GalleryPost).where(GalleryPost.id == post_id))
        ).scalar_one_or_none()
        if not post:
            raise HTTPException(status_code=404, detail="帖子不存在")
        if post.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="无权操作此帖子")

        history = None
        if post.task_id:
            history = (
                await session.execute(
                    select(History).where(
                        History.task_id == post.task_id, History.user_id == current_user.id
                    )
                )
            ).scalar_one_or_none()

        # Keep the existing contribution counter behavior: only decrement when the
        # post was still on shelf at delete time.
        if post.is_active:
            user_record = await session.execute(
                select(User).where(User.id == current_user.id)
            )
            user_obj = user_record.scalar_one_or_none()
            if user_obj:
                user_obj.total_contributions = max(
                    (user_obj.total_contributions or 0) - 1, 0
                )

        # Unlink history from this post so user can re-submit if they want.
        if history:
            history.is_public = False
            if history.output_file:
                media_type = get_media_type_from_history(history.type)
                _, object_name = resolve_storage_object(history.output_file)
                thumb_object_name = build_thumbnail_object_name(object_name, media_type)
                r2_cleanup_keys = {
                    key
                    for key in {
                        build_history_r2_media_key(post.task_id, history.output_file),
                        build_history_r2_thumbnail_key(post.task_id, media_type),
                        build_legacy_r2_key(object_name),
                        build_legacy_r2_key(thumb_object_name),
                    }
                    if key
                }
        elif post.task_id:
            await session.execute(
                update(History)
                .where(
                    History.task_id == post.task_id, History.user_id == current_user.id
                )
                .values(is_public=False)
            )

        await session.execute(
            delete(UserInteraction).where(UserInteraction.post_id == post_id)
        )
        await session.execute(
            delete(GalleryComment).where(GalleryComment.post_id == post_id)
        )
        await session.execute(delete(GalleryPost).where(GalleryPost.id == post_id))

        await session.commit()

    if r2_cleanup_keys:
        try:
            await storage.async_delete_r2_objects(list(r2_cleanup_keys))
        except Exception:
            logger.warning(
                "Failed to clean R2 cache after deleting gallery post %s",
                post_id,
                exc_info=True,
            )

    return {"status": "success", "message": "删除成功"}


@router.post("/posts/{post_id}/interact")
async def interact_with_post(
    post_id: int,
    action: str = Query(..., pattern="^(like|dislike)$"),
    current_user: User = Depends(get_current_user),
):
    from src.core.gallery_core import (
        toggle_like,
        GalleryCoreError,
        DuplicateInteractionError,
    )

    try:
        result = await toggle_like(current_user.id, post_id, action)
        action_state = result.get("action_state")
        if action_state == "canceled":
            message = "已取消点赞" if action == "like" else "已取消点踩"
        else:
            message = "点赞成功" if action == "like" else "点踩成功"
        return {"status": "success", "message": message, "data": result}
    except DuplicateInteractionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except GalleryCoreError as e:
        if "不存在" in str(e):
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.error("发生未捕获异常", exc_info=True)
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.post("/posts/{post_id}/comments", response_model=GalleryCommentResponse)
async def create_gallery_comment(
    post_id: int,
    comment: CommentCreate,
    current_user: User = Depends(get_current_user),
):
    from src.services.redis_client import redis_client
    unavailable_comment_error = "帖子已下架或已删除，无法发布评论"

    async with AsyncSessionLocal() as session:
        # 校验帖子
        post = await session.get(GalleryPost, post_id)
        if not post or not post.is_active:
            raise HTTPException(status_code=404, detail="帖子不存在或已下架")

        # 防刷校验：仅对有效帖子申请频率锁，避免 404 请求误伤后续正常评论
        lock_acquired = await redis_client.set_comment_lock(current_user.id, ttl=5)
        if not lock_acquired:
            raise HTTPException(status_code=429, detail="操作过于频繁，请稍后再试")

        # 插入评论
        new_comment = GalleryComment(
            post_id=post_id,
            user_id=current_user.id,
            content=comment.content,
        )
        try:
            session.add(new_comment)
            await session.flush()

            # 原子更新评论数（附带 is_active 二次校验，防止并发下架）
            stmt = (
                update(GalleryPost)
                .where(GalleryPost.id == post_id, GalleryPost.is_active.is_(True))
                .values(comments_count=GalleryPost.comments_count + 1)
            )
            result = await session.execute(stmt)
            
            if result.rowcount == 0:
                # 帖子在此期间已被下架或删除，回滚整个事务（包括 session.flush() 中已插入的评论）
                await session.rollback()
                await redis_client.delete_comment_lock(current_user.id)
                raise HTTPException(status_code=404, detail=unavailable_comment_error)

            # 在 commit 前构造返回值对象
            response_data = GalleryCommentResponse(
                id=new_comment.id,
                content=new_comment.content,
                created_at=new_comment.created_at,
                user=CommentUserResponse(
                    id=current_user.id,
                    author_name=_resolve_author_name(current_user),
                ),
            )

            await session.commit()
            return response_data
        except HTTPException:
            raise
        except IntegrityError:
            # 并发删除帖子时，flush/commit 可能触发外键约束错误。
            await session.rollback()
            await redis_client.delete_comment_lock(current_user.id)
            raise HTTPException(status_code=404, detail=unavailable_comment_error)
        except Exception:
            await session.rollback()
            await redis_client.delete_comment_lock(current_user.id)
            logger.error("Failed to create comment", exc_info=True)
            raise HTTPException(status_code=500, detail="发布评论失败")


@router.get("/posts/{post_id}/comments", response_model=PaginatedCommentResponse)
async def get_gallery_comments(
    post_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    async with AsyncSessionLocal() as session:
        # 校验帖子
        post = await session.get(GalleryPost, post_id)
        if not post or not post.is_active:
            raise HTTPException(status_code=404, detail="帖子不存在或已下架")

        # 查询总数
        count_stmt = select(func.count(GalleryComment.id)).where(
            GalleryComment.post_id == post_id,
            GalleryComment.is_active.is_(True),
        )
        total = await session.scalar(count_stmt) or 0

        # 分页查询
        stmt = (
            select(GalleryComment)
            .options(joinedload(GalleryComment.user))
            .where(
                GalleryComment.post_id == post_id,
                GalleryComment.is_active.is_(True),
            )
            .order_by(desc(GalleryComment.created_at), desc(GalleryComment.id))
            .offset((page - 1) * size)
            .limit(size)
        )
        result = await session.execute(stmt)
        comments = result.scalars().all()

        response_items = []
        for c in comments:
            response_items.append(
                GalleryCommentResponse(
                    id=c.id,
                    content=c.content,
                    created_at=c.created_at,
                    user=CommentUserResponse(
                        id=c.user.id if c.user else c.user_id,
                        author_name=_resolve_author_name(c.user, c.user_id),
                    ),
                )
            )

        pages = (total + size - 1) // size
        return PaginatedCommentResponse(
            items=response_items,
            total=total,
            page=page,
            size=size,
            pages=pages
        )

@router.get("/posts/{post_id}/apply-context", response_model=ApplyContextResponse)
async def get_apply_context(
    post_id: int, current_user: User = Depends(get_current_user)
):
    _ = current_user
    async with AsyncSessionLocal() as session:
        post = (
            await session.execute(select(GalleryPost).where(GalleryPost.id == post_id))
        ).scalar_one_or_none()
        if not post:
            raise HTTPException(status_code=404, detail="帖子不存在或已失效")

        hist_res = await session.execute(
            select(History).where(History.task_id == post.task_id)
        )
        history = hist_res.scalars().first()

        if not history:
            raise HTTPException(status_code=404, detail="未找到原任务详情")

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

            # Map Chinese lora_tag back to ID if needed
            reverse_lora_models = {v: k for k, v in ALL_LORA_MODELS.items()}
            # also handle qwen/YARN explicitly since we might map it differently
            reverse_lora_models["逼真"] = "qwen/YARN_1.0.safetensors"
            reverse_lora_models["菊花+内凹穴"] = "qwen/adjust_pussy_anus.safetensors"
            reverse_lora_models["真实质感"] = "qwen/realistic_texture.safetensors"
            reverse_lora_models["平胸/无毛穴"] = "qwen/flat_chest_hairless.safetensors"
            reverse_lora_models["扶他(阴茎)"] = "qwen/penis.safetensors"

            if lora_tag in reverse_lora_models:
                lora_name = reverse_lora_models[lora_tag]
            else:
                lora_name = lora_tag

        width = post.width if post.width is not None else history.width
        height = post.height if post.height is not None else history.height
        # Keep `duration` as media metadata; request canonical stays in
        # `requested_duration`.
        duration = post.duration if post.duration is not None else history.duration
        requested_duration = _resolve_legacy_requested_duration(
            history=history,
            duration=duration,
        )
        billing_resolution = _resolve_history_billing_resolution(
            history, width=width, height=height, gallery_post=post
        )

        return ApplyContextResponse(
            post_id=post.id,
            source_post_id=post.id,
            billing_resolution=billing_resolution,
            requested_duration=requested_duration,
            task_id=post.task_id,
            media_type=post.media_type,
            prompt=prompt,
            lora_name=lora_name,
            input_file=history.input_file,
            input_file_url=input_file_url,
            width=width,
            height=height,
            duration=duration,
            task_type=history.type,
        )


from src.core.gallery_core import (
    GalleryCoreError,
    get_gallery_feed,
    process_submit_to_gallery,
)


@router.post("/posts/submit/{task_id}")
async def submit_to_gallery(
    task_id: str,
    background_tasks: BackgroundTasks,
    request: GallerySubmitRequest = None,
    current_user: User = Depends(get_current_user),
):
    try:
        width = request.width if request else None
        height = request.height if request else None
        duration = request.duration if request else None
        
        result = await process_submit_to_gallery(
            current_user.id, task_id, background_tasks, width, height, duration
        )
        return result
    except GalleryCoreError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error submitting to gallery: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
