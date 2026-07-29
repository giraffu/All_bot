import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from dashboard.backend.schemas import (
    CommentUpdate,
    GalleryPostUpdate,
    GalleryUserSubmissionModerationRequest,
)
from dashboard.backend.services.gallery_admin_service import (
    ban_user_submissions_and_takedown_payload,
    delete_gallery_post_payload,
    get_all_gallery_comments_payload,
    get_all_gallery_posts_payload,
    get_all_gallery_reports_payload,
    get_gallery_comments_payload,
    resolve_gallery_report_payload,
    takedown_gallery_report_payload,
    update_gallery_comment_payload,
    update_gallery_post_payload,
)
from src.database.core import get_db

router = APIRouter(prefix="/api/gallery", tags=["gallery"])
logger = logging.getLogger("dashboard.gallery")


@router.get("/all")
async def get_all_gallery_posts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    is_active: Optional[bool] = None,
    media_type: Optional[str] = None,
    task_type: Optional[str] = None,
    sort_by: Optional[str] = None,
    username: Optional[str] = Query(None, max_length=100),
    user_id: Optional[int] = Query(None, ge=1),
    prompt_contains: Optional[str] = Query(None, max_length=500),
    prompt_max_length: Optional[int] = Query(None, ge=1, le=20000),
):
    return await get_all_gallery_posts_payload(
        page=page,
        page_size=page_size,
        is_active=is_active,
        media_type=media_type,
        task_type=task_type,
        sort_by=sort_by,
        username=username,
        author_user_id=user_id,
        prompt_contains=prompt_contains,
        prompt_max_length=prompt_max_length,
        logger_override=logger,
    )


@router.put("/{post_id:int}")
async def update_gallery_post(
    post_id: int, update_data: GalleryPostUpdate, db: AsyncSession = Depends(get_db)
):
    return await update_gallery_post_payload(
        post_id=post_id,
        update_data=update_data,
        db=db,
        logger_override=logger,
    )


@router.post("/users/{user_id:int}/ban-submissions-and-takedown")
async def ban_user_submissions_and_takedown(
    user_id: int,
    request: GalleryUserSubmissionModerationRequest,
    db: AsyncSession = Depends(get_db),
):
    return await ban_user_submissions_and_takedown_payload(
        user_id=user_id,
        request=request,
        db=db,
        logger_override=logger,
    )


@router.delete("/{post_id}")
async def delete_gallery_post(post_id: int, db: AsyncSession = Depends(get_db)):
    return await delete_gallery_post_payload(
        post_id=post_id,
        db=db,
        logger_override=logger,
    )


@router.get("/reports")
async def get_all_gallery_reports(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query("pending", pattern="^(pending|resolved|all)$"),
    reason: Optional[str] = Query(
        None,
        pattern="^(children|gore|gross|other|all)$",
    ),
    post_id: Optional[int] = Query(None, ge=1),
    db: AsyncSession = Depends(get_db),
):
    return await get_all_gallery_reports_payload(
        page=page,
        page_size=page_size,
        status=status,
        reason=reason,
        post_id=post_id,
        db=db,
        logger_override=logger,
    )


@router.post("/reports/{report_id:int}/resolve")
async def resolve_gallery_report(
    report_id: int,
    db: AsyncSession = Depends(get_db),
):
    return await resolve_gallery_report_payload(
        report_id=report_id,
        db=db,
        logger_override=logger,
    )


@router.post("/reports/{report_id:int}/takedown")
async def takedown_gallery_report(
    report_id: int,
    db: AsyncSession = Depends(get_db),
):
    return await takedown_gallery_report_payload(
        report_id=report_id,
        db=db,
        logger_override=logger,
    )


@router.get("/comments/all")
async def get_all_gallery_comments(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    post_id: Optional[int] = Query(None, ge=1),
    is_active: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
):
    return await get_all_gallery_comments_payload(
        page=page,
        page_size=page_size,
        post_id=post_id,
        is_active=is_active,
        db=db,
        logger_override=logger,
    )


@router.get("/comments")
async def get_gallery_comments(
    post_id: int = Query(..., ge=1),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    return await get_gallery_comments_payload(
        post_id=post_id,
        page=page,
        page_size=page_size,
        db=db,
        logger_override=logger,
    )


@router.put("/comments/{comment_id}")
async def update_gallery_comment(
    comment_id: int, update_data: CommentUpdate, db: AsyncSession = Depends(get_db)
):
    return await update_gallery_comment_payload(
        comment_id=comment_id,
        update_data=update_data,
        db=db,
        logger_override=logger,
    )
