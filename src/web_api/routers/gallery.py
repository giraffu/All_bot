import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Query

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
from src.database.core import AsyncSessionLocal
from src.database.models import History, User
from src.services.storage import storage
from src.web_api.dependencies import (
    CurrentUserDep,
    DbSessionDep,
    get_current_user,
)
from src.web_api.routers.utils import (
    build_storage_input_file_url,
    build_history_apply_context_response,
    call_with_optional_db,
    run_with_optional_db,
)
from src.web_api.presenters.media_presenter import resolve_media_url, resolve_thumbnail_url
from src.web_api.presenters.media_presenter import (
    resolve_gallery_media_urls as presenter_resolve_gallery_media_urls,
)
from src.web_api.services.gallery_service import (
    build_gallery_media_url,
    build_gallery_post_responses,
    build_gallery_thumbnail_url,
    build_gallery_config_payload,
    create_gallery_comment_payload,
    delete_gallery_post,
    get_gallery_comments_payload,
    get_gallery_apply_context_payload,
    get_gallery_posts_payload,
    get_my_favorite_posts_payload,
    get_my_gallery_posts_payload,
    interact_with_gallery_post,
    pick_gallery_media_urls as service_pick_gallery_media_urls,
    resolve_gallery_author_name,
    submit_gallery_post_payload,
    should_return_gallery_apply_input_file,
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

GALLERY_ALLOWED_TYPE_CONFIGS = [
    (MODE_I2I_PRO, "task.mode_i2i_pro"),
    (MODE_I2I_DRAW, "task.mode_i2i_draw"),
    (MODE_EDIT, "task.mode_edit"),
    ("img2img_lora", "task.mode_img2img_lora"),
    (MODE_CUSTOM_VIDEO, "task.mode_custom_video"),
    (MODE_VIDEO_LORA, "task.mode_video_lora"),
    (MODE_LTX_VIDEO, "task.mode_ltx_video"),
]


def _should_return_apply_input_file(history: History) -> bool:
    return should_return_gallery_apply_input_file(
        history,
        allow_input_reuse_task_types=APPLY_CONTEXT_ALLOW_INPUT_REUSE_TASK_TYPES,
    )



async def _pick_gallery_media_urls(
    *,
    task_id: str | None,
    output_file: str | None,
    media_type: str,
) -> tuple[str, str]:
    return await service_pick_gallery_media_urls(
        task_id=task_id,
        output_file=output_file,
        media_type=media_type,
        resolve_gallery_media_urls_fn=presenter_resolve_gallery_media_urls,
        build_media_url_fn=get_media_url,
        build_thumbnail_url_fn=generate_thumbnail_url,
        logger=logger,
    )


async def get_media_url(
    output_file: str | None,
    *,
    task_id: str | None = None,
) -> str:
    return await build_gallery_media_url(
        output_file=output_file,
        task_id=task_id,
        resolve_media_url_fn=resolve_media_url,
    )


async def generate_thumbnail_url(
    output_file: str | None,
    media_type: str,
    *,
    task_id: str | None = None,
) -> str:
    return await build_gallery_thumbnail_url(
        output_file=output_file,
        media_type=media_type,
        task_id=task_id,
        resolve_thumbnail_url_fn=resolve_thumbnail_url,
        resolve_storage_object_fn=resolve_storage_object,
        build_thumbnail_object_name_fn=build_thumbnail_object_name,
        get_presigned_url_fn=storage.get_presigned_url,
    )


@router.get("/config")
async def get_gallery_config():
    return build_gallery_config_payload(
        allowed_type_configs=GALLERY_ALLOWED_TYPE_CONFIGS,
        mode_name_map=MODE_NAME_MAP,
        video_lora_models=VIDEO_LORA_MODELS,
        image_lora_models=IMAGE_LORA_MODELS,
    )


async def _build_post_responses(session, posts, current_user: Optional[User]):
    return await build_gallery_post_responses(
        session=session,
        posts=posts,
        current_user=current_user,
        pick_gallery_media_urls=_pick_gallery_media_urls,
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
    return await run_with_optional_db(
        db=db,
        session_factory=AsyncSessionLocal,
        action=lambda session: get_gallery_posts_payload(
            page=page,
            size=size,
            media_type=media_type,
            task_type=task_type,
            lora_model=lora_model,
            sort_by=sort_by,
            time_range=time_range,
            current_user=current_user,
            db=session,
            fetch_gallery_feed=get_gallery_feed,
            build_post_responses_fn=_build_post_responses,
        ),
    )


@router.get("/my-posts", response_model=PaginatedGalleryResponse)
async def get_my_gallery_posts(
    current_user: CurrentUserDep,
    db: DbSessionDep = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    task_type: Optional[str] = None,
):
    return await call_with_optional_db(
        db=db,
        service_fn=get_my_gallery_posts_payload,
        session_factory=AsyncSessionLocal,
        current_user=current_user,
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
    return await call_with_optional_db(
        db=db,
        service_fn=get_my_favorite_posts_payload,
        session_factory=AsyncSessionLocal,
        current_user=current_user,
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
    return await call_with_optional_db(
        db=db,
        service_fn=delete_gallery_post,
        session_factory=AsyncSessionLocal,
        post_id=post_id,
        current_user=current_user,
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

    return await call_with_optional_db(
        db=db,
        service_fn=create_gallery_comment_payload,
        session_factory=AsyncSessionLocal,
        post_id=post_id,
        comment=comment,
        current_user=current_user,
        redis_client=redis_client,
        resolve_author_name=resolve_gallery_author_name,
    )


@router.get("/posts/{post_id}/comments", response_model=PaginatedCommentResponse)
async def get_gallery_comments(
    post_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: DbSessionDep = None,
):
    return await call_with_optional_db(
        db=db,
        service_fn=get_gallery_comments_payload,
        session_factory=AsyncSessionLocal,
        post_id=post_id,
        page=page,
        size=size,
        resolve_author_name=resolve_gallery_author_name,
    )

@router.get("/posts/{post_id}/apply-context", response_model=ApplyContextResponse)
async def get_apply_context(
    post_id: int,
    current_user: CurrentUserDep,
    db: DbSessionDep = None,
):
    _ = current_user
    return await call_with_optional_db(
        db=db,
        service_fn=get_gallery_apply_context_payload,
        session_factory=AsyncSessionLocal,
        post_id=post_id,
        build_history_apply_context_response_fn=build_history_apply_context_response,
        should_return_apply_input_file=_should_return_apply_input_file,
        build_input_file_url=build_storage_input_file_url,
    )


from src.core.gallery_core import (
    get_gallery_feed,
    process_submit_to_gallery,
)


@router.post("/posts/submit/{task_id}")
async def submit_to_gallery(
    task_id: str,
    background_tasks: BackgroundTasks,
    current_user: CurrentUserDep,
    request: GallerySubmitRequest = None,
):
    return await submit_gallery_post_payload(
        task_id=task_id,
        background_tasks=background_tasks,
        request=request,
        current_user=current_user,
        process_submit_to_gallery_fn=process_submit_to_gallery,
    )
