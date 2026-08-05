import logging
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import delete, select, update

from src.database.core import AsyncSessionLocal
from src.database.models import (
    GalleryComment,
    GalleryPost,
    GalleryPromptUnlock,
    GalleryReport,
    History,
    User,
    UserInteraction,
)
from src.services.submission_ban_service import (
    SubmissionBannedError,
    ensure_submission_allowed_for_user,
)
from src.services.storage_r2_cleanup import build_history_r2_cleanup_keys
from src.services.media_archive_service import enqueue_history_media_restore
from src.services.storage import storage
from src.web_api.common.utils import call_with_optional_db

logger = logging.getLogger(__name__)


async def _sync_gallery_history_public_flag(
    *,
    db,
    task_id: str | None,
    user_id: int,
    is_public: bool,
):
    if not task_id:
        return None

    histories = (
        await db.execute(
            select(History).where(History.task_id == task_id, History.user_id == user_id)
        )
    ).scalars().all()
    if not histories:
        return None

    primary_history = _select_primary_gallery_history(histories)
    for history in histories:
        history.is_public = is_public and history is primary_history
    return primary_history


def _select_primary_gallery_history(histories):
    if not histories:
        return None

    return sorted(
        histories,
        key=lambda history: (
            0 if getattr(history, "is_visible", True) else 1,
            0 if getattr(history, "is_public", False) else 1,
            getattr(history, "created_at", None) is None,
            getattr(history, "created_at", None),
            getattr(history, "id", 0) or 0,
        ),
    )[0]


async def _adjust_user_total_contributions(
    *,
    db,
    user_id: int,
    delta: int,
):
    if delta == 0:
        return

    user_obj = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user_obj:
        return

    user_obj.total_contributions = max((user_obj.total_contributions or 0) + delta, 0)


async def update_gallery_post_status(
    *,
    post_id: int,
    current_user,
    db,
    is_active: bool,
    enqueue_restore_func=enqueue_history_media_restore,
) -> dict:
    post = (
        await db.execute(select(GalleryPost).where(GalleryPost.id == post_id))
    ).scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="帖子不存在")
    if post.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作此帖子")
    if is_active:
        try:
            ensure_submission_allowed_for_user(current_user)
        except SubmissionBannedError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    state_changed = post.is_active != is_active
    post.is_active = is_active

    primary_history = await _sync_gallery_history_public_flag(
        db=db,
        task_id=post.task_id,
        user_id=current_user.id,
        is_public=is_active,
    )
    if is_active and primary_history is not None:
        await enqueue_restore_func(db, primary_history, priority=0)

    if state_changed:
        await _adjust_user_total_contributions(
            db=db,
            user_id=current_user.id,
            delta=1 if is_active else -1,
        )

    await db.commit()
    return {"status": "success", "message": f"已{'上架' if is_active else '下架'}"}


async def update_gallery_post_status_api_payload(
    *,
    post_id: int,
    current_user,
    db,
    is_active: bool,
    service_fn=None,
) -> dict:
    if service_fn is None:
        service_fn = update_gallery_post_status
    return await service_fn(
        post_id=post_id,
        current_user=current_user,
        db=db,
        is_active=is_active,
    )


async def delete_gallery_post(
    *,
    post_id: int,
    current_user,
    db,
    storage_service=storage,
    logger_override=logger,
) -> dict:
    r2_cleanup_keys: set[str] = set()
    post = (
        await db.execute(select(GalleryPost).where(GalleryPost.id == post_id))
    ).scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="帖子不存在")
    if post.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作此帖子")

    histories = []
    primary_history = None
    if post.task_id:
        histories = (
            await db.execute(
                select(History).where(
                    History.task_id == post.task_id, History.user_id == current_user.id
                )
            )
        ).scalars().all()
        primary_history = _select_primary_gallery_history(histories)

    if post.is_active:
        user_record = await db.execute(
            select(User).where(User.id == current_user.id)
        )
        user_obj = user_record.scalar_one_or_none()
        if user_obj:
            user_obj.total_contributions = max(
                (user_obj.total_contributions or 0) - 1, 0
            )

    if histories:
        for history in histories:
            history.is_public = False
        if primary_history and primary_history.output_file:
            r2_cleanup_keys = build_history_r2_cleanup_keys(
                post.task_id,
                primary_history.output_file,
                primary_history.type,
            )
    elif post.task_id:
        await db.execute(
            update(History)
            .where(
                History.task_id == post.task_id, History.user_id == current_user.id
            )
            .values(is_public=False)
        )

    await db.execute(
        update(GalleryReport)
        .where(
            GalleryReport.post_id == post_id,
            GalleryReport.status == "pending",
        )
        .values(
            status="resolved",
            resolved_at=datetime.now(),
            resolution_action="user_deleted",
        )
    )

    await db.execute(
        delete(UserInteraction).where(UserInteraction.post_id == post_id)
    )
    await db.execute(
        delete(GalleryPromptUnlock).where(GalleryPromptUnlock.post_id == post_id)
    )
    await db.execute(
        delete(GalleryComment).where(GalleryComment.post_id == post_id)
    )
    await db.execute(delete(GalleryPost).where(GalleryPost.id == post_id))

    await db.commit()

    if r2_cleanup_keys:
        try:
            await storage_service.async_delete_r2_objects(list(r2_cleanup_keys))
        except Exception:
            logger_override.warning(
                "Failed to clean R2 cache after deleting gallery post %s",
                post_id,
                exc_info=True,
            )

    return {"status": "success", "message": "删除成功"}


async def delete_gallery_post_api_payload(
    *,
    post_id: int,
    current_user,
    db=None,
    session_factory=None,
    service_fn=None,
) -> dict:
    return await call_with_optional_db(
        db=db,
        service_fn=service_fn or delete_gallery_post,
        session_factory=session_factory or AsyncSessionLocal,
        post_id=post_id,
        current_user=current_user,
    )


async def interact_with_gallery_post(
    *,
    post_id: int,
    action: str,
    current_user,
    toggle_like=None,
    gallery_core_error_cls=None,
    duplicate_interaction_error_cls=None,
    logger_override=logger,
) -> dict:
    try:
        if (
            toggle_like is None
            or gallery_core_error_cls is None
            or duplicate_interaction_error_cls is None
        ):
            from src.core.gallery_core import (
                DuplicateInteractionError,
                GalleryCoreError,
                toggle_like as core_toggle_like,
            )

            toggle_like = toggle_like or core_toggle_like
            gallery_core_error_cls = gallery_core_error_cls or GalleryCoreError
            duplicate_interaction_error_cls = (
                duplicate_interaction_error_cls or DuplicateInteractionError
            )
        result = await toggle_like(current_user.id, post_id, action)
        action_state = result.get("action_state")
        if action_state == "canceled":
            message = "已取消点赞" if action == "like" else "已取消点踩"
        else:
            message = "点赞成功" if action == "like" else "点踩成功"
        return {"status": "success", "message": message, "data": result}
    except duplicate_interaction_error_cls as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except gallery_core_error_cls as exc:
        if "不存在" in str(exc):
            raise HTTPException(status_code=404, detail=str(exc))
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger_override.error("发生未捕获异常", exc_info=True)
        raise HTTPException(status_code=500, detail="服务器内部错误")


async def interact_with_gallery_post_api_payload(
    *,
    post_id: int,
    action: str,
    current_user,
    service_fn=None,
) -> dict:
    if service_fn is None:
        service_fn = interact_with_gallery_post
    return await service_fn(
        post_id=post_id,
        action=action,
        current_user=current_user,
    )
