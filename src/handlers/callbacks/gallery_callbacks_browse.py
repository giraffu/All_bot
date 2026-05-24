import contextlib
import html
import json
import logging
import os

from sqlalchemy import select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.handlers.callback_router import register_callback
from src.core.gallery_core import get_gallery_feed
from src.core.user_core import get_or_create_user_by_telegram
from src.database.core import AsyncSessionLocal
from src.database.models import GalleryPost, History
from src.lora_mapping import translate_tags
from src.services.storage import storage
from src.utils import (
    robust_edit_reply_markup,
    robust_delete_message,
    robust_send_message,
    robust_send_photo,
    robust_send_video,
    safe_answer_query,
)

logger = logging.getLogger(__name__)

_SUPPORTED_GALLERY_CATEGORIES = {
    "all",
    "i2ipro",
    "edit",
    "custvid",
    "vidlora",
    "ltxvid",
    "imglora",
}

GALLERY_CATEGORY_OPTIONS = (
    ("all", "🌈 全部"),
    ("ltxvid", "💎 高级图生视频"),
    ("i2ipro", "🎭 幻想换脸"),
    ("edit", "🖼️ 自由P图"),
    ("imglora", "🎨 图生图(附加模型)"),
    ("custvid", "🎬 自定义图生视频"),
    ("vidlora", "🌟 图生视频（附加模型）"),
)


def parse_gallery_browse_callback_data(data: str) -> tuple[str, str, int]:
    parts = data.split("_")
    sort_type = parts[2]
    if len(parts) >= 4 and parts[3] in _SUPPORTED_GALLERY_CATEGORIES:
        category = parts[3]
        page = int(parts[4]) if len(parts) > 4 else 0
    else:
        category = "all"
        page = int(parts[3]) if len(parts) > 3 else 0
    return sort_type, category, page


def build_gallery_category_menu(sort_type: str) -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton(
                label,
                callback_data=f"gallery_sort_{sort_type}_{category}",
            )
        ]
        for category, label in GALLERY_CATEGORY_OPTIONS
    ]
    return InlineKeyboardMarkup(keyboard)


async def _resolve_gallery_viewer_id(update: Update, sort_type: str) -> int | None:
    if sort_type != "mine":
        return None
    internal_user, _ = await get_or_create_user_by_telegram(update.effective_user.id)
    return internal_user.id


def _build_gallery_caption(post, translated_tags: list[str]) -> str:
    tags_str = " ".join(translated_tags) if translated_tags else "无标签"
    if post.media_type == "video":
        spec_str = (
            f"{post.duration}秒 | {post.width}x{post.height}"
            if post.duration
            else "视频"
        )
    else:
        spec_str = f"图片 | {post.width}x{post.height}" if post.width else "图片"

    author_name = "佚名道友"
    if post.user:
        author_name = post.user.username or f"道友_{post.user.id}"

    return (
        f"🏆 <b>修仙界广场</b>\n\n"
        f"👤 <b>作者</b>：{html.escape(author_name)}\n"
        f"📝 <b>提示词</b>：<code>*** 已隐藏（可一键应用体验） ***</code>\n"
        f"🏷 <b>标签</b>：{html.escape(tags_str)}\n"
        f"📏 <b>规格</b>：{html.escape(spec_str)}\n\n"
        f"❤️ {post.likes_count}  |  👎 {post.dislikes_count}  |  🪄 {post.applied_count} 次应用"
    )


def _build_gallery_reply_markup(
    *,
    post_id: int,
    sort_type: str,
    category: str,
    page: int,
    has_next: bool,
    likes_count: int,
    dislikes_count: int,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    f"👍 赞 ({likes_count})",
                    callback_data=f"gallery_like_{post_id}_{sort_type}_{category}_{page}",
                ),
                InlineKeyboardButton(
                    f"👎 踩 ({dislikes_count})",
                    callback_data=f"gallery_dislike_{post_id}_{sort_type}_{category}_{page}",
                ),
            ],
            [
                InlineKeyboardButton(
                    "⬅️ 上一个",
                    callback_data=f"gallery_page_{sort_type}_{category}_{max(0, page - 1)}",
                )
                if page > 0
                else InlineKeyboardButton("🚫", callback_data="noop"),
                InlineKeyboardButton(
                    "下一个 ➡️",
                    callback_data=f"gallery_page_{sort_type}_{category}_{page + 1}",
                )
                if has_next
                else InlineKeyboardButton("🚫", callback_data="noop"),
            ],
        ]
    )


def _resolve_gallery_media_source(
    *,
    post,
    history,
    storage_service,
) -> tuple[str | None, bytes | None, str | None]:
    is_test_bot = os.getenv("BOT_TYPE") == "TEST"
    cached_file_id = getattr(post, "telegram_file_id", None)
    if is_test_bot:
        cached_file_id = None

    output_file = history.output_file if history else None
    media_bytes = None
    if not cached_file_id and output_file:
        media_bytes = storage_service.get_file_bytes(output_file)
    return cached_file_id, media_bytes, output_file


async def _send_gallery_media_message(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    query,
    post,
    caption: str,
    reply_markup: InlineKeyboardMarkup,
    cached_file_id: str | None,
    media_bytes: bytes | None,
    output_file: str | None,
    storage_service,
    session_factory=AsyncSessionLocal,
):
    if not cached_file_id and not media_bytes:
        await robust_send_message(
            context.bot,
            query.message.chat_id,
            "❌ 抱歉，该文件已失效或被删除。",
        )
        return None

    sent_msg = None
    try:
        if post.media_type == "video":
            sent_msg = await robust_send_video(
                context.bot,
                query.message.chat_id,
                video=cached_file_id or media_bytes,
                caption=caption,
                reply_markup=reply_markup,
                parse_mode="HTML",
            )
        else:
            sent_msg = await robust_send_photo(
                context.bot,
                query.message.chat_id,
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
                    query.message.chat_id,
                    "❌ 抱歉，该文件已失效或被删除。",
                )
                return None
            if post.media_type == "video":
                sent_msg = await robust_send_video(
                    context.bot,
                    query.message.chat_id,
                    video=media_bytes,
                    caption=caption,
                    reply_markup=reply_markup,
                    parse_mode="HTML",
                )
            else:
                sent_msg = await robust_send_photo(
                    context.bot,
                    query.message.chat_id,
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
            async with session_factory() as session:
                update_post = (
                    await session.execute(
                        select(GalleryPost).where(GalleryPost.id == post.id)
                    )
                ).scalar_one_or_none()
                if update_post:
                    update_post.telegram_file_id = new_file_id
                    await session.commit()

    return sent_msg


async def display_gallery_sort_page(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    storage_service=storage,
    session_factory=AsyncSessionLocal,
):
    query = update.callback_query
    with contextlib.suppress(Exception):
        await query.answer()

    sort_type, category, page = parse_gallery_browse_callback_data(query.data)
    internal_user_id = await _resolve_gallery_viewer_id(update, sort_type)

    posts, _total = await get_gallery_feed(
        page=page + 1,
        size=2,
        category=category if category != "all" else None,
        sort_by=sort_type,
        user_id=internal_user_id,
    )

    if not posts:
        if page == 0:
            await safe_answer_query(
                query, text="📭 当前排行榜空空如也，快去投稿吧！", show_alert=True
            )
        else:
            await safe_answer_query(query, text="没有更多内容了~", show_alert=True)
        return

    post = posts[0]
    has_next = len(posts) > 1

    async with session_factory() as session:
        history = (
            await session.execute(select(History).where(History.task_id == post.task_id))
        ).scalars().first()
        try:
            tags = json.loads(post.tags)
        except Exception:
            tags = []

    caption = _build_gallery_caption(post, translate_tags(tags))
    reply_markup = _build_gallery_reply_markup(
        post_id=post.id,
        sort_type=sort_type,
        category=category,
        page=page,
        has_next=has_next,
        likes_count=post.likes_count,
        dislikes_count=post.dislikes_count,
    )

    await safe_answer_query(query, text="正在加载中...")
    cached_file_id, media_bytes, output_file = _resolve_gallery_media_source(
        post=post,
        history=history,
        storage_service=storage_service,
    )
    sent_msg = await _send_gallery_media_message(
        context=context,
        query=query,
        post=post,
        caption=caption,
        reply_markup=reply_markup,
        cached_file_id=cached_file_id,
        media_bytes=media_bytes,
        output_file=output_file,
        storage_service=storage_service,
        session_factory=session_factory,
    )
    if sent_msg:
        await robust_delete_message(query.message)


@register_callback("gallery_catmenu_")
async def gallery_catmenu_callback(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    sort_type = query.data.split("_")[2]
    await robust_edit_reply_markup(
        query.message,
        reply_markup=build_gallery_category_menu(sort_type),
    )
    await safe_answer_query(query)


@register_callback("gallery_sort_")
@register_callback("gallery_page_")
async def gallery_sort_page_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    try:
        await display_gallery_sort_page(update, context)
    except Exception as exc:
        logger.error(f"Error displaying gallery: {exc}")
        await safe_answer_query(
            update.callback_query, text="❌ 加载失败，请稍后再试", show_alert=True
        )
