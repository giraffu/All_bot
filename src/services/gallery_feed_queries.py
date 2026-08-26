from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import desc, func, not_, or_, select
from sqlalchemy.orm import selectinload

from src.constants import (
    MODE_FREE_EDIT_V2_5,
    MODE_IMAGE_TO_VIDEO,
    MODE_LTX_VIDEO,
    MODE_LTX_VIDEO_FLF2V,
    MODE_MINIMAX_H3_I2V,
    MODE_MINIMAX_H3_FLF2V,
    MODE_MINIMAX_H3_REF2V,
    MODE_PORNMASTER_FLUX2_MULTI_EDIT,
    MODE_PORNMASTER_FLUX2_EDIT_BF16,
    MODE_PORNMASTER_FLUX2_SINGLE_EDIT,
)
from src.database.models import GalleryPost, History, User
from src.domain_config.scail2_video import SCAIL2_FACE_SWAP_V2_TASK_TYPE
from src.lora_catalog import IMAGE_LORA_MODELS, VIDEO_LORA_MODELS
from src.services.compat_telemetry import record_compat_hit

GALLERY_LORA_MODEL_NONE = "__none__"
GALLERY_LTX_VIDEO_TASK_TYPES = (MODE_LTX_VIDEO, MODE_LTX_VIDEO_FLF2V)

GALLERY_GROUPED_TASK_TYPE_FAMILIES = {
    "edit_group": (
        "edit",
        "quick_image",
        "img2img_lora",
    ),
    "free_edit_v3_group": (
        MODE_PORNMASTER_FLUX2_EDIT_BF16,
        MODE_PORNMASTER_FLUX2_SINGLE_EDIT,
        MODE_PORNMASTER_FLUX2_MULTI_EDIT,
    ),
    "free_edit_v2_5_group": (MODE_FREE_EDIT_V2_5,),
    "free_edit_v2_group": (
        MODE_PORNMASTER_FLUX2_EDIT_BF16,
        MODE_PORNMASTER_FLUX2_SINGLE_EDIT,
        MODE_PORNMASTER_FLUX2_MULTI_EDIT,
    ),
    "img2video_group": ("custom_video", MODE_IMAGE_TO_VIDEO),
    "scail2_action_transfer": (
        "scail2_action_transfer",
        "scail2_action_transfer_long",
    ),
    MODE_LTX_VIDEO: GALLERY_LTX_VIDEO_TASK_TYPES,
    "minimax_h3": (
        MODE_MINIMAX_H3_I2V,
        MODE_MINIMAX_H3_FLF2V,
        MODE_MINIMAX_H3_REF2V,
    ),
}

GALLERY_GROUPED_TASK_TYPE_LORA_MODELS = {
    "edit_group": tuple(model for model in IMAGE_LORA_MODELS if model),
    "img2video_group": tuple(model for model in VIDEO_LORA_MODELS if model),
}


def _resolve_grouped_task_type_values(*, task_type: str | None, lora_model: str | None):
    _ = lora_model
    return resolve_gallery_task_type_filter_values(task_type)


def resolve_gallery_task_type_filter_values(task_type: str | None):
    if not task_type or task_type == "all":
        return None

    if task_type == "free_edit_v2_group":
        record_compat_hit(
            "compat.gallery.free_edit_v2_group",
            entrypoint="Gallery task_type filter",
        )
    grouped_values = GALLERY_GROUPED_TASK_TYPE_FAMILIES.get(task_type)
    if grouped_values is None:
        return (task_type,)

    return grouped_values


def _apply_active_filter(query, *, is_active: bool | None):
    if is_active is True:
        return query.where(GalleryPost.is_active.is_(True))
    if is_active is False:
        return query.where(GalleryPost.is_active.is_(False))
    return query


def _apply_task_type_or_category_filter(
    query,
    *,
    task_type: str | None,
    category: str | None,
    lora_model: str | None,
):
    task_type_values = _resolve_grouped_task_type_values(
        task_type=task_type,
        lora_model=lora_model,
    )
    if task_type_values:
        if len(task_type_values) == 1:
            return query.where(History.type == task_type_values[0])
        return query.where(History.type.in_(task_type_values))

    if not category or category == "all":
        return query

    if category == "i2ipro":
        return query.where(History.type == "i2i_pro")
    if category == "faceswap":
        return query.where(
            History.type.in_(["face_video", SCAIL2_FACE_SWAP_V2_TASK_TYPE])
        )
    if category == "edit":
        return query.where(History.type.in_(["edit", "quick_image"]))
    if category == "imglora":
        return query.where(History.type == "img2img_lora")
    if category == "custvid":
        return query.where(History.type == "custom_video")
    if category == "vidlora":
        return query.where(History.type == MODE_IMAGE_TO_VIDEO)
    if category == "ltxvid":
        return query.where(History.type.in_(GALLERY_LTX_VIDEO_TASK_TYPES))
    return query


def _requires_history_join(
    *,
    task_type: str | None,
    category: str | None,
    prompt_contains: str | None,
    prompt_max_length: int | None,
) -> bool:
    if task_type and task_type != "all":
        return True
    if category and category != "all":
        return True
    if prompt_contains and prompt_contains.strip():
        return True
    return prompt_max_length is not None


def _apply_author_username_filter(query, *, username: str | None):
    normalized_username = (username or "").strip()
    if not normalized_username:
        return query

    pattern = f"%{normalized_username}%"
    return query.join(User, GalleryPost.user_id == User.id).where(
        or_(
            User.username.ilike(pattern),
            User.full_name.ilike(pattern),
        )
    )


def _apply_prompt_filters(
    query,
    *,
    prompt_contains: str | None,
    prompt_max_length: int | None,
):
    normalized_prompt = (prompt_contains or "").strip()
    if normalized_prompt:
        query = query.where(History.prompt.ilike(f"%{normalized_prompt}%"))

    if prompt_max_length is not None:
        query = query.where(
            History.prompt.is_not(None),
            func.length(func.trim(History.prompt)) <= prompt_max_length,
        )

    return query


def _apply_media_filters(
    query,
    *,
    media_type: str | None,
    task_type: str | None,
    category: str | None,
    lora_model: str | None,
    user_id: int | None,
    sort_by: str,
):
    if media_type and media_type != "all" and not task_type and not category:
        query = query.where(GalleryPost.media_type == media_type)

    grouped_lora_models = GALLERY_GROUPED_TASK_TYPE_LORA_MODELS.get(task_type or "")
    if lora_model == GALLERY_LORA_MODEL_NONE and grouped_lora_models:
        addon_tag_filters = [
            GalleryPost.tags.like(f'%"{f"#{model_name}"}"%')
            for model_name in grouped_lora_models
        ]
        if addon_tag_filters:
            query = query.where(
                or_(
                    GalleryPost.tags.is_(None),
                    not_(or_(*addon_tag_filters)),
                )
            )

    if lora_model and lora_model not in {"all", GALLERY_LORA_MODEL_NONE}:
        lora_tag = f'"#{lora_model}"'
        query = query.where(GalleryPost.tags.like(f"%{lora_tag}%"))

    if user_id and sort_by == "mine":
        query = query.where(GalleryPost.user_id == user_id)

    return query


def _apply_time_range_filter(query, *, time_range: str):
    now = datetime.now()
    if time_range == "today":
        start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return query.where(GalleryPost.created_at >= start_time)
    if time_range == "week":
        return query.where(GalleryPost.created_at >= now - timedelta(days=7))
    if time_range == "month":
        return query.where(GalleryPost.created_at >= now - timedelta(days=30))
    return query


def _apply_sort(query, *, sort_by: str):
    if sort_by == "likes":
        return query.order_by(
            desc(GalleryPost.likes_count), desc(GalleryPost.created_at)
        )
    if sort_by == "dislikes":
        return query.order_by(
            desc(GalleryPost.dislikes_count), desc(GalleryPost.created_at)
        )
    if sort_by == "absolute_likes":
        sort_score = (
            GalleryPost.likes_count - GalleryPost.dislikes_count
        ).label("gallery_sort_score")
        return query.order_by(
            desc(sort_score),
            desc(GalleryPost.created_at),
        ).add_columns(sort_score)
    if sort_by == "absolute_dislikes":
        sort_score = (
            GalleryPost.dislikes_count - GalleryPost.likes_count
        ).label("gallery_sort_score")
        return query.order_by(
            desc(sort_score),
            desc(GalleryPost.created_at),
        ).add_columns(sort_score)
    if sort_by == "applied":
        return query.order_by(
            desc(GalleryPost.applied_count), desc(GalleryPost.created_at)
        )
    return query.order_by(desc(GalleryPost.created_at))


def build_gallery_feed_query(
    *,
    media_type: str | None,
    task_type: str | None,
    lora_model: str | None,
    sort_by: str,
    time_range: str,
    user_id: int | None,
    category: str | None,
    is_active: bool | None,
    username: str | None = None,
    prompt_contains: str | None = None,
    prompt_max_length: int | None = None,
    author_user_id: int | None = None,
):
    query = select(GalleryPost)
    query = _apply_active_filter(query, is_active=is_active)
    history_join_required = _requires_history_join(
        task_type=task_type,
        category=category,
        prompt_contains=prompt_contains,
        prompt_max_length=prompt_max_length,
    )
    if history_join_required:
        query = query.join(History, GalleryPost.task_id == History.task_id)
    query = _apply_task_type_or_category_filter(
        query,
        task_type=task_type,
        category=category,
        lora_model=lora_model,
    )
    query = _apply_media_filters(
        query,
        media_type=media_type,
        task_type=task_type,
        category=category,
        lora_model=lora_model,
        user_id=user_id,
        sort_by=sort_by,
    )
    query = _apply_time_range_filter(query, time_range=time_range)
    query = _apply_author_username_filter(query, username=username)
    if author_user_id is not None:
        query = query.where(GalleryPost.user_id == author_user_id)
    query = _apply_prompt_filters(
        query,
        prompt_contains=prompt_contains,
        prompt_max_length=prompt_max_length,
    )
    if history_join_required:
        query = query.distinct()
    query = _apply_sort(query, sort_by=sort_by)
    return query


async def fetch_gallery_feed_page(
    *,
    session,
    page: int,
    size: int,
    media_type: str | None,
    task_type: str | None,
    lora_model: str | None,
    sort_by: str,
    time_range: str,
    user_id: int | None,
    category: str | None,
    is_active: bool | None,
    username: str | None = None,
    prompt_contains: str | None = None,
    prompt_max_length: int | None = None,
    author_user_id: int | None = None,
) -> tuple[list, int]:
    query = build_gallery_feed_query(
        media_type=media_type,
        task_type=task_type,
        lora_model=lora_model,
        sort_by=sort_by,
        time_range=time_range,
        user_id=user_id,
        category=category,
        is_active=is_active,
        username=username,
        prompt_contains=prompt_contains,
        prompt_max_length=prompt_max_length,
        author_user_id=author_user_id,
    )

    total_query = select(func.count()).select_from(query.order_by(None).subquery())
    total = (await session.execute(total_query)).scalar()

    offset = (page - 1) * size if page > 0 else 0
    paged_query = (
        query.options(
            selectinload(GalleryPost.user), selectinload(GalleryPost.histories)
        )
        .offset(offset)
        .limit(size)
    )

    result = await session.execute(paged_query)
    return result.scalars().all(), total
