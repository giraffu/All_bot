import logging
import os
from dataclasses import dataclass

from sqlalchemy import select

from src.database.models import GalleryPost, History
from src.utils import (
    robust_send_message,
    robust_send_photo,
    robust_send_video,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GalleryBrowseMediaSource:
    cached_file_id: str | None
    media_bytes: bytes | None
    output_file: str | None


async def get_history_for_gallery_post(*, post, session) -> History | None:
    result = await session.execute(select(History).where(History.task_id == post.task_id))
    return result.scalars().first()


def resolve_gallery_media_source(
    *,
    post,
    history,
    storage_service,
) -> GalleryBrowseMediaSource:
    is_test_bot = os.getenv("BOT_TYPE") == "TEST"
    cached_file_id = getattr(post, "telegram_file_id", None)
    if is_test_bot:
        cached_file_id = None

    output_file = history.output_file if history else None
    media_bytes = None
    if not cached_file_id and output_file:
        media_bytes = storage_service.get_file_bytes(output_file)

    return GalleryBrowseMediaSource(
        cached_file_id=cached_file_id,
        media_bytes=media_bytes,
        output_file=output_file,
    )


async def update_gallery_post_telegram_file_id(
    *,
    post_id: int,
    telegram_file_id: str,
    session_factory,
) -> None:
    async with session_factory() as session:
        update_post = (
            await session.execute(select(GalleryPost).where(GalleryPost.id == post_id))
        ).scalar_one_or_none()
        if update_post is None:
            return
        update_post.telegram_file_id = telegram_file_id
        await session.commit()


async def send_gallery_media_message(
    *,
    context,
    chat_id: int,
    post,
    caption: str,
    reply_markup,
    media_source: GalleryBrowseMediaSource,
    storage_service,
    session_factory,
):
    cached_file_id = media_source.cached_file_id
    media_bytes = media_source.media_bytes
    output_file = media_source.output_file

    if not cached_file_id and not media_bytes:
        await robust_send_message(
            context.bot,
            chat_id,
            "❌ 抱歉，该文件已失效或被删除。",
        )
        return None

    sent_msg = None
    try:
        if post.media_type == "video":
            sent_msg = await robust_send_video(
                context.bot,
                chat_id,
                video=cached_file_id or media_bytes,
                caption=caption,
                reply_markup=reply_markup,
                parse_mode="HTML",
            )
        else:
            sent_msg = await robust_send_photo(
                context.bot,
                chat_id,
                photo=cached_file_id or media_bytes,
                caption=caption,
                reply_markup=reply_markup,
                parse_mode="HTML",
            )
    except Exception as exc:
        if cached_file_id and "wrong file identifier" in str(exc).lower():
            logger.warning("Cached file_id invalid, falling back to MinIO download...")
            media_bytes = storage_service.get_file_bytes(output_file) if output_file else None
            if not media_bytes:
                await robust_send_message(
                    context.bot,
                    chat_id,
                    "❌ 抱歉，该文件已失效或被删除。",
                )
                return None
            if post.media_type == "video":
                sent_msg = await robust_send_video(
                    context.bot,
                    chat_id,
                    video=media_bytes,
                    caption=caption,
                    reply_markup=reply_markup,
                    parse_mode="HTML",
                )
            else:
                sent_msg = await robust_send_photo(
                    context.bot,
                    chat_id,
                    photo=media_bytes,
                    caption=caption,
                    reply_markup=reply_markup,
                    parse_mode="HTML",
                )
            cached_file_id = None
        else:
            raise

    is_test_bot = os.getenv("BOT_TYPE") == "TEST"
    if sent_msg and not cached_file_id and not is_test_bot:
        new_file_id = None
        if post.media_type == "video" and sent_msg.video:
            new_file_id = sent_msg.video.file_id
        elif post.media_type != "video" and sent_msg.photo:
            new_file_id = sent_msg.photo[-1].file_id

        if new_file_id:
            await update_gallery_post_telegram_file_id(
                post_id=post.id,
                telegram_file_id=new_file_id,
                session_factory=session_factory,
            )

    return sent_msg
