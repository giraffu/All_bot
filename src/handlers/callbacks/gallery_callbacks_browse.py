import contextlib
import html
import json
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.handlers.callback_router import register_callback
from src.core.gallery_core import get_gallery_feed
from src.core.user_core import get_or_create_user_by_telegram
from src.database.core import AsyncSessionLocal
from src.lora_mapping import translate_tags
from src.services.gallery_browse_service import (
    get_history_for_gallery_post,
    resolve_gallery_media_source,
    send_gallery_media_message,
)
from src.utils import (
    robust_edit_reply_markup,
    robust_delete_message,
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


async def display_gallery_sort_page(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    session_factory=AsyncSessionLocal,
):
    query = update.callback_query
    with contextlib.suppress(Exception):
        await safe_answer_query(query)

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
        history = await get_history_for_gallery_post(post=post, session=session)
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
    media_source = await resolve_gallery_media_source(
        post=post,
        history=history,
    )
    sent_msg = await send_gallery_media_message(
        context=context,
        chat_id=query.message.chat_id,
        post=post,
        caption=caption,
        reply_markup=reply_markup,
        media_source=media_source,
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
