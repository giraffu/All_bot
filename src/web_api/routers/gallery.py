import asyncio
import logging
from typing import Annotated, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.lora_mapping import translate_tags
from src.constants import (
    MODE_CUSTOM_VIDEO,
    MODE_EDIT,
    MODE_I2I_PRO,
    MODE_I2I_DRAW,
    MODE_LTX_VIDEO,
    MODE_NAME_MAP,
    MODE_VIDEO_LORA,
)
from src.lora_catalog import IMAGE_LORA_MODELS, VIDEO_LORA_MODELS
from src.core.media_paths import (
    build_thumbnail_object_name,
    resolve_storage_object,
)
from src.core.media_urls import (
    build_storage_presigned_url,
)
from src.database.core import AsyncSessionLocal
from src.database.models import History, User
from src.services.storage import storage
from src.web_api.dependencies import get_current_user, get_db
from src.web_api.routers.utils import (
    build_history_apply_context_response,
    resolve_history_billing_resolution,
)
from src.web_api.presenters.media_presenter import resolve_media_url, resolve_thumbnail_url
from src.web_api.services.gallery_service import (
    build_apply_context_payload,
    build_post_responses as service_build_post_responses,
    create_gallery_comment_payload,
    delete_gallery_post,
    get_gallery_comments_payload,
    get_my_favorite_posts_payload,
    get_my_gallery_posts_payload,
    interact_with_gallery_post,
    update_gallery_post_status,
)
from src.web_api.schemas.gallery_schema import (
    ApplyContextResponse,
    PaginatedGalleryResponse,
    GallerySubmitRequest,
    CommentCreate,
    GalleryCommentResponse,
    PaginatedCommentResponse,
)

router = APIRouter()
logger = logging.getLogger(__name__)
CurrentUserDep = Annotated[User, Depends(get_current_user)]
DbSessionDep = Annotated[AsyncSession, Depends(get_db)]

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

APPLY_CONTEXT_ALLOW_INPUT_REUSE_TASK_TYPES = {
    "face_swap",
    "face_video",
}


def _resolve_author_name(user: User | None, fallback_user_id: int | None = None) -> str:
    if user:
        return user.full_name or user.username or f"User {user.id}"
    if fallback_user_id is not None:
        return f"User {fallback_user_id}"
    return "匿名修士"


def _should_return_apply_input_file(history: History) -> bool:
    return (history.type or "") in APPLY_CONTEXT_ALLOW_INPUT_REUSE_TASK_TYPES



async def _pick_gallery_media_urls(
    *,
    task_id: str | None,
    output_file: str | None,
    media_type: str,
) -> tuple[str, str]:
    if not output_file:
        return "", ""

    try:
        media_url, thumbnail_url = await asyncio.gather(
            get_media_url(
                output_file,
                task_id=task_id,
            ),
            generate_thumbnail_url(
                output_file,
                media_type,
                task_id=task_id,
            ),
        )
        return media_url or output_file, thumbnail_url
    except Exception as exc:
        logger.warning(
            "Failed to build gallery media URL for task_id=%s: %s",
            task_id,
            exc,
            exc_info=exc,
        )
        return output_file, ""


async def get_media_url(
    output_file: str | None,
    *,
    task_id: str | None = None,
) -> str:
    return await resolve_media_url(
        output_file,
        task_id=task_id,
        fallback_to_storage_path=True,
    )


async def generate_thumbnail_url(
    output_file: str | None,
    media_type: str,
    *,
    task_id: str | None = None,
) -> str:
    thumbnail_url = await resolve_thumbnail_url(
        output_file,
        media_type,
        task_id=task_id,
    )
    if thumbnail_url:
        return thumbnail_url

    if not output_file:
        return ""

    bucket_name, object_name = resolve_storage_object(output_file)
    thumb_object_name = build_thumbnail_object_name(object_name, media_type)
    return storage.get_presigned_url(thumb_object_name, bucket=bucket_name) or ""


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
    return await service_build_post_responses(
        session=session,
        posts=posts,
        current_user=current_user,
        translate_tags=translate_tags,
        resolve_history_billing_resolution=resolve_history_billing_resolution,
        resolve_author_name=_resolve_author_name,
        pick_gallery_media_urls=_pick_gallery_media_urls,
        logger=logger,
    )


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
    db: DbSessionDep = None,
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

    response_items = await _build_post_responses(db, posts, current_user)

    pages = (total + size - 1) // size
    return PaginatedGalleryResponse(
        items=response_items, total=total, page=page, size=size, pages=pages
    )


@router.get("/my-posts", response_model=PaginatedGalleryResponse)
async def get_my_gallery_posts(
    current_user: CurrentUserDep,
    db: DbSessionDep = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    task_type: Optional[str] = None,
):
    if db is not None:
        return await get_my_gallery_posts_payload(
            current_user=current_user,
            db=db,
            page=page,
            size=size,
            task_type=task_type,
            build_post_responses_fn=_build_post_responses,
        )
    async with AsyncSessionLocal() as fallback_db:
        return await get_my_gallery_posts_payload(
            current_user=current_user,
            db=fallback_db,
            page=page,
            size=size,
            task_type=task_type,
            build_post_responses_fn=_build_post_responses,
        )


@router.get("/my-favorites", response_model=PaginatedGalleryResponse)
async def get_my_favorite_posts(
    current_user: CurrentUserDep,
    db: DbSessionDep = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    filter_type: str = Query("all", pattern="^(all|like|apply)$"),
    task_type: Optional[str] = None,
):
    if db is not None:
        return await get_my_favorite_posts_payload(
            current_user=current_user,
            db=db,
            page=page,
            size=size,
            filter_type=filter_type,
            task_type=task_type,
            build_post_responses_fn=_build_post_responses,
        )
    async with AsyncSessionLocal() as fallback_db:
        return await get_my_favorite_posts_payload(
            current_user=current_user,
            db=fallback_db,
            page=page,
            size=size,
            filter_type=filter_type,
            task_type=task_type,
            build_post_responses_fn=_build_post_responses,
        )


@router.put("/posts/{post_id}/status")
async def update_post_status(
    post_id: int,
    current_user: CurrentUserDep,
    db: DbSessionDep,
    is_active: bool = Query(...),
):
    return await update_gallery_post_status(
        post_id=post_id,
        current_user=current_user,
        db=db,
        is_active=is_active,
    )


@router.delete("/posts/{post_id}")
async def delete_post(post_id: int, current_user: CurrentUserDep, db: DbSessionDep = None):
    if db is not None:
        return await delete_gallery_post(
            post_id=post_id,
            current_user=current_user,
            db=db,
            storage=storage,
            logger=logger,
        )
    async with AsyncSessionLocal() as fallback_db:
        return await delete_gallery_post(
            post_id=post_id,
            current_user=current_user,
            db=fallback_db,
            storage=storage,
            logger=logger,
        )


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

    return await interact_with_gallery_post(
        post_id=post_id,
        action=action,
        current_user=current_user,
        toggle_like=toggle_like,
        gallery_core_error_cls=GalleryCoreError,
        duplicate_interaction_error_cls=DuplicateInteractionError,
        logger=logger,
    )


@router.post("/posts/{post_id}/comments", response_model=GalleryCommentResponse)
async def create_gallery_comment(
    post_id: int,
    comment: CommentCreate,
    current_user: CurrentUserDep,
    db: DbSessionDep = None,
):
    from src.services.redis_client import redis_client
    if db is not None:
        return await create_gallery_comment_payload(
            post_id=post_id,
            comment=comment,
            current_user=current_user,
            db=db,
            redis_client=redis_client,
            resolve_author_name=_resolve_author_name,
        )
    async with AsyncSessionLocal() as fallback_db:
        return await create_gallery_comment_payload(
            post_id=post_id,
            comment=comment,
            current_user=current_user,
            db=fallback_db,
            redis_client=redis_client,
            resolve_author_name=_resolve_author_name,
        )


@router.get("/posts/{post_id}/comments", response_model=PaginatedCommentResponse)
async def get_gallery_comments(
    post_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: DbSessionDep = None,
):
    if db is not None:
        return await get_gallery_comments_payload(
            post_id=post_id,
            page=page,
            size=size,
            db=db,
            resolve_author_name=_resolve_author_name,
        )
    async with AsyncSessionLocal() as fallback_db:
        return await get_gallery_comments_payload(
            post_id=post_id,
            page=page,
            size=size,
            db=fallback_db,
            resolve_author_name=_resolve_author_name,
        )

async def _build_apply_context_response(
    post_id: int,
    current_user: User,
    db: AsyncSession,
) -> ApplyContextResponse:
    _ = current_user
    return await build_apply_context_payload(
        post_id=post_id,
        db=db,
        build_history_apply_context_response_fn=build_history_apply_context_response,
        should_return_apply_input_file=_should_return_apply_input_file,
        build_input_file_url=lambda file_path: build_storage_presigned_url(
            file_path,
            lambda object_name, bucket_name: storage.get_presigned_url(
                object_name, bucket=bucket_name
            ),
        ),
    )


@router.get("/posts/{post_id}/apply-context", response_model=ApplyContextResponse)
async def get_apply_context(
    post_id: int,
    current_user: CurrentUserDep,
    db: DbSessionDep = None,
):
    if db is not None:
        return await _build_apply_context_response(post_id, current_user, db)
    async with AsyncSessionLocal() as fallback_db:
        return await _build_apply_context_response(post_id, current_user, fallback_db)


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
