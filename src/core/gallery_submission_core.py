from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any, Callable

from src.constants import MODE_IMAGE_TO_VIDEO, MODE_NAME_MAP, MODE_WAN22_VIDEO_V2
from src.gallery_core_dependencies import (
    GallerySubmissionDependencies,
    get_default_gallery_submission_dependencies,
    get_gallery_submission_outbox,
)
from src.core.gallery_core_errors import GalleryCoreError
from src.core.gallery_submission_effects import build_gallery_submit_side_effects

if TYPE_CHECKING:
    from src.database.models import History

ALLOWED_WEB_SUBMIT_TYPES = list(
    dict.fromkeys(
        [
            "txt2img",
            "i2i_pro",
            "i2i_draw",
            "custom_video",
            MODE_IMAGE_TO_VIDEO,
            "ltx_video",
            MODE_WAN22_VIDEO_V2,
            "edit",
            "img2img_lora",
        ]
    )
)


def _detect_media_type(output_file: str) -> str:
    lower_path = output_file.lower()
    is_video = any(
        lower_path.endswith(ext) for ext in [".mp4", ".mov", ".webm", ".mkv", ".avi"]
    )
    return "video" if is_video else "image"


def _build_gallery_tags(history: History) -> list[str]:
    tags: list[str] = []
    base_tag = MODE_NAME_MAP.get(history.type, history.type)
    if base_tag:
        tags.append(f"#{base_tag}")

    if history.prompt:
        match = re.search(r"\[模型:\s*(.*?)\]\s*(.*)", history.prompt, re.DOTALL)
        if match:
            lora_tag = match.group(1).strip()
            tags.append(f"#{lora_tag}")

    return tags


async def _resolve_gallery_submit_capabilities(
    *,
    dependencies: GallerySubmissionDependencies | None,
    check_gallery_submit_limit_func,
    increment_gallery_submit_func,
):
    dependencies = dependencies or get_default_gallery_submission_dependencies()
    if check_gallery_submit_limit_func is None:
        check_gallery_submit_limit_func = dependencies.check_gallery_submit_limit_func
    if increment_gallery_submit_func is None:
        increment_gallery_submit_func = dependencies.increment_gallery_submit_func
    if (
        check_gallery_submit_limit_func is None
        or increment_gallery_submit_func is None
    ):
        gallery_submission_outbox = get_gallery_submission_outbox()
        if check_gallery_submit_limit_func is None:
            check_gallery_submit_limit_func = (
                gallery_submission_outbox.check_gallery_submit_limit
            )
        if increment_gallery_submit_func is None:
            increment_gallery_submit_func = (
                gallery_submission_outbox.increment_gallery_submit
            )
    return check_gallery_submit_limit_func, increment_gallery_submit_func


def _validate_gallery_submit_history(history: History | None) -> None:
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


async def _reactivate_existing_gallery_post(
    *,
    session,
    existing,
    user_id: int,
    task_id: str,
    gallery_submit_outcome_cls,
    dependencies: GallerySubmissionDependencies,
):
    if existing.user_id != user_id:
        raise GalleryCoreError("无法操作他人的投稿！")
    if existing.is_active:
        raise GalleryCoreError("您已经投稿过此内容啦！")

    history = await dependencies.get_gallery_history_for_user_task_func(
        session,
        task_id=task_id,
        user_id=user_id,
    )
    user_obj = await dependencies.get_gallery_user_func(session, user_id)
    await dependencies.reactivate_gallery_post_for_owner_func(
        session,
        existing_post=existing,
        history=history,
        user=user_obj,
    )
    return gallery_submit_outcome_cls(
        payload={
            "status": "success",
            "message": "已为您重新上架该作品！",
            "tags": [],
        },
        side_effects=[],
    )


async def _create_gallery_post_from_history(
    *,
    session,
    task_id: str,
    user_id: int,
    width: int | None,
    height: int | None,
    duration: int | None,
    dependencies: GallerySubmissionDependencies,
):
    history = await dependencies.get_gallery_history_for_user_task_func(
        session,
        task_id=task_id,
        user_id=user_id,
    )
    _validate_gallery_submit_history(history)

    media_type = _detect_media_type(history.output_file)
    tags = _build_gallery_tags(history)
    user_obj = await dependencies.get_gallery_user_func(session, user_id)
    await dependencies.create_gallery_post_from_history_func(
        session,
        task_id=task_id,
        user_id=user_id,
        media_type=media_type,
        width=width,
        height=height,
        duration=duration,
        tags_json=json.dumps(tags, ensure_ascii=False),
        history=history,
        user=user_obj,
    )
    return history, media_type, tags


def _build_gallery_submit_success_payload(tags: list[str]) -> dict[str, Any]:
    return {
        "status": "success",
        "message": f"投稿成功！已自动添加标签：{' '.join(tags)}",
        "tags": tags,
    }


async def process_submit_to_gallery_result_impl(
    *,
    gallery_submit_outcome_cls,
    user_id: int,
    task_id: str,
    width: int = None,
    height: int = None,
    duration: int = None,
    session_factory: Callable[[], Any] | None = None,
    dependencies: GallerySubmissionDependencies | None = None,
    check_gallery_submit_limit_func=None,
    increment_gallery_submit_func=None,
    build_gallery_submit_side_effects_func=None,
):
    dependencies = dependencies or get_default_gallery_submission_dependencies()
    session_factory = session_factory or dependencies.session_factory
    (
        check_gallery_submit_limit_func,
        increment_gallery_submit_func,
    ) = await _resolve_gallery_submit_capabilities(
        dependencies=dependencies,
        check_gallery_submit_limit_func=check_gallery_submit_limit_func,
        increment_gallery_submit_func=increment_gallery_submit_func,
    )
    build_gallery_submit_side_effects_func = (
        build_gallery_submit_side_effects_func or build_gallery_submit_side_effects
    )

    can_submit = await check_gallery_submit_limit_func(user_id, limit=10)
    if not can_submit:
        raise GalleryCoreError("您今日的投稿次数已达 10 次上限，请明日再来~")

    async with session_factory() as session:
        existing = await dependencies.get_gallery_post_by_task_id_func(session, task_id)

        if existing:
            return await _reactivate_existing_gallery_post(
                session=session,
                existing=existing,
                user_id=user_id,
                task_id=task_id,
                gallery_submit_outcome_cls=gallery_submit_outcome_cls,
                dependencies=dependencies,
            )

        history, media_type, tags = await _create_gallery_post_from_history(
            session=session,
            task_id=task_id,
            user_id=user_id,
            width=width,
            height=height,
            duration=duration,
            dependencies=dependencies,
        )

        side_effects = build_gallery_submit_side_effects_func(
            task_id=task_id,
            output_file=history.output_file,
            media_type=media_type,
        )
        await increment_gallery_submit_func(user_id)

        return gallery_submit_outcome_cls(
            payload=_build_gallery_submit_success_payload(tags),
            side_effects=side_effects,
        )
