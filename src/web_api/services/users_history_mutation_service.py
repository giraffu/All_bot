from fastapi import HTTPException
from sqlalchemy import func, select, update

from src.constants import DEFAULT_FAVORITE_LIMIT, FAVORITE_LIMITS_BY_IDENTITY
from src.core.gallery_submission_effects import async_copy_to_r2_background
from src.core.media_paths import (
    build_history_r2_media_key,
    build_history_r2_thumbnail_key,
    get_media_type_from_history,
    resolve_storage_object,
)
from src.core.media_processor import generate_and_upload_thumbnail
from src.database.models import GalleryPost, History


def _get_favorite_limit_for_identity(identity: str | None) -> int:
    normalized_identity = identity or "外门弟子"
    return FAVORITE_LIMITS_BY_IDENTITY.get(normalized_identity, DEFAULT_FAVORITE_LIMIT)


async def _count_visible_favorites_for_user(*, db, user_id: int) -> int:
    stmt = select(func.count(History.id)).where(
        History.user_id == user_id,
        History.is_favorited == True,
        History.is_visible == True,
    )
    result = await db.execute(stmt)
    return int(result.scalar() or 0)


async def _assert_can_add_favorite(*, db, current_user) -> None:
    identity = getattr(current_user, "current_identity", None)
    favorite_limit = _get_favorite_limit_for_identity(identity)
    favorite_count = await _count_visible_favorites_for_user(
        db=db,
        user_id=current_user.id,
    )
    if favorite_count >= favorite_limit:
        identity_display = identity or "外门弟子"
        raise HTTPException(
            status_code=400,
            detail=f"当前身份“{identity_display}”的收藏上限为 {favorite_limit}，请先取消部分收藏后再试",
        )


async def _load_owned_history_by_task_id(*, db, user_id: int, task_id: str) -> History:
    stmt = select(History).where(History.task_id == task_id, History.user_id == user_id)
    result = await db.execute(stmt)
    history = result.scalar_one_or_none()
    if not history:
        raise HTTPException(status_code=404, detail="未找到原任务详情")
    return history


async def _load_owned_history_by_id(*, db, user_id: int, history_id: int) -> History:
    stmt = select(History).where(History.id == history_id, History.user_id == user_id)
    result = await db.execute(stmt)
    history = result.scalar_one_or_none()
    if not history:
        raise HTTPException(status_code=404, detail="未找到对应的记录")
    return history


async def favorite_user_history(
    *,
    task_id: str,
    current_user,
    db,
    schedule_background_task=None,
) -> dict[str, str]:
    history = await _load_owned_history_by_task_id(
        db=db,
        user_id=current_user.id,
        task_id=task_id,
    )

    if not history.output_file:
        raise HTTPException(status_code=400, detail="该任务没有生成文件")

    if not history.is_favorited:
        await _assert_can_add_favorite(db=db, current_user=current_user)
        history.is_favorited = True
        await db.commit()

        bucket_name, object_name = resolve_storage_object(history.output_file)
        media_type = get_media_type_from_history(history.type)
        r2_object_name = build_history_r2_media_key(
            history.task_id,
            history.output_file,
        )

        if schedule_background_task is not None:
            schedule_background_task(
                async_copy_to_r2_background,
                bucket_name,
                object_name,
                r2_object_name,
            )
            schedule_background_task(
                generate_and_upload_thumbnail,
                history.output_file,
                media_type,
                build_history_r2_thumbnail_key(history.task_id, media_type),
            )

    return {"status": "success", "message": "收藏成功"}


async def unfavorite_user_history(
    *,
    task_id: str,
    current_user,
    db,
) -> dict[str, str]:
    history = await _load_owned_history_by_task_id(
        db=db,
        user_id=current_user.id,
        task_id=task_id,
    )

    if history.is_favorited:
        history.is_favorited = False
        await db.commit()

    return {"status": "success", "message": "已取消收藏"}


async def soft_delete_user_history(
    *,
    history_id: int,
    current_user,
    db,
) -> dict[str, str]:
    history = await _load_owned_history_by_id(
        db=db,
        user_id=current_user.id,
        history_id=history_id,
    )

    if not history.is_visible:
        return {"status": "success", "message": "记录已删除"}

    history.is_visible = False

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
            current_total = getattr(current_user, "total_contributions", 0) or 0
            current_user.total_contributions = max(current_total - 1, 0)

    await db.commit()
    return {"status": "success", "message": "记录已删除"}
