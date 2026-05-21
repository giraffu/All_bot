from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import select, update

from src.core.gallery_core import async_copy_to_r2_background
from src.core.media_paths import (
    build_history_r2_media_key,
    build_history_r2_thumbnail_key,
    get_media_type_from_history,
    resolve_storage_object,
)
from src.core.media_processor import generate_and_upload_thumbnail
from src.database.models import GalleryPost, History


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
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    history = await _load_owned_history_by_task_id(
        db=db,
        user_id=current_user.id,
        task_id=task_id,
    )

    if not history.output_file:
        raise HTTPException(status_code=400, detail="该任务没有生成文件")

    if not history.is_favorited:
        history.is_favorited = True
        await db.commit()

        bucket_name, object_name = resolve_storage_object(history.output_file)
        media_type = get_media_type_from_history(history.type)
        r2_object_name = build_history_r2_media_key(
            history.task_id,
            history.output_file,
        )

        background_tasks.add_task(
            async_copy_to_r2_background,
            bucket_name,
            object_name,
            r2_object_name,
        )
        background_tasks.add_task(
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
