from fastapi import HTTPException
from sqlalchemy import func, select, update

from src.core.gallery_submission_effects import async_copy_to_r2_background
from src.media_paths import (
    build_r2_media_materialization_plan,
    get_media_type_from_history,
    resolve_storage_object,
)
from src.media_processor import generate_and_upload_thumbnail
from src.database.models import GalleryPost, History
from src.services.media_archive_service import enqueue_history_media_restore
from src.services.user_tier_policy_service import (
    get_identity_policy,
    load_user_tier_policy_config,
    resolve_effective_identity,
)
from src.web_api.services.history_query_service import (
    fetch_owned_histories_by_task_id,
    pick_preferred_history,
)


def _get_favorite_limit_for_identity(policy: dict, identity: str | None) -> int:
    return get_identity_policy(policy, identity)["benefits"]["favorite_limit"]


async def _count_visible_favorites_for_user(*, db, user_id: int) -> int:
    stmt = select(func.count(History.id)).where(
        History.user_id == user_id,
        History.is_favorited.is_(True),
        History.is_visible.is_(True),
    )
    result = await db.execute(stmt)
    return int(result.scalar() or 0)


async def _assert_can_add_favorite(*, db, current_user) -> None:
    identity = resolve_effective_identity(current_user)
    policy = await load_user_tier_policy_config()
    favorite_limit = _get_favorite_limit_for_identity(policy, identity)
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
    histories = await fetch_owned_histories_by_task_id(
        db=db,
        task_id=task_id,
        current_user_id=user_id,
    )
    history = pick_preferred_history(histories)
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
    enqueue_restore_func=enqueue_history_media_restore,
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
        await enqueue_restore_func(db, history, priority=0)
        await db.commit()

        media_type = get_media_type_from_history(history.type)
        materialization_plan = build_r2_media_materialization_plan(
            task_id=history.task_id,
            output_file=history.output_file,
            media_type=media_type,
        )

        if schedule_background_task is not None:
            if materialization_plan.original_copy_key:
                bucket_name, object_name = resolve_storage_object(history.output_file)
                schedule_background_task(
                    async_copy_to_r2_background,
                    bucket_name,
                    object_name,
                    materialization_plan.original_copy_key,
                )
            schedule_background_task(
                generate_and_upload_thumbnail,
                history.output_file,
                media_type,
                materialization_plan.thumbnail_key,
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
                GalleryPost.is_active.is_(True),
            )
            .values(is_active=False)
        )
        upd_result = await db.execute(upd_stmt)

        if upd_result.rowcount > 0:
            current_total = getattr(current_user, "total_contributions", 0) or 0
            current_user.total_contributions = max(current_total - 1, 0)

    await db.commit()
    return {"status": "success", "message": "记录已删除"}
