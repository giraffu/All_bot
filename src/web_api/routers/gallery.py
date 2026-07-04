from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from src.constants import (
    MODE_NAME_MAP,
)
from src.database.models import User
from src.lora_catalog import IMAGE_LORA_MODELS, VIDEO_LORA_MODELS
from src.web_api.dependencies import (
    CurrentUserDep,
    DbSessionDep,
    get_current_user,
)
from src.web_api.services.gallery_service_comments import (
    create_gallery_comment_api_payload,
    get_gallery_comments_api_payload,
)
from src.web_api.services.gallery_service_mutations import (
    delete_gallery_post_api_payload,
    interact_with_gallery_post_api_payload,
    update_gallery_post_status_api_payload,
)
from src.web_api.services.gallery_service_queries import (
    get_gallery_apply_context_api_payload,
    get_gallery_posts_api_payload,
    get_my_favorite_posts_api_payload,
    get_my_gallery_posts_api_payload,
    get_my_prompt_unlocked_posts_api_payload,
)
from src.web_api.services.gallery_prompt_unlock_service import (
    unlock_gallery_prompt_payload,
)
from src.web_api.services.gallery_report_service import (
    create_gallery_report_api_payload,
)
from src.web_api.services.users_history_service import (
    get_history_apply_context_for_current_user,
)
from src.web_api.services.gallery_service_support import (
    DEFAULT_GALLERY_ALLOWED_TYPE_CONFIGS,
    build_gallery_config_payload,
    submit_gallery_post_payload,
)
from src.web_api.schemas.gallery_schema import (
    ApplyContextResponse,
    PaginatedGalleryResponse,
    GallerySubmitRequest,
    CommentCreate,
    GalleryCommentResponse,
    GalleryReportCreate,
    GalleryReportSubmitResponse,
    PaginatedCommentResponse,
    PromptUnlockResponse,
)

router = APIRouter()

@router.get("/config")
async def get_gallery_config():
    return build_gallery_config_payload(
        allowed_type_configs=DEFAULT_GALLERY_ALLOWED_TYPE_CONFIGS,
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


@router.get("/my-prompt-unlocks", response_model=PaginatedGalleryResponse)
async def get_my_prompt_unlocked_posts(
    current_user: CurrentUserDep,
    db: DbSessionDep = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    task_type: Optional[str] = None,
):
    return await get_my_prompt_unlocked_posts_api_payload(
        current_user=current_user,
        page=page,
        size=size,
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
    current_user: CurrentUserDep,
    action: str = Query(..., pattern="^(like|dislike)$"),
):
    return await interact_with_gallery_post_api_payload(
        post_id=post_id,
        action=action,
        current_user=current_user,
    )


@router.post("/posts/{post_id}/prompt-unlock", response_model=PromptUnlockResponse)
async def unlock_post_prompt(
    post_id: int,
    current_user: CurrentUserDep,
    db: DbSessionDep,
):
    return await unlock_gallery_prompt_payload(
        post_id=post_id,
        current_user=current_user,
        db=db,
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


@router.post("/posts/{post_id}/reports", response_model=GalleryReportSubmitResponse)
async def create_gallery_report(
    post_id: int,
    report: GalleryReportCreate,
    current_user: CurrentUserDep,
    db: DbSessionDep = None,
):
    return await create_gallery_report_api_payload(
        post_id=post_id,
        report=report,
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


@router.get("/items/{item_id}/apply-context", response_model=ApplyContextResponse)
async def get_item_apply_context(
    item_id: str,
    current_user: CurrentUserDep,
    db: DbSessionDep = None,
    source: str = Query(default="gallery", pattern="^(gallery|favorites|submissions)$"),
):
    if source == "favorites":
        return await get_history_apply_context_for_current_user(
            task_id=item_id,
            current_user=current_user,
            db=db,
        )

    try:
        post_id = int(item_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="无效的作品标识") from exc

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
        schedule_background_task=getattr(background_tasks, "add_task", None),
        request=request,
        current_user=current_user,
    )
