import asyncio
import re

from src.core.media_paths import get_media_type_from_history
from src.services.wan22_video_v2_extension_service import (
    extract_wan22_history_context,
    is_wan22_stitched_result,
    resolve_wan22_segment_index,
    resolve_wan22_stitched_segment_count,
)
from src.services.ltx_video_extension_service import (
    extract_ltx_history_context,
    is_ltx_video_history_task_type,
    is_ltx_stitched_result,
    resolve_ltx_segment_index,
    resolve_ltx_stitched_segment_count,
)
from src.domain_config.wan22_aio_video import is_wan22_chain_history_task_type
from src.web_api.common.utils import (
    build_storage_input_file_url,
    resolve_history_billing_resolution,
)
from src.web_api.presenters.media_presenter import (
    extract_history_result_meta,
    filter_user_visible_extra_outputs,
    resolve_history_extra_outputs,
    resolve_history_media_urls,
)
from src.web_api.schemas.gallery_schema import GalleryPostResponse
from src.web_api.schemas.user_schema import HistoryItem
from src.web_api.services.apply_context_service import (
    resolve_history_template_apply_disabled_reason,
)
from src.web_api.services.history_input_presenter import (
    build_history_input_file_payload,
)


def extract_history_tags(
    prompt: str | None,
    *,
    task_type: str | None = None,
    extra_outputs: dict | None = None,
) -> list[str]:
    tags: list[str] = []
    if prompt:
        match = re.search(r"\\[模型:\\s*(.*?)\\]", prompt)
        if match:
            tags.append(f"#{match.group(1).strip()}")
    if is_wan22_chain_history_task_type(task_type):
        if is_wan22_stitched_result(extra_outputs):
            segment_count = resolve_wan22_stitched_segment_count(extra_outputs)
            if segment_count:
                tags.append(f"task.wan22_stitched_video:{segment_count}")
            return tags
        result_meta = extract_wan22_history_context(extra_outputs)
        tags.append(
            "task.wan22_start_end_frame"
            if bool(result_meta.get("wan22_use_end_frame"))
            else "task.wan22_start_frame"
        )
        segment_index = resolve_wan22_segment_index(extra_outputs)
        if segment_index:
            tags.append(f"task.wan22_segment:{segment_index}")
    if is_ltx_video_history_task_type(task_type):
        if is_ltx_stitched_result(extra_outputs):
            segment_count = resolve_ltx_stitched_segment_count(extra_outputs)
            if segment_count:
                tags.append(f"task.ltx_stitched_video:{segment_count}")
            return tags
        result_meta = extract_ltx_history_context(extra_outputs)
        tags.append(
            "task.ltx_start_end_frame"
            if bool(result_meta.get("ltx_use_end_frame"))
            or str(result_meta.get("ltx_mode") or "").strip() == "flf2v"
            else "task.ltx_start_frame"
        )
        segment_index = resolve_ltx_segment_index(extra_outputs)
        if segment_index:
            tags.append(f"task.ltx_segment:{segment_index}")
    return tags


async def build_user_history_payload(
    *,
    histories,
    gallery_task_ids: set[str],
):
    media_results = await asyncio.gather(
        *(
            resolve_history_media_urls(
                task_id=history.task_id,
                output_file=history.output_file,
                history_type=history.type,
            )
            for history in histories
        )
    )
    extra_output_results = await asyncio.gather(
        *(
            resolve_history_extra_outputs(
                task_id=history.task_id,
                extra_outputs=getattr(history, "extra_outputs", None),
                source=getattr(history, "source", None),
            )
            for history in histories
        )
    )
    items = []
    for history, media_result, resolved_extra_outputs in zip(
        histories,
        media_results,
        extra_output_results,
    ):
        result_meta = extract_history_result_meta(
            task_type=history.type,
            extra_outputs=getattr(history, "extra_outputs", None),
        )
        media_url, thumbnail_url = media_result
        input_payload = build_history_input_file_payload(
            getattr(history, "input_file", None),
            build_input_file_url=build_storage_input_file_url,
        )
        items.append(
            HistoryItem(
                task_id=history.task_id,
                type=history.type,
                prompt=history.prompt,
                id=history.id,
                input_file=getattr(history, "input_file", None),
                input_file_urls=input_payload["input_file_urls"],
                output_file=history.output_file,
                output_file_url=media_url,
                thumbnail_url=thumbnail_url,
                created_at=history.created_at,
                is_public=history.task_id in gallery_task_ids,
                billing_resolution=resolve_history_billing_resolution(history),
                width=history.width,
                height=history.height,
                duration=history.duration,
                allow_contribute=history.allow_contribute,
                source=history.source,
                is_favorited=history.is_favorited,
                result_meta=result_meta,
                extra_outputs=filter_user_visible_extra_outputs(
                    task_type=history.type,
                    extra_outputs=resolved_extra_outputs,
                ),
            )
        )
    return items


async def build_favorite_gallery_payload(
    *,
    histories,
    gallery_post_map: dict[str, object],
):
    media_results = await asyncio.gather(
        *(
            resolve_history_media_urls(
                task_id=history.task_id,
                output_file=history.output_file,
                history_type=history.type,
            )
            for history in histories
        )
    )
    items = []
    for history, media_result in zip(histories, media_results):
        gallery_post = gallery_post_map.get(history.task_id)
        result_meta = extract_history_result_meta(
            task_type=history.type,
            extra_outputs=getattr(history, "extra_outputs", None),
        )
        template_apply_disabled_reason = resolve_history_template_apply_disabled_reason(
            history
        )
        media_url, thumbnail_url = media_result
        input_payload = build_history_input_file_payload(
            getattr(history, "input_file", None),
            build_input_file_url=build_storage_input_file_url,
        )
        items.append(
            GalleryPostResponse(
                id=gallery_post.id if gallery_post else 0,
                task_id=history.task_id,
                media_type=(
                    gallery_post.media_type
                    if gallery_post
                    else get_media_type_from_history(history.type)
                ),
                billing_resolution=resolve_history_billing_resolution(
                    history,
                    width=gallery_post.width if gallery_post else None,
                    height=gallery_post.height if gallery_post else None,
                    gallery_post=gallery_post,
                ),
                width=gallery_post.width if gallery_post else history.width,
                height=gallery_post.height if gallery_post else history.height,
                duration=gallery_post.duration if gallery_post else history.duration,
                tags=extract_history_tags(
                    history.prompt,
                    task_type=history.type,
                    extra_outputs=getattr(history, "extra_outputs", None),
                ),
                likes_count=gallery_post.likes_count if gallery_post else 0,
                dislikes_count=gallery_post.dislikes_count if gallery_post else 0,
                applied_count=gallery_post.applied_count if gallery_post else 0,
                comments_count=gallery_post.comments_count if gallery_post else 0,
                thumbnail_url=thumbnail_url,
                media_url=media_url,
                created_at=history.created_at,
                is_active=gallery_post.is_active if gallery_post else False,
                prompt=history.prompt,
                prompt_unlocked=True,
                prompt_unlockable=False,
                prompt_is_masked=False,
                prompt_unlock_price=1,
                task_type=history.type,
                result_meta=result_meta,
                **input_payload,
                template_apply_supported=template_apply_disabled_reason is None,
                template_apply_disabled_reason=template_apply_disabled_reason,
                has_liked=False,
                has_disliked=False,
                author_name="我",
            )
        )
    return items
