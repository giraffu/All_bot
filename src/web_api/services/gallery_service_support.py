import asyncio
import json
import logging

from fastapi import HTTPException
from sqlalchemy import select

from src.core.media_paths import build_thumbnail_object_name, resolve_storage_object
from src.database.models import History, User, UserInteraction
from src.lora_mapping import translate_tags
from src.services.storage import storage
from src.web_api.presenters.media_presenter import (
    resolve_gallery_media_urls as presenter_resolve_gallery_media_urls,
)
from src.web_api.presenters.media_presenter import resolve_media_url, resolve_thumbnail_url
from src.web_api.routers.utils import (
    call_with_optional_db,
    resolve_history_billing_resolution,
)
from src.web_api.schemas.gallery_schema import GalleryPostResponse

logger = logging.getLogger(__name__)

DEFAULT_GALLERY_ALLOWED_TYPE_CONFIGS = [
    ("i2i_pro", "task.mode_i2i_pro"),
    ("i2i_draw", "task.mode_i2i_draw"),
    ("edit", "task.mode_edit"),
    ("img2img_lora", "task.mode_img2img_lora"),
    ("custom_video", "task.mode_custom_video"),
    ("video_lora", "task.mode_video_lora"),
    ("ltx_video", "task.mode_ltx_video"),
]

APPLY_CONTEXT_ALLOW_INPUT_REUSE_TASK_TYPES = {
    "face_swap",
    "face_video",
}


def build_gallery_config_payload(
    *,
    allowed_type_configs: list[tuple[str, str]],
    mode_name_map: dict[str, str],
    video_lora_models: dict[str, str],
    image_lora_models: dict[str, str],
) -> dict[str, list[dict[str, str]]]:
    return {
        "allowed_types": [
            {"id": task_type, "name": mode_name_map.get(task_type, fallback_name)}
            for task_type, fallback_name in allowed_type_configs
        ],
        "lora_models": [{"id": key, "name": value} for key, value in video_lora_models.items()],
        "img2img_lora_models": [
            {"id": key, "name": value}
            for key, value in image_lora_models.items()
            if key
        ],
    }


async def submit_gallery_post_payload(
    *,
    task_id: str,
    background_tasks,
    request,
    current_user,
    process_submit_to_gallery_fn=None,
) -> dict:
    try:
        if process_submit_to_gallery_fn is None:
            from src.core.gallery_core import process_submit_to_gallery

            process_submit_to_gallery_fn = process_submit_to_gallery
        width = request.width if request else None
        height = request.height if request else None
        duration = request.duration if request else None
        return await process_submit_to_gallery_fn(
            current_user.id,
            task_id,
            background_tasks,
            width,
            height,
            duration,
        )
    except HTTPException:
        raise
    except Exception as exc:
        if exc.__class__.__name__ == "GalleryCoreError":
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        logger.error(
            "Unexpected error submitting to gallery for user_id=%s task_id=%s: %s",
            getattr(current_user, "id", None),
            task_id,
            exc,
        )
        raise HTTPException(status_code=500, detail="Internal server error") from exc


def should_return_gallery_apply_input_file(
    history: History,
    *,
    allow_input_reuse_task_types: set[str],
) -> bool:
    return (history.type or "") in allow_input_reuse_task_types


def default_should_return_gallery_apply_input_file(history: History) -> bool:
    return should_return_gallery_apply_input_file(
        history,
        allow_input_reuse_task_types=APPLY_CONTEXT_ALLOW_INPUT_REUSE_TASK_TYPES,
    )


async def build_gallery_media_url(
    output_file: str | None,
    *,
    task_id: str | None,
    resolve_media_url_fn,
) -> str:
    return await resolve_media_url_fn(
        output_file,
        task_id=task_id,
        fallback_to_storage_path=True,
    )


async def build_gallery_thumbnail_url(
    output_file: str | None,
    media_type: str,
    *,
    task_id: str | None,
    resolve_thumbnail_url_fn,
    resolve_storage_object_fn,
    build_thumbnail_object_name_fn,
    async_object_exists_fn,
    get_presigned_url_fn,
) -> str:
    thumbnail_url = await resolve_thumbnail_url_fn(
        output_file,
        media_type,
        task_id=task_id,
    )
    if thumbnail_url:
        return thumbnail_url

    if not output_file:
        return ""

    bucket_name, object_name = resolve_storage_object_fn(output_file)
    thumb_object_name = build_thumbnail_object_name_fn(object_name, media_type)
    if not await async_object_exists_fn(bucket_name, thumb_object_name):
        return ""
    return get_presigned_url_fn(thumb_object_name, bucket=bucket_name) or ""


async def pick_gallery_media_urls(
    *,
    task_id: str | None,
    output_file: str | None,
    media_type: str,
    resolve_gallery_media_urls_fn,
    build_media_url_fn,
    build_thumbnail_url_fn,
    logger,
) -> tuple[str, str]:
    return await resolve_gallery_media_urls_fn(
        task_id=task_id,
        output_file=output_file,
        media_type=media_type,
        build_media_url=build_media_url_fn,
        build_thumbnail_url=build_thumbnail_url_fn,
        logger=logger,
    )


async def resolve_gallery_post_media_urls(
    *,
    task_id: str | None,
    output_file: str | None,
    media_type: str,
) -> tuple[str, str]:
    return await pick_gallery_media_urls(
        task_id=task_id,
        output_file=output_file,
        media_type=media_type,
        resolve_gallery_media_urls_fn=presenter_resolve_gallery_media_urls,
        build_media_url_fn=lambda output_file, *, task_id=None: build_gallery_media_url(
            output_file=output_file,
            task_id=task_id,
            resolve_media_url_fn=resolve_media_url,
        ),
        build_thumbnail_url_fn=lambda output_file, media_type, *, task_id=None: build_gallery_thumbnail_url(
            output_file=output_file,
            media_type=media_type,
            task_id=task_id,
            resolve_thumbnail_url_fn=resolve_thumbnail_url,
            resolve_storage_object_fn=resolve_storage_object,
            build_thumbnail_object_name_fn=build_thumbnail_object_name,
            async_object_exists_fn=storage.async_object_exists,
            get_presigned_url_fn=storage.get_presigned_url,
        ),
        logger=logger,
    )


def resolve_gallery_author_name(
    user: User | None,
    fallback_user_id: int | None = None,
) -> str:
    if user:
        return user.full_name or user.username or f"User {user.id}"
    if fallback_user_id is not None:
        return f"User {fallback_user_id}"
    return "匿名修士"


async def build_post_responses(
    *,
    session,
    posts,
    current_user,
    translate_tags_func,
    resolve_history_billing_resolution_func,
    resolve_author_name,
    pick_gallery_media_urls_func,
    logger,
    gallery_post_response_cls,
) -> list:
    if not posts:
        return []

    post_ids = [p.id for p in posts]
    task_ids = [p.task_id for p in posts if p.task_id]

    user_likes = set()
    user_dislikes = set()
    if current_user and post_ids:
        interactions = (
            (
                await session.execute(
                    select(UserInteraction)
                    .where(UserInteraction.user_id == current_user.id)
                    .where(UserInteraction.post_id.in_(post_ids))
                    .where(UserInteraction.action_type.in_(["like", "dislike"]))
                )
            )
            .scalars()
            .all()
        )
        for inter in interactions:
            if inter.action_type == "like":
                user_likes.add(inter.post_id)
            elif inter.action_type == "dislike":
                user_dislikes.add(inter.post_id)

    history_map = {}
    if task_ids:
        histories = (
            (await session.execute(select(History).where(History.task_id.in_(task_ids))))
            .scalars()
            .all()
        )
        history_map = {h.task_id: h for h in histories}

    user_ids = list(set([p.user_id for p in posts if p.user_id]))
    user_map = {}
    if user_ids:
        users = (
            (await session.execute(select(User).where(User.id.in_(user_ids))))
            .scalars()
            .all()
        )
        for user in users:
            name = user.full_name if user.full_name else (user.username or f"User {user.id}")
            user_map[user.id] = name

    tasks = []
    for post in posts:
        history = history_map.get(post.task_id)
        output_file = history.output_file if history else None
        tasks.append(
            pick_gallery_media_urls_func(
                task_id=post.task_id,
                output_file=output_file,
                media_type=post.media_type,
            )
        )
    urls_results = await asyncio.gather(*tasks, return_exceptions=True)

    response_items = []
    for index, post in enumerate(posts):
        try:
            tags = json.loads(post.tags) if post.tags else []
        except Exception:
            tags = []
        translated_tags = translate_tags_func(tags)

        history = history_map.get(post.task_id)
        prompt = history.prompt if history else None
        task_type_from_history = history.type if history else None

        url_result = urls_results[index]
        if isinstance(url_result, Exception):
            logger.warning(
                "Failed to build gallery media URLs for post_id=%s task_id=%s: %s",
                post.id,
                post.task_id,
                url_result,
                exc_info=url_result,
            )
            media_url = history.output_file if history and history.output_file else ""
            thumbnail_url = ""
        else:
            media_url, thumbnail_url = url_result

        billing_resolution = None
        if history:
            billing_resolution = resolve_history_billing_resolution_func(
                history,
                width=post.width if post.width is not None else history.width,
                height=post.height if post.height is not None else history.height,
                gallery_post=post,
            )

        response_items.append(
            gallery_post_response_cls(
                id=post.id,
                task_id=post.task_id,
                media_type=post.media_type,
                billing_resolution=billing_resolution,
                width=post.width,
                height=post.height,
                duration=post.duration,
                tags=translated_tags,
                likes_count=post.likes_count,
                dislikes_count=post.dislikes_count,
                applied_count=post.applied_count,
                comments_count=post.comments_count or 0,
                thumbnail_url=thumbnail_url,
                media_url=media_url,
                created_at=post.created_at,
                is_active=post.is_active,
                prompt=prompt,
                task_type=task_type_from_history,
                has_liked=post.id in user_likes,
                has_disliked=post.id in user_dislikes,
                author_name=user_map.get(post.user_id)
                if post.user_id
                else resolve_author_name(None),
            )
        )
    return response_items


async def build_gallery_post_responses(
    *,
    session,
    posts,
    current_user,
    gallery_post_response_cls=GalleryPostResponse,
    pick_gallery_media_urls=resolve_gallery_post_media_urls,
) -> list:
    return await build_post_responses(
        session=session,
        posts=posts,
        current_user=current_user,
        translate_tags_func=translate_tags,
        resolve_history_billing_resolution_func=resolve_history_billing_resolution,
        resolve_author_name=resolve_gallery_author_name,
        pick_gallery_media_urls_func=pick_gallery_media_urls,
        logger=logger,
        gallery_post_response_cls=gallery_post_response_cls,
    )


async def call_gallery_service_with_optional_db(
    *,
    db,
    service_fn,
    session_factory,
    **kwargs,
):
    return await call_with_optional_db(
        db=db,
        service_fn=service_fn,
        session_factory=session_factory,
        **kwargs,
    )
