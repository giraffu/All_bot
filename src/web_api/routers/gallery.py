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
from src.database.models import User
from src.web_api.dependencies import (
    CurrentUserDep,
    DbSessionDep,
    get_current_user,
)
from src.web_api.services.gallery_service import (
    build_gallery_config_payload,
    create_gallery_comment_api_payload,
    delete_gallery_post_api_payload,
    get_gallery_comments_api_payload,
    get_gallery_apply_context_api_payload,
    get_gallery_posts_api_payload,
    get_my_favorite_posts_api_payload,
    get_my_gallery_posts_api_payload,
    interact_with_gallery_post_api_payload,
    submit_gallery_post_payload,
    update_gallery_post_status_api_payload,
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

GALLERY_ALLOWED_TYPE_CONFIGS = [
    (MODE_I2I_PRO, "task.mode_i2i_pro"),
    (MODE_I2I_DRAW, "task.mode_i2i_draw"),
    (MODE_EDIT, "task.mode_edit"),
    ("img2img_lora", "task.mode_img2img_lora"),
    (MODE_CUSTOM_VIDEO, "task.mode_custom_video"),
    (MODE_VIDEO_LORA, "task.mode_video_lora"),
    (MODE_LTX_VIDEO, "task.mode_ltx_video"),
]
@router.get("/config")
async def get_gallery_config():
    return build_gallery_config_payload(
        allowed_type_configs=GALLERY_ALLOWED_TYPE_CONFIGS,
        mode_name_map=MODE_NAME_MAP,
        video_lora_models=VIDEO_LORA_MODELS,
        image_lora_models=IMAGE_LORA_MODELS,
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
    return await get_gallery_posts_api_payload(
        page=page,
        size=size,
        media_type=media_type,
        task_type=task_type,
        lora_model=lora_model,
        sort_by=sort_by,
        time_range=time_range,
        current_user=current_user,
        db=db,
    )


@router.get("/my-posts", response_model=PaginatedGalleryResponse)
async def get_my_gallery_posts(
    current_user: CurrentUserDep,
    db: DbSessionDep = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    task_type: Optional[str] = None,
):
    return await get_my_gallery_posts_api_payload(
        current_user=current_user,
        page=page,
        size=size,
        task_type=task_type,
        db=db,
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
    return await get_my_favorite_posts_api_payload(
        current_user=current_user,
        page=page,
        size=size,
        filter_type=filter_type,
        task_type=task_type,
        db=db,
    )


@router.put("/posts/{post_id}/status")
async def update_post_status(
    post_id: int,
    current_user: CurrentUserDep,
    db: DbSessionDep,
    is_active: bool = Query(...),
):
    return await update_gallery_post_status_api_payload(
        post_id=post_id,
        current_user=current_user,
        db=db,
        is_active=is_active,
    )


@router.delete("/posts/{post_id}")
async def delete_post(post_id: int, current_user: CurrentUserDep, db: DbSessionDep = None):
    return await delete_gallery_post_api_payload(
        post_id=post_id,
        current_user=current_user,
        db=db,
    )


@router.post("/posts/{post_id}/interact")
async def interact_with_post(
    post_id: int,
    action: str = Query(..., pattern="^(like|dislike)$"),
    current_user: User = Depends(get_current_user),
):
    return await interact_with_gallery_post_api_payload(
        post_id=post_id,
        action=action,
        current_user=current_user,
    )


@router.post("/posts/{post_id}/comments", response_model=GalleryCommentResponse)
async def create_gallery_comment(
    post_id: int,
    comment: CommentCreate,
    current_user: CurrentUserDep,
    db: DbSessionDep = None,
):
    return await create_gallery_comment_api_payload(
        post_id=post_id,
        comment=comment,
        current_user=current_user,
        db=db,
    )


@router.get("/posts/{post_id}/comments", response_model=PaginatedCommentResponse)
async def get_gallery_comments(
    post_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: DbSessionDep = None,
):
    return await get_gallery_comments_api_payload(
        post_id=post_id,
        page=page,
        size=size,
        db=db,
    )

@router.get("/posts/{post_id}/apply-context", response_model=ApplyContextResponse)
async def get_apply_context(
    post_id: int,
    current_user: CurrentUserDep,
    db: DbSessionDep = None,
):
    return await get_gallery_apply_context_api_payload(
        post_id=post_id,
        current_user=current_user,
        db=db,
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
    )
