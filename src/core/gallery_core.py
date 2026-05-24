from dataclasses import dataclass
import json
import logging
import re

from sqlalchemy import desc, func, select
from sqlalchemy.orm import selectinload

from src.database.core import AsyncSessionLocal
from src.database.models import GalleryPost, History, User, UserInteraction
from src.services.redis_client import redis_client
from src.constants import MODE_NAME_MAP
from src.services.storage import storage
from src.core.media_processor import generate_and_upload_thumbnail
from src.core.media_paths import (
    build_history_r2_media_key,
    build_history_r2_thumbnail_key,
    resolve_storage_object,
)

logger = logging.getLogger(__name__)

ALLOWED_WEB_SUBMIT_TYPES = [
    "i2i_pro",
    "i2i_draw",
    "custom_video",
    "video_lora",
    "ltx_video",
    "edit",
    "img2img_lora",
]


class GalleryCoreError(Exception):
    pass


class DuplicateInteractionError(GalleryCoreError):
    pass


@dataclass(slots=True)
class GallerySubmitOutcome:
    payload: dict
    side_effects: list[tuple[object, tuple[object, ...]]]


async def async_copy_to_r2_background(
    bucket_name: str, object_name: str, r2_object_name: str
):
    """Background task to copy file to R2."""
    try:
        await storage.async_copy_to_r2(bucket_name, object_name, r2_object_name)
    except Exception as e:
        logger.error(f"Background task failed to copy {object_name} to R2: {e}")


def build_gallery_submit_side_effects(
    *,
    task_id: str,
    output_file: str,
    media_type: str,
) -> list[tuple[object, tuple[object, ...]]]:
    bucket_name, object_name = resolve_storage_object(output_file)
    r2_object_name = build_history_r2_media_key(task_id, output_file)
    thumbnail_key = build_history_r2_thumbnail_key(task_id, media_type)
    return [
        (
            async_copy_to_r2_background,
            (bucket_name, object_name, r2_object_name),
        ),
        (
            generate_and_upload_thumbnail,
            (output_file, media_type, thumbnail_key),
        ),
    ]


async def process_submit_to_gallery_result(
    user_id: int,
    task_id: str,
    width: int = None,
    height: int = None,
    duration: int = None,
) -> GallerySubmitOutcome:
    """Core logic for submitting a task to the gallery."""
    # Check limit
    can_submit = await redis_client.check_gallery_submit_limit(user_id, limit=10)
    if not can_submit:
        raise GalleryCoreError("您今日的投稿次数已达 10 次上限，请明日再来~")

    async with AsyncSessionLocal() as session:
        # Check existing
        existing_res = await session.execute(
            select(GalleryPost).where(GalleryPost.task_id == task_id)
        )
        existing = existing_res.scalars().first()

        if existing:
            if existing.user_id != user_id:
                raise GalleryCoreError("无法操作他人的投稿！")

            if existing.is_active:
                raise GalleryCoreError("您已经投稿过此内容啦！")
            else:
                # 重新上架
                existing.is_active = True
                # Get History to update is_public
                hist_res = await session.execute(
                    select(History)
                    .where(History.task_id == task_id)
                    .where(History.user_id == user_id)
                )
                history = hist_res.scalars().first()
                if history:
                    history.is_public = True
                await session.commit()
                return GallerySubmitOutcome(
                    payload={
                        "status": "success",
                        "message": "已为您重新上架该作品！",
                        "tags": [],
                    },
                    side_effects=[],
                )

        # Get History
        hist_res = await session.execute(
            select(History)
            .where(History.task_id == task_id)
            .where(History.user_id == user_id)
        )
        history = hist_res.scalars().first()
        if not history:
            raise GalleryCoreError("无法找到对应的任务记录，投稿失败")

        if getattr(history, "allow_contribute", True) is False:
            raise GalleryCoreError(
                "这是一键应用他人的模板生成的作品，为了保护原创，暂不支持再次投稿。"
            )

        if history.type not in ALLOWED_WEB_SUBMIT_TYPES:
            allowed_names = [MODE_NAME_MAP.get(t, t) for t in ALLOWED_WEB_SUBMIT_TYPES]
            raise GalleryCoreError(
                f"暂不支持该类型记录的投稿，目前仅支持：{', '.join(allowed_names)}"
            )

        if not history.output_file:
            raise GalleryCoreError("此任务没有生成文件，无法投稿")

        # Determine media_type from output_file extension
        lower_path = history.output_file.lower()
        is_video = any(
            lower_path.endswith(ext)
            for ext in [".mp4", ".mov", ".webm", ".mkv", ".avi"]
        )
        media_type = "video" if is_video else "image"

        # Auto Tags
        tags = []
        base_tag = MODE_NAME_MAP.get(history.type, history.type)
        if base_tag:
            tags.append(f"#{base_tag}")

        if history.prompt:
            match = re.search(r"\[模型:\s*(.*?)\]\s*(.*)", history.prompt, re.DOTALL)
            if match:
                lora_tag = match.group(1).strip()
                tags.append(f"#{lora_tag}")

        tags_json = json.dumps(tags, ensure_ascii=False)

        new_post = GalleryPost(
            task_id=task_id,
            user_id=user_id,
            media_type=media_type,
            width=width,
            height=height,
            duration=duration,
            tags=tags_json,
        )
        session.add(new_post)

        # Increment total_contributions in users table
        user_record = await session.execute(select(User).where(User.id == user_id))
        user_obj = user_record.scalar_one_or_none()
        if user_obj:
            user_obj.total_contributions = (user_obj.total_contributions or 0) + 1

        history.is_public = True

        await session.commit()

        side_effects = build_gallery_submit_side_effects(
            task_id=task_id,
            output_file=history.output_file,
            media_type=media_type,
        )

        await redis_client.increment_gallery_submit(user_id)

        tags_str = " ".join(tags)
        return GallerySubmitOutcome(
            payload={
                "status": "success",
                "message": f"投稿成功！已自动添加标签：{tags_str}",
                "tags": tags,
            },
            side_effects=side_effects,
        )


async def toggle_like(user_id: int, post_id: int, action: str) -> dict:
    """Core logic for toggling like/dislike on a gallery post."""
    if action not in ["like", "dislike"]:
        raise GalleryCoreError("无效的操作类型")

    async with AsyncSessionLocal() as session:
        post = await session.get(GalleryPost, post_id)
        if not post:
            raise GalleryCoreError("帖子不存在")

        existing_inter = await session.execute(
            select(UserInteraction).where(
                UserInteraction.user_id == user_id,
                UserInteraction.post_id == post_id,
                UserInteraction.action_type.in_(["like", "dislike"]),
            )
        )
        inter = existing_inter.scalars().first()

        action_state = ""

        if inter:
            from sqlalchemy import update, delete, func

            if inter.action_type == action:
                # Cancel action
                stmt_del = delete(UserInteraction).where(
                    UserInteraction.user_id == user_id,
                    UserInteraction.post_id == post_id,
                    UserInteraction.action_type == action,
                )
                res_del = await session.execute(stmt_del)

                if res_del.rowcount > 0:
                    if action == "like":
                        stmt_upd = (
                            update(GalleryPost)
                            .where(GalleryPost.id == post_id)
                            .values(
                                likes_count=func.greatest(
                                    GalleryPost.likes_count - 1, 0
                                )
                            )
                            .returning(
                                GalleryPost.likes_count, GalleryPost.dislikes_count
                            )
                        )
                    else:
                        stmt_upd = (
                            update(GalleryPost)
                            .where(GalleryPost.id == post_id)
                            .values(
                                dislikes_count=func.greatest(
                                    GalleryPost.dislikes_count - 1, 0
                                )
                            )
                            .returning(
                                GalleryPost.likes_count, GalleryPost.dislikes_count
                            )
                        )

                    res = await session.execute(stmt_upd)
                    updated = res.fetchone()
                    post.likes_count = updated[0]
                    post.dislikes_count = updated[1]

                action_state = "canceled"
            else:
                # Switch action
                if inter.action_type == "like" and action == "dislike":
                    stmt = (
                        update(GalleryPost)
                        .where(GalleryPost.id == post_id)
                        .values(
                            likes_count=func.greatest(GalleryPost.likes_count - 1, 0),
                            dislikes_count=GalleryPost.dislikes_count + 1,
                        )
                        .returning(GalleryPost.likes_count, GalleryPost.dislikes_count)
                    )
                elif inter.action_type == "dislike" and action == "like":
                    stmt = (
                        update(GalleryPost)
                        .where(GalleryPost.id == post_id)
                        .values(
                            likes_count=GalleryPost.likes_count + 1,
                            dislikes_count=func.greatest(
                                GalleryPost.dislikes_count - 1, 0
                            ),
                        )
                        .returning(GalleryPost.likes_count, GalleryPost.dislikes_count)
                    )

                res = await session.execute(stmt)
                updated = res.fetchone()
                post.likes_count = updated[0]
                post.dislikes_count = updated[1]

                inter.action_type = action
                action_state = "switched"
        else:
            from sqlalchemy.dialects.postgresql import insert
            from sqlalchemy import update

            stmt_insert = (
                insert(UserInteraction)
                .values(user_id=user_id, post_id=post_id, action_type=action)
                .on_conflict_do_nothing()
            )

            result = await session.execute(stmt_insert)
            if result.rowcount > 0:
                if action == "like":
                    stmt = (
                        update(GalleryPost)
                        .where(GalleryPost.id == post_id)
                        .values(likes_count=GalleryPost.likes_count + 1)
                        .returning(GalleryPost.likes_count, GalleryPost.dislikes_count)
                    )
                else:
                    stmt = (
                        update(GalleryPost)
                        .where(GalleryPost.id == post_id)
                        .values(dislikes_count=GalleryPost.dislikes_count + 1)
                        .returning(GalleryPost.likes_count, GalleryPost.dislikes_count)
                    )

                res = await session.execute(stmt)
                updated = res.fetchone()
                post.likes_count = updated[0]
                post.dislikes_count = updated[1]
                action_state = "added"
            else:
                raise DuplicateInteractionError("您已经进行过此操作啦！")

        await session.commit()

        return {
            "likes_count": post.likes_count,
            "dislikes_count": post.dislikes_count,
            "action_state": action_state,
        }


async def record_apply_interaction(user_id: int, post_id: int):
    """
    Record an apply action for a gallery post when a task is actually generated.
    """
    from sqlalchemy.dialects.postgresql import insert
    from sqlalchemy import update

    async with AsyncSessionLocal() as session:
        try:
            stmt_insert = (
                insert(UserInteraction)
                .values(user_id=user_id, post_id=post_id, action_type="apply")
                .on_conflict_do_nothing()
            )

            result = await session.execute(stmt_insert)
            if result.rowcount > 0:
                stmt_update = (
                    update(GalleryPost)
                    .where(GalleryPost.id == post_id)
                    .values(applied_count=GalleryPost.applied_count + 1)
                )
                await session.execute(stmt_update)
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Failed to record apply interaction for post {post_id}: {e}")


async def get_gallery_feed(
    page: int = 1,
    size: int = 20,
    media_type: str = None,
    task_type: str = None,
    lora_model: str = None,
    sort_by: str = "latest",
    time_range: str = "all",
    user_id: int = None,
    category: str = None,
    is_active: bool = True,
) -> tuple[list, int]:
    """
    Core logic to fetch paginated gallery feed.
    Returns (posts, total_count).
    """
    async with AsyncSessionLocal() as session:
        query = select(GalleryPost)
        if is_active is True:
            query = query.where(GalleryPost.is_active == True)
        elif is_active is False:
            query = query.where(GalleryPost.is_active == False)

        # Join with History to filter by task_type or category
        if task_type and task_type != "all":
            query = query.join(History, GalleryPost.task_id == History.task_id)
            query = query.where(History.type == task_type)
        elif category and category != "all":
            query = query.join(History, GalleryPost.task_id == History.task_id)
            if category == "i2ipro":
                query = query.where(History.type == "i2i_pro")
            elif category == "faceswap":
                query = query.where(History.type.in_(["face_video"]))
            elif category == "edit":
                query = query.where(History.type.in_(["edit", "quick_image"]))
            elif category == "imglora":
                query = query.where(History.type == "img2img_lora")
            elif category == "custvid":
                query = query.where(History.type == "custom_video")
            elif category == "vidlora":
                query = query.where(History.type == "video_lora")
            elif category == "ltxvid":
                query = query.where(History.type == "ltx_video")

        if media_type and media_type != "all" and not task_type and not category:
            query = query.where(GalleryPost.media_type == media_type)

        if lora_model:
            lora_tag = f'"#{lora_model}"'
            query = query.where(GalleryPost.tags.like(f"%{lora_tag}%"))

        if user_id and sort_by == "mine":
            query = query.where(GalleryPost.user_id == user_id)

        from datetime import datetime, timedelta

        now = datetime.now()
        if time_range == "today":
            start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
            query = query.where(GalleryPost.created_at >= start_time)
        elif time_range == "week":
            start_time = now - timedelta(days=7)
            query = query.where(GalleryPost.created_at >= start_time)
        elif time_range == "month":
            start_time = now - timedelta(days=30)
            query = query.where(GalleryPost.created_at >= start_time)

        if sort_by == "likes":
            query = query.order_by(
                desc(GalleryPost.likes_count), desc(GalleryPost.created_at)
            )
        elif sort_by == "dislikes":
            query = query.order_by(
                desc(GalleryPost.dislikes_count), desc(GalleryPost.created_at)
            )
        elif sort_by == "absolute_likes":
            query = query.order_by(
                desc(GalleryPost.likes_count - GalleryPost.dislikes_count),
                desc(GalleryPost.created_at),
            )
        elif sort_by == "absolute_dislikes":
            query = query.order_by(
                desc(GalleryPost.dislikes_count - GalleryPost.likes_count),
                desc(GalleryPost.created_at),
            )
        elif sort_by == "applied":
            query = query.order_by(
                desc(GalleryPost.applied_count), desc(GalleryPost.created_at)
            )
        else:
            query = query.order_by(desc(GalleryPost.created_at))

        # Get total count dynamically
        total_query = select(func.count()).select_from(query.subquery())
        total = (await session.execute(total_query)).scalar()

        # Eager load related User and History
        query = query.options(
            selectinload(GalleryPost.user), selectinload(GalleryPost.histories)
        )

        # Paginate
        offset = (page - 1) * size if page > 0 else 0
        query = query.offset(offset).limit(size)

        result = await session.execute(query)
        posts = result.scalars().all()

        return posts, total
