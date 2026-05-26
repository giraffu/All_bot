import json
import re
from typing import Any, Callable

from sqlalchemy import select

from src.constants import MODE_IMAGE_TO_VIDEO, MODE_NAME_MAP
from src.database.models import GalleryPost, History, User
from src.core.gallery_core_dependencies import (
    get_gallery_session_factory,
    get_gallery_submission_outbox,
)
from src.core.gallery_core_errors import GalleryCoreError
from src.core.gallery_submission_effects import build_gallery_submit_side_effects

ALLOWED_WEB_SUBMIT_TYPES = list(
    dict.fromkeys(
        [
            "txt2img",
            "i2i_pro",
            "i2i_draw",
            "custom_video",
            MODE_IMAGE_TO_VIDEO,
            "ltx_video",
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


async def process_submit_to_gallery_result_impl(
    *,
    gallery_submit_outcome_cls,
    user_id: int,
    task_id: str,
    width: int = None,
    height: int = None,
    duration: int = None,
    session_factory: Callable[[], Any] | None = None,
    gallery_submission_outbox=None,
    check_gallery_submit_limit_func=None,
    increment_gallery_submit_func=None,
    build_gallery_submit_side_effects_func=None,
):
    session_factory = session_factory or get_gallery_session_factory()
    if (
        gallery_submission_outbox is None
        and (
            check_gallery_submit_limit_func is None
            or increment_gallery_submit_func is None
        )
    ):
        gallery_submission_outbox = get_gallery_submission_outbox()
    if check_gallery_submit_limit_func is None:
        check_gallery_submit_limit_func = (
            gallery_submission_outbox.check_gallery_submit_limit
        )
    if increment_gallery_submit_func is None:
        increment_gallery_submit_func = gallery_submission_outbox.increment_gallery_submit
    build_gallery_submit_side_effects_func = (
        build_gallery_submit_side_effects_func or build_gallery_submit_side_effects
    )

    can_submit = await check_gallery_submit_limit_func(user_id, limit=10)
    if not can_submit:
        raise GalleryCoreError("您今日的投稿次数已达 10 次上限，请明日再来~")

    async with session_factory() as session:
        existing = (
            (
                await session.execute(
                    select(GalleryPost).where(GalleryPost.task_id == task_id)
                )
            )
            .scalars()
            .first()
        )

        if existing:
            if existing.user_id != user_id:
                raise GalleryCoreError("无法操作他人的投稿！")

            if existing.is_active:
                raise GalleryCoreError("您已经投稿过此内容啦！")

            history = (
                (
                    await session.execute(
                        select(History)
                        .where(History.task_id == task_id)
                        .where(History.user_id == user_id)
                    )
                )
                .scalars()
                .first()
            )
            existing.is_active = True
            if history:
                history.is_public = True
            await session.commit()
            return gallery_submit_outcome_cls(
                payload={
                    "status": "success",
                    "message": "已为您重新上架该作品！",
                    "tags": [],
                },
                side_effects=[],
            )

        history = (
            (
                await session.execute(
                    select(History)
                    .where(History.task_id == task_id)
                    .where(History.user_id == user_id)
                )
            )
            .scalars()
            .first()
        )
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

        media_type = _detect_media_type(history.output_file)
        tags = _build_gallery_tags(history)
        new_post = GalleryPost(
            task_id=task_id,
            user_id=user_id,
            media_type=media_type,
            width=width,
            height=height,
            duration=duration,
            tags=json.dumps(tags, ensure_ascii=False),
        )
        session.add(new_post)

        user_obj = (
            await session.execute(select(User).where(User.id == user_id))
        ).scalar_one_or_none()
        if user_obj:
            user_obj.total_contributions = (user_obj.total_contributions or 0) + 1

        history.is_public = True
        await session.commit()

        side_effects = build_gallery_submit_side_effects_func(
            task_id=task_id,
            output_file=history.output_file,
            media_type=media_type,
        )
        await increment_gallery_submit_func(user_id)

        tags_str = " ".join(tags)
        return gallery_submit_outcome_cls(
            payload={
                "status": "success",
                "message": f"投稿成功！已自动添加标签：{tags_str}",
                "tags": tags,
            },
            side_effects=side_effects,
        )
